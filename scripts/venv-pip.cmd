@echo off
setlocal
set "ROOT=%~dp0.."
set "PY=%ROOT%\.venv\Scripts\python.exe"
if exist "%PY%" goto run
echo [error] Virtual environment python not found: %PY%
echo [hint] Create it first: py -3 -m venv .venv
exit /b 1
:run
"%PY%" -m pip %*
exit /b %ERRORLEVEL%
