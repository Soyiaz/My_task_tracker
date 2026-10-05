"""Optional cloud mode: sign in (Google, or email and password), keep your
own database.

A deployed container has a disposable disk, so "everyone shares one database
that evaporates" is all a plain deployment can offer. This module fixes both
halves when — and only when — the host provides two secrets sections:

    [auth]        Streamlit's native OIDC login (Google)
    [supabase]    url, key (service_role), bucket — free-tier object storage

Email-and-password accounts need nothing more: the salted hash of the
password is one small file, ``<uid>/auth.json``, in the same bucket folder
as that account's database. No table anywhere is created or changed.

With them, every account gets its own SQLite file, pulled from the bucket at
login and parked back whenever it changes. The rest of the app is untouched:
it keeps talking to "one SQLite file" exactly as it does locally, because
``db.db_path()`` resolves to this user's copy for the duration of their
session. Without the secrets every function here is a no-op and the app is
the same local, loginless tracker it always was.

Honest limits: the whole file is uploaded on change (it is small), the last
writer wins if the same account is open in two places at once, and a write
made inside a fragment rerun is parked on the next full rerun.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets as pysecrets
import tempfile
import time
from pathlib import Path

# Session keys — db.py reads the two path overrides by these exact names.
K_DB = "_user_db_path"
K_FILES = "_user_files_dir"
K_UID = "_cloud_uid"
K_DIRTY = "_cloud_dirty"
K_DEMO = "_cloud_demo"
K_PW_EMAIL = "_cloud_pw_email"  # set once an email + password login succeeds

PW_MIN = 8
PW_ITERATIONS = 300_000
PW_MAX_FAILS = 8  # wrong passwords in a row before the account locks
PW_LOCK_SECONDS = 15 * 60

_BARE: dict = {}  # stands in for session state in tests and bare scripts


def _state():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is not None:
            import streamlit as st

            return st.session_state
    except Exception:
        pass
    return _BARE


def _secrets() -> dict | None:
    try:
        import streamlit as st

        if "supabase" in st.secrets and "auth" in st.secrets:
            return dict(st.secrets["supabase"])
    except Exception:
        pass
    return None


def enabled() -> bool:
    return _secrets() is not None


def _uid_for(email: str) -> str:
    """A stable, anonymous folder name per account — the bucket never needs
    to know the address itself."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def _workdir(uid: str) -> Path:
    return Path(tempfile.gettempdir()) / "tracker_cloud" / uid


# --- the bucket, by hand -----------------------------------------------------


def _store() -> tuple[str, str, str]:
    s = _secrets() or {}
    return s["url"].rstrip("/"), s["key"], s.get("bucket", "trackers")


def _headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "apikey": key}


def _get(path: str) -> bytes | None:
    import requests

    url, key, bucket = _store()
    r = requests.get(
        f"{url}/storage/v1/object/{bucket}/{path}", headers=_headers(key), timeout=30
    )
    return r.content if r.status_code == 200 else None


def _put(path: str, data: bytes) -> None:
    import requests

    url, key, bucket = _store()
    headers = {
        **_headers(key),
        "x-upsert": "true",
        "Content-Type": "application/octet-stream",
    }
    r = requests.post(
        f"{url}/storage/v1/object/{bucket}/{path}",
        headers=headers,
        data=data,
        timeout=60,
    )
    if r.status_code == 400 and "Bucket not found" in r.text:
        requests.post(
            f"{url}/storage/v1/bucket",
            headers=_headers(key),
            json={"name": bucket, "id": bucket, "public": False},
            timeout=30,
        )
        r = requests.post(
            f"{url}/storage/v1/object/{bucket}/{path}",
            headers=headers,
            data=data,
            timeout=60,
        )
    r.raise_for_status()


def _get_strict(path: str) -> bytes | None:
    """Like ``_get``, but only "there is no such object" comes back as None.
    Anything else that is not a 200 raises — login decisions must never
    mistake an outage for "this account does not exist"."""
    import requests

    url, key, bucket = _store()
    r = requests.get(
        f"{url}/storage/v1/object/{bucket}/{path}", headers=_headers(key), timeout=30
    )
    if r.status_code == 200:
        return r.content
    text = r.text.lower()
    if r.status_code == 404 or (
        r.status_code == 400 and ("not_found" in text or "not found" in text)
    ):
        return None
    raise RuntimeError(f"storage answered {r.status_code}")


def _delete(path: str) -> None:
    import requests

    url, key, bucket = _store()
    requests.delete(
        f"{url}/storage/v1/object/{bucket}/{path}", headers=_headers(key), timeout=30
    )


# --- passwords ---------------------------------------------------------------
# One JSON file per account, next to its database: a random salt and the
# PBKDF2 hash of the password. The password itself is never stored or logged.


def _pw_hash(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
    ).hex()


def _read_auth(uid: str) -> dict | None:
    raw = _get_strict(f"{uid}/auth.json")
    if raw is None:
        return None
    try:
        rec = json.loads(raw)
    except ValueError:
        raise RuntimeError("the stored password record is unreadable")
    return rec if isinstance(rec, dict) and rec.get("hash") else None


def _write_auth(uid: str, rec: dict) -> None:
    _put(f"{uid}/auth.json", json.dumps(rec).encode())


def valid_email(email: str) -> bool:
    e = email.strip()
    return "@" in e and " " not in e and "." in e.split("@")[-1] and len(e) >= 6


def has_password(email: str) -> bool:
    return _read_auth(_uid_for(email)) is not None


def set_password(email: str, password: str) -> None:
    """Create or replace the password of an account. Callers decide whether
    that is allowed; this only writes the record."""
    salt = pysecrets.token_hex(16)
    _write_auth(
        _uid_for(email),
        {
            "v": 1,
            "salt": salt,
            "iterations": PW_ITERATIONS,
            "hash": _pw_hash(password, salt, PW_ITERATIONS),
            "fails": 0,
            "locked_until": 0,
            "set_at": int(time.time()),
        },
    )


def register(email: str, password: str) -> tuple[bool, str]:
    """Sign up with an email and a password.

    An email that already owns a tracker made through Google sign-in cannot
    be claimed here — otherwise anyone could type someone else's address,
    pick a password, and walk into their data. That owner signs in with
    Google and sets a password from the sidebar instead.
    """
    email = email.strip().lower()
    if not valid_email(email):
        return False, "That does not look like an email address."
    if len(password) < PW_MIN:
        return False, f"Use at least {PW_MIN} characters for the password."
    uid = _uid_for(email)
    if _read_auth(uid) is not None:
        return False, "That email already has an account. Log in instead."
    if _get_strict(f"{uid}/tracker.db") is not None:
        return False, (
            "That email already has a tracker made with Google sign-in. Sign in "
            "with Google, then set a password from the sidebar."
        )
    set_password(email, password)
    return True, ""


def check_password(email: str, password: str) -> tuple[bool, str]:
    email = email.strip().lower()
    uid = _uid_for(email)
    rec = _read_auth(uid) if valid_email(email) else None
    if rec is None:
        _pw_hash(password, "00" * 16, PW_ITERATIONS)  # same work either way
        return False, "Wrong email or password."
    now = int(time.time())
    if int(rec.get("locked_until", 0)) > now:
        mins = (int(rec["locked_until"]) - now) // 60 + 1
        return False, f"Too many wrong passwords. Try again in {mins} minute(s)."
    good = hmac.compare_digest(
        _pw_hash(password, rec["salt"], rec.get("iterations", PW_ITERATIONS)), rec["hash"]
    )
    if good:
        if rec.get("fails"):
            rec["fails"] = 0
            rec["locked_until"] = 0
            _write_auth(uid, rec)
        return True, ""
    rec["fails"] = int(rec.get("fails", 0)) + 1
    if rec["fails"] >= PW_MAX_FAILS:
        rec["fails"] = 0
        rec["locked_until"] = now + PW_LOCK_SECONDS
    _write_auth(uid, rec)
    return False, "Wrong email or password."


def current_email() -> str | None:
    """Who is signed in, by either route. None when nobody is."""
    try:
        import streamlit as st

        if getattr(st.user, "is_logged_in", False):
            return st.user.email
    except Exception:
        pass
    return _state().get(K_PW_EMAIL)


def signed_in_with_password() -> bool:
    try:
        import streamlit as st

        if getattr(st.user, "is_logged_in", False):
            return False
    except Exception:
        pass
    return bool(_state().get(K_PW_EMAIL))


# --- the session -------------------------------------------------------------


def activate() -> None:
    """Called first thing in streamlit_app.py. Locally: does nothing. In
    cloud mode: gate behind login, then point this session at its own copy
    of its own database."""
    if not enabled():
        return
    import streamlit as st

    state = _state()
    if state.get(K_DEMO):
        return  # the shared, resettable container database — on purpose

    email = current_email()
    if not email:
        _landing()
        st.stop()

    uid = _uid_for(email)
    work = _workdir(uid)
    dbfile = work / "tracker.db"
    filesdir = work / "files"
    if state.get(K_UID) != uid:
        work.mkdir(parents=True, exist_ok=True)
        filesdir.mkdir(parents=True, exist_ok=True)
        brand_new = False
        if not dbfile.exists():
            remote = _get(f"{uid}/tracker.db")
            if remote:
                dbfile.write_bytes(remote)
            else:
                brand_new = True
        state[K_UID] = uid
        state[K_DB] = str(dbfile)
        state[K_FILES] = str(filesdir)
        state.pop(K_DIRTY, None)
        if brand_new:
            # A new account starts blank — the structure is theirs to build,
            # and the demo is the worked example. Only the measuring lenses
            # are planted, and even those are editable.
            from tracker import db, seed

            db.init(plant=False)
            seed.plant_minimal()


def _landing() -> None:
    import streamlit as st

    st.title(":material/target: Plan tracker")
    st.markdown(
        "Plan the week, work the day, log the hours — and keep your own "
        "tracker, tied to your account. Only you see your data."
    )

    login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
    with login_tab:
        with st.form("pw_login"):
            email = st.text_input("Email", key="pw_login_email")
            password = st.text_input("Password", type="password", key="pw_login_pw")
            go = st.form_submit_button(
                "Log in", type="primary", icon=":material/login:", use_container_width=True
            )
        if go:
            try:
                ok, msg = check_password(email, password)
            except Exception:
                ok, msg = False, "Storage is unreachable right now. Try again in a minute."
            if ok:
                _state()[K_PW_EMAIL] = email.strip().lower()
                st.rerun()
            st.error(msg)
    with signup_tab:
        with st.form("pw_signup"):
            email = st.text_input("Email", key="pw_signup_email")
            password = st.text_input(
                "Password",
                type="password",
                key="pw_signup_pw",
                help=f"At least {PW_MIN} characters.",
            )
            again = st.text_input("Password again", type="password", key="pw_signup_pw2")
            go = st.form_submit_button(
                "Create account",
                type="primary",
                icon=":material/person_add:",
                use_container_width=True,
            )
        if go:
            if password != again:
                st.error("The two passwords do not match.")
            else:
                try:
                    ok, msg = register(email, password)
                except Exception:
                    ok, msg = False, "Storage is unreachable right now. Try again in a minute."
                if ok:
                    _state()[K_PW_EMAIL] = email.strip().lower()
                    st.rerun()
                st.error(msg)

    st.caption("Or")
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Sign in with Google",
            icon=":material/login:",
            use_container_width=True,
        ):
            st.login()
    with c2:
        if st.button(
            "Just try the demo",
            icon=":material/visibility:",
            use_container_width=True,
        ):
            _state()[K_DEMO] = True
            st.rerun()
    st.caption(
        "Signing in starts you with a blank tracker — you build your own "
        "tracks and categories in Settings. Want to see how a filled-in one "
        "works first? The demo is a shared sandbox with an example plan: "
        "everyone sees the same data and it resets whenever the app restarts. "
        "You can also clone the repo and run it locally, no account needed."
    )


def mark_dirty() -> None:
    """db.py calls this after every write. Only means something for a signed-in
    cloud session."""
    state = _state()
    if state.get(K_UID):
        state[K_DIRTY] = True


def flush() -> None:
    """Park the user's database in the bucket if this run changed it. Called
    at the end of every full script run."""
    state = _state()
    uid = state.get(K_UID)
    if not uid or not state.get(K_DIRTY):
        return
    dbfile = Path(state[K_DB])
    if dbfile.exists():
        _put(f"{uid}/tracker.db", dbfile.read_bytes())
    state[K_DIRTY] = False


# --- attachments -------------------------------------------------------------


def push_attachment(stored_name: str) -> None:
    """Uploads are parked immediately — they can be big, and they never
    change after creation, so once is enough."""
    state = _state()
    uid = state.get(K_UID)
    if not uid:
        return
    path = Path(state[K_FILES]) / stored_name
    if path.exists():
        _put(f"{uid}/files/{stored_name}", path.read_bytes())


def fetch_attachment(stored_name: str) -> None:
    """A fresh container has an empty disk; pull a file back down the first
    time this session asks for it."""
    state = _state()
    uid = state.get(K_UID)
    if not uid:
        return
    path = Path(state[K_FILES]) / stored_name
    if path.exists():
        return
    data = _get(f"{uid}/files/{stored_name}")
    if data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def drop_attachment(stored_name: str) -> None:
    state = _state()
    uid = state.get(K_UID)
    if uid:
        _delete(f"{uid}/files/{stored_name}")


# --- sidebar -----------------------------------------------------------------


def account_ui() -> None:
    """Who is signed in, and the way out. Lives at the bottom of the sidebar;
    silent when cloud mode is off."""
    if not enabled():
        return
    import streamlit as st

    state = _state()
    if state.get(K_DEMO):
        st.divider()
        st.badge("Shared demo — resets on restart", icon=":material/science:", color="orange")
        if st.button("Sign in for your own", icon=":material/login:"):
            state.pop(K_DEMO, None)
            st.rerun()
        return
    email = current_email()
    if not email:
        return
    by_password = signed_in_with_password()
    st.divider()
    st.caption(f":material/account_circle: {email}")
    with st.popover(
        "Change password" if by_password else "Password", icon=":material/key:"
    ):
        _password_form(email, by_password)
    if st.button("Sign out", icon=":material/logout:"):
        if by_password:
            flush()
            for k in (K_PW_EMAIL, K_UID, K_DB, K_FILES, K_DIRTY):
                state.pop(k, None)
            st.rerun()
        else:
            st.logout()


def _password_form(email: str, by_password: bool) -> None:
    """Set or change the password of the signed-in account. Someone who came
    in through Google is already proven to own the email; someone who came
    in with a password has to give the current one again."""
    import streamlit as st

    if not by_password:
        st.caption(
            "Set a password to also log in with this email and a password, "
            "without Google. Setting it again replaces the old one."
        )
    with st.form("pw_change", border=False):
        current = (
            st.text_input("Current password", type="password", key="pw_change_cur")
            if by_password
            else ""
        )
        new = st.text_input(
            "New password",
            type="password",
            key="pw_change_new",
            help=f"At least {PW_MIN} characters.",
        )
        again = st.text_input("New password again", type="password", key="pw_change_new2")
        go = st.form_submit_button("Save password", type="primary", icon=":material/save:")
    if not go:
        return
    if len(new) < PW_MIN:
        st.error(f"Use at least {PW_MIN} characters.")
    elif new != again:
        st.error("The two new passwords do not match.")
    else:
        try:
            if by_password:
                ok, msg = check_password(email, current)
                if not ok:
                    st.error("The current password is wrong." if "Wrong" in msg else msg)
                    return
            set_password(email, new)
            st.success("Password saved.")
        except Exception:
            st.error("Storage is unreachable right now. Try again in a minute.")
