@echo off
setlocal
call "%~dp0scripts\run-main.cmd" %*
exit /b %ERRORLEVEL%
