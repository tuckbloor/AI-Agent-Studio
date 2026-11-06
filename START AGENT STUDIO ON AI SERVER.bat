@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI APP SERVER - AGENT STUDIO

echo ==========================================
echo AI APP SERVER + AGENT STUDIO
echo ==========================================
echo.
if not exist "engine\ai_app_server\__init__.py" goto :missing
if not exist "RUN_AGENT_STUDIO_ON_SERVER.py" goto :missing

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=%CD%\venv\Scripts\python.exe"
if not defined PY goto :setup
"%PY%" -c "import uvicorn, ai_app_server.server; from fastapi import FastAPI" >nul 2>nul
if errorlevel 1 goto :setup
echo Starting the integrated AI App Server on its configured port.
echo Sign in at /admin first, then choose Agent Studio in the admin menu.
echo Press Ctrl+C to stop this instance.
echo.
"%PY%" "RUN_AGENT_STUDIO_ON_SERVER.py"
echo.
echo Agent Studio stopped or could not start. See the message above.
pause
exit /b 0
:setup
echo Python environment missing or incomplete.
echo Re-run INSTALL AND RUN.bat from the complete Agent Studio package.
goto :fail
:missing
echo This folder is missing AI App Server source or Agent Studio files.
echo Use the complete Agent Studio installer package.
:fail
echo No database, settings or application files have been deleted.
pause
exit /b 1
