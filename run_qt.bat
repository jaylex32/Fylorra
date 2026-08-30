@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\\Scripts\\python.exe" (
  .venv\\Scripts\\python.exe main_qt.py
  exit /b %ERRORLEVEL%
)

python main_qt.py
exit /b %ERRORLEVEL%

