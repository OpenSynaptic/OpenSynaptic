@echo off
setlocal
set "ROOT=%~dp0.."
call "%ROOT%\scripts\venv-python.cmd" -u "%ROOT%\src\main.py" %*
exit /b %ERRORLEVEL%
