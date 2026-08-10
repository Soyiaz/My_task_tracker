"""Optional cloud mode: sign in with Google, keep your own database.

A deployed container has a disposable disk, so "everyone shares one database
that evaporates" is all a plain deployment can offer. This module fixes both
halves when — and only when — the host provides two secrets sections:

    [auth]        Streamlit's native OIDC login (Google)
    [supabase]    url, key (service_role), bucket — free-tier object storage

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
import tempfile
from pathlib import Path

# Session keys — db.py reads the two path overrides by these exact names.
K_DB = "_user_db_path"
K_FILES = "_user_files_dir"
K_UID = "_cloud_uid"
K_DIRTY = "_cloud_dirty"
K_DEMO = "_cloud_demo"

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


def _delete(path: str) -> None:
    import requests

    url, key, bucket = _store()
    requests.delete(
        f"{url}/storage/v1/object/{bucket}/{path}", headers=_headers(key), timeout=30
    )


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

    if not st.user.is_logged_in:
        _landing()
        st.stop()

    uid = _uid_for(st.user.email)
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
        "tracker, tied to your Google account. Only you see your data."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Sign in with Google",
            type="primary",
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
    if getattr(st.user, "is_logged_in", False):
        st.divider()
        st.caption(f":material/account_circle: {st.user.email}")
        if st.button("Sign out", icon=":material/logout:"):
            st.logout()
