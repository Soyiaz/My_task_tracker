#!/usr/bin/env bash
# Install or update the Plan tracker on the cPanel server, over SSH.
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/Soyiaz/My_task_tracker/main/deploy/install.sh)
#   # or, once cloned:  bash ~/tracker/deploy/install.sh
#
# Idempotent: run it for the first install and for every update. It clones
# or pulls the repo into ~/tracker, builds .venv, installs requirements,
# seeds .streamlit/secrets.toml from the example only if it is missing,
# and (re)starts the pm2 app "tracker". It never copies, downloads or
# touches a database file: the hosted tracker starts empty and tracker.db
# is created by the app on first run.
#
# Overridable: REPO, DIR, BRANCH, PYTHON, VENV, PORT, BASE_URL_PATH.

set -euo pipefail

REPO="${REPO:-https://github.com/Soyiaz/My_task_tracker.git}"
DIR="${DIR:-$HOME/tracker}"
BRANCH="${BRANCH:-main}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- 1. code -----------------------------------------------------------------
if [ -d "$DIR/.git" ]; then
  say "Updating $DIR"
  git -C "$DIR" fetch --quiet origin
  git -C "$DIR" checkout --quiet "$BRANCH"
  git -C "$DIR" pull --ff-only --quiet origin "$BRANCH"
else
  say "Cloning $REPO into $DIR"
  git clone --quiet --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

# --- 2. python ---------------------------------------------------------------
# Prefer an explicit PYTHON, else the newest 3.11+ interpreter on the PATH.
pick_python() {
  if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return 0; fi
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        echo "$c"; return 0
      fi
    fi
  done
  return 1
}
PY="$(pick_python)" || die "No python3 >= 3.11 found. On cPanel try: ls /opt/alt/python3*/bin/python3  and rerun with PYTHON=/opt/alt/python311/bin/python3"
say "Using $("$PY" --version 2>&1) at $(command -v "$PY" || echo "$PY")"

if [ ! -x "$DIR/.venv/bin/python" ]; then
  say "Creating .venv"
  "$PY" -m venv "$DIR/.venv"
fi
VENV_PY="$DIR/.venv/bin/python"

say "Installing requirements"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r "$DIR/requirements.txt"
"$VENV_PY" -c 'import streamlit; print("streamlit", streamlit.__version__)'

# --- 3. config and folders ---------------------------------------------------
mkdir -p "$DIR/.streamlit" "$DIR/logs" "$DIR/files"
if [ ! -f "$DIR/.streamlit/secrets.toml" ]; then
  say "Seeding .streamlit/secrets.toml from deploy/secrets.example.toml (edit it afterwards)"
  cp "$DIR/deploy/secrets.example.toml" "$DIR/.streamlit/secrets.toml"
  chmod 600 "$DIR/.streamlit/secrets.toml"
fi

# --- 4. pm2 ------------------------------------------------------------------
if ! command -v pm2 >/dev/null 2>&1; then
  # cPanel keeps node and its globals under ~/nodevenv/<app>/<ver>/bin.
  for p in "$HOME"/nodevenv/*/*/bin "$HOME"/.npm-global/bin "$HOME"/node_modules/.bin; do
    if [ -x "$p/pm2" ]; then export PATH="$p:$PATH"; break; fi
  done
fi
command -v pm2 >/dev/null 2>&1 || die "pm2 is not on PATH. Find it with: ls ~/nodevenv/*/*/bin/pm2 ; or install it: npm install -g pm2 . If pm2 is not an option at all, use deploy/passenger_wsgi.py instead (see deploy/DEPLOY.md)."

export VENV="${VENV:-$VENV_PY}"
export PORT="${PORT:-8601}"
export BASE_URL_PATH="${BASE_URL_PATH:-/tracker}"

if pm2 describe tracker >/dev/null 2>&1; then
  say "Restarting pm2 app 'tracker'"
  pm2 restart "$DIR/deploy/ecosystem.streamlit.config.js" --only tracker --update-env
else
  say "Starting pm2 app 'tracker'"
  pm2 start "$DIR/deploy/ecosystem.streamlit.config.js"
fi
pm2 save

# --- 5. check ----------------------------------------------------------------
say "Waiting for Streamlit on 127.0.0.1:$PORT"
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT$BASE_URL_PATH/_stcore/health" >/dev/null 2>&1; then
    echo "Streamlit is up: http://127.0.0.1:$PORT$BASE_URL_PATH"
    echo "Now make Apache forward $BASE_URL_PATH to it (deploy/tracker.htaccess) and open https://aauaiandrobotics.com$BASE_URL_PATH"
    exit 0
  fi
  sleep 0.5
done
echo "Streamlit did not answer within 20 s. Look at:  pm2 logs tracker --lines 50"
exit 1
