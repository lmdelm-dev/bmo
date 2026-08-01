@echo off
rem BMO for Windows (run from a console)
setlocal
set "APP_DIR=%~dp0"
python "%APP_DIR%gameboy.py" %*
