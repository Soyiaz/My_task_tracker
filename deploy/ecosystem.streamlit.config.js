// pm2 ecosystem for the Plan tracker (Streamlit) on the cPanel server.
//
//   pm2 start deploy/ecosystem.streamlit.config.js && pm2 save
//
// One app, "tracker", running Streamlit through the project's own venv on
// 127.0.0.1 only; Apache (or cPanel's app proxy) puts it on the public
// hostname under BASE_URL_PATH. Knobs, all optional, read when pm2 starts:
//
//   VENV           python inside the venv   (default ~/tracker/.venv/bin/python)
//   PORT           local port               (default 8601)
//   BASE_URL_PATH  public sub-path          (default /tracker)
//
// Change a knob with e.g.
//   PORT=8602 pm2 restart deploy/ecosystem.streamlit.config.js --update-env

const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const VENV = process.env.VENV || path.join(os.homedir(), 'tracker', '.venv', 'bin', 'python');
const PORT = process.env.PORT || '8601';
const BASE_URL_PATH = process.env.BASE_URL_PATH || '/tracker';

module.exports = {
  apps: [
    {
      name: 'tracker',
      cwd: ROOT,
      // The venv's python is the executable; pm2 must not wrap it in node.
      script: VENV,
      interpreter: 'none',
      args: [
        '-m', 'streamlit', 'run', 'streamlit_app.py',
        '--server.port', PORT,
        '--server.address', '127.0.0.1',
        '--server.headless', 'true',
        '--server.baseUrlPath', BASE_URL_PATH,
        '--browser.gatherUsageStats', 'false',
        '--server.enableCORS', 'false',
        '--server.enableXsrfProtection', 'true',
      ].join(' '),
      watch: false,
      autorestart: true,
      max_restarts: 20,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: '1',
      },
      error_file: path.join(ROOT, 'logs', 'tracker-error.log'),
      out_file: path.join(ROOT, 'logs', 'tracker-out.log'),
      time: true,
    },
  ],
};
