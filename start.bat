@echo off
rem Summer tracker. Double-click to open. Close this window to stop it.
cd /d "%~dp0"
".venv\Scripts\streamlit.exe" run streamlit_app.py
pause
