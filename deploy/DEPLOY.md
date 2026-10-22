# Hosting the tracker on the cPanel server

This puts the Streamlit app on https://aauaiandrobotics.com/tracker, on the
same cPanel account that already runs the duo Node.js API under pm2, so it
is on all the time. Everything below runs over SSH as your cPanel user.

The hosted copy starts with an empty `tracker.db`; nothing from your laptop
is migrated, and nothing here reads, copies or uploads a database file.

What is in this folder:

| File | Purpose |
| --- | --- |
| `install.sh` | clone or pull the repo into `~/tracker`, build `.venv`, install requirements, seed secrets, start pm2 |
| `ecosystem.streamlit.config.js` | the pm2 app `tracker`: Streamlit on 127.0.0.1:8601 under `/tracker` |
| `tracker.htaccess` | Apache rules that forward `/tracker` (HTTP and WebSocket) to that port |
| `secrets.example.toml` | template for `.streamlit/secrets.toml`; placeholders only |
| `passenger_wsgi.py` | fallback launcher for cPanel "Setup Python App" if pm2 is not an option |

## 0. One decision first: accounts or not

Without `[auth]` and `[supabase]` in the secrets the app is one tracker with
one `tracker.db` on the server and no login page, which is the right choice
for a tracker you alone use; anyone with the URL can open it, so keep the
URL to yourself or put HTTP basic auth on `/tracker` in `.htaccess`. With
both sections filled in it becomes cloud mode: a Google or email login and a
separate database per account in a Supabase bucket, which only makes sense
if several people will have their own tracker. Recommendation: skip cloud
mode unless you want separate accounts.

## 1. Check the server (five minutes)

```bash
ssh <cpanel-user>@aauaiandrobotics.com

python3 --version              # need 3.11 or newer
ls /opt/alt/python3*/bin/python3   # cPanel's extra pythons, if python3 is older
python3 -m pip --version

which pm2 || ls ~/nodevenv/*/*/bin/pm2    # pm2 that keeps the Node API alive
pm2 list                                  # the API should be listed here

ls ~/nodevenv                 # exists  -> the API is a cPanel "Setup Node.js App" (Passenger)
cat ~/public_html/.htaccess   # PassengerAppRoot / PassengerBaseURI lines -> Passenger;
                              # RewriteRule ... [P] or ProxyPass lines    -> Apache proxy
```

In cPanel, look for the icons **Setup Node.js App** and **Setup Python App**
(Software section). If `~/nodevenv` exists and `.htaccess` carries
`PassengerBaseURI /repositories/private/backendAdvanced-telegram-task-tracker`,
the API's path mapping is done by Passenger and pm2 is only the keep-alive.
If instead `.htaccess` has a `RewriteRule ... [P]` pointing at
`127.0.0.1:3001`, the host allows mod_proxy from `.htaccess`, and step 4 will
work first time.

The API's health check is
https://aauaiandrobotics.com/repositories/private/backendAdvanced-telegram-task-tracker/api/health;
it should keep answering throughout, since nothing here touches it.

## 2. Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Soyiaz/My_task_tracker/main/deploy/install.sh)
```

If `python3` is too old, point the script at a newer one:
`PYTHON=/opt/alt/python311/bin/python3 bash <(curl ...)`. The script clones
into `~/tracker` (or pulls if it is already there), builds `.venv`, installs
`requirements.txt`, creates `logs/` and `files/`, copies
`deploy/secrets.example.toml` to `.streamlit/secrets.toml` only if that file
does not exist yet, then starts the pm2 app and saves the process list. It
ends by curling `http://127.0.0.1:8601/tracker/_stcore/health`; "Streamlit is
up" means the process side is done.

## 3. Secrets

```bash
nano ~/tracker/.streamlit/secrets.toml
pm2 restart tracker
```

Fill in `[duo]` (the duo API URL and your own duo password) if you want the
Duo page; leave the commented sections alone unless you want the journal,
the Telegram bot or cloud mode. The file is mode 600 and ignored by git.

## 4. Make Apache forward /tracker

Open `~/public_html/.htaccess` (the document root of aauaiandrobotics.com;
back it up first: `cp ~/public_html/.htaccess ~/htaccess.bak`) and paste the
contents of `~/tracker/deploy/tracker.htaccess` above any existing catch-all
`RewriteRule`. Do not remove anything that is already there.

```bash
curl -sI https://aauaiandrobotics.com/tracker/_stcore/health | head -1   # HTTP/2 200
```

Then open https://aauaiandrobotics.com/tracker in a browser. If the page
loads but stays on "Please wait..." or keeps reconnecting, the HTTP proxy
works and the WebSocket rule does not: `mod_proxy_wstunnel` is missing or the
`Upgrade` header is being stripped. Ask the host to enable
`mod_proxy_wstunnel`.

### If [P] is not allowed

A 500 on `/tracker` with "proxy flag not allowed" (or "mod_rewrite without
proxy enabled") in the Apache error log (cPanel: Metrics, Errors) means
`.htaccess` may not proxy. Two ways out, in order of preference:

1. Ask the host to enable `mod_proxy`, `mod_proxy_http` and
   `mod_proxy_wstunnel` for your account, or to add the four `ProxyPass`
   lines at the bottom of `tracker.htaccess` to the domain's vhost include.
2. Use cPanel's own proxy. In **Setup Python App** create an application
   with Python 3.11+, application root `tracker`, application URL `tracker`,
   startup file `passenger_wsgi.py`, entry point `application`; run
   `cp ~/tracker/deploy/passenger_wsgi.py ~/tracker/passenger_wsgi.py`; from
   the same screen install `requirements.txt` into the app's virtualenv.
   cPanel then writes its own `PassengerBaseURI /tracker` block into
   `.htaccess`, so remove the pasted rewrite block. Passenger itself cannot
   carry Streamlit's WebSocket, so this route only works when the host
   enables WebSocket pass-through for Passenger apps (it is on by default on
   current cPanel builds; the Node API on this server is proof if it uses
   Passenger). `passenger_wsgi.py` only starts Streamlit as a detached
   process on 127.0.0.1:8601 and redirects; it is the keep-alive to use when
   pm2 processes get killed, which you test with `pm2 list` after logging
   out and back in.

## 5. Verify

```bash
pm2 list                                                             # tracker: online
curl -s http://127.0.0.1:8601/tracker/_stcore/health                 # ok
curl -sI https://aauaiandrobotics.com/tracker/_stcore/health | head -1  # HTTP/2 200
```

Open https://aauaiandrobotics.com/tracker. The first visit creates
`~/tracker/tracker.db` and plants the starter plan; the sidebar should show
the plan progress bars and the Today page should load with no spinner.

## 6. Keep it alive across reboots

`pm2 save` records the process list; `pm2 startup` needs root, which shared
hosting does not give. Use a cron entry instead (cPanel: Cron Jobs, or
`crontab -e`), with pm2's full path from step 1:

```
@reboot /home/<user>/nodevenv/<app>/<ver>/bin/pm2 resurrect
```

If the API already has such a line, `pm2 save` was enough: one `resurrect`
brings both apps back.

## 7. Update

```bash
bash ~/tracker/deploy/install.sh      # git pull, pip install, pm2 restart tracker
```

or, by hand, `cd ~/tracker && git pull && pm2 restart tracker`. The database
and `files/` are untouched by either.

## 8. Logs

```bash
pm2 logs tracker --lines 100
tail -f ~/tracker/logs/tracker-error.log
pm2 describe tracker
```

The Apache side is under cPanel, Metrics, Errors.

## Troubleshooting

- `pm2 start` says the script is not found: the venv is somewhere else. Run
  `VENV=/path/to/.venv/bin/python pm2 start deploy/ecosystem.streamlit.config.js`.
- Port 8601 is taken: `PORT=8602 pm2 restart deploy/ecosystem.streamlit.config.js --update-env`
  and change the two `8601` in the pasted `.htaccess` block to match.
- File uploads or form posts fail with 403 through the proxy: XSRF
  protection and the proxy disagree about the origin. Set
  `--server.enableXsrfProtection false` in the ecosystem file as a last
  resort; the app is then protected only by the obscurity of its URL, so add
  basic auth to `/tracker` in `.htaccess` if you do this.
- The Duo page says it cannot reach the duo server: check `[duo] url` in the
  secrets and that the API health URL above answers.

## What only you can do

1. Log in over SSH and run `install.sh`; the login and the server are yours.
2. Edit `~/public_html/.htaccess` (step 4) and, if `[P]` is refused, talk to
   the host or set up the cPanel Python app (the fallback above).
