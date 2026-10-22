@echo off
setlocal
cd /d "%~dp0"
echo Installing or updating Local Media dependencies...
py -m pip install --upgrade --target packages -r requirements.txt
if errorlevel 1 goto failed
if not exist runtime\node_modules\deno\deno.exe (
  echo Installing the YouTube JavaScript runtime...
  npm install --prefix runtime deno
  if errorlevel 1 goto failed
)
set "PATH=%CD%\runtime\node_modules\deno;%PATH%"
set "PYTHONPATH=%CD%\packages;%PYTHONPATH%"
echo.
echo Starting Local Media at http://127.0.0.1:8765
start "Local Media" http://127.0.0.1:8765
py server.py
goto end
:failed
echo.
echo Setup failed. Check Python, Node.js/npm, and your internet connection.
pause
:end
