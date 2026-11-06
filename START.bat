@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Agent Studio
set "ACTION=start"
set "BROWSER_FLAG="
if /I "%~1"=="--background" set "BROWSER_FLAG=--no-browser"
if /I "%~1"=="--stop" set "ACTION=stop"
if /I "%~1"=="--status" set "ACTION=status"
if /I "%~1"=="--disable-autostart" set "ACTION=remove-startup"

rem The SOURCE ZIP includes app/studio_integration too. Check for framework FIRST.
rem Extracted source: find/ask for the real installed destination.
if exist "%~dp0framework\engine\pyproject.toml" goto :source
rem Installed copy: use its isolated environment, or recover it if interrupted.
if exist "%~dp0engine\pyproject.toml" if exist "%~dp0app\studio_integration\routes.py" goto :installed

echo ERROR: This is neither the extracted complete source nor an installed Studio.
echo Extract the full ZIP and run INSTALL.bat once.
goto :failed

:installed
if not exist "%~dp0.venv\Scripts\python.exe" goto :recover
"%~dp0.venv\Scripts\python.exe" -m ai_app_server.desktop_launcher %ACTION% --project "%CD%" %BROWSER_FLAG%
goto :done

:recover
if not exist "%~dp0tools\studio_install.py" (
  echo The Python environment is missing and this older installation has no recovery helper.
  echo Use INSTALL.bat --resume FROM THE NEW SOURCE ZIP and select this installed folder:
  echo %~dp0
  goto :failed
)
if /I not "%ACTION%"=="start" (
  echo This installation has no Python environment. Start it first to complete setup.
  goto :failed
)
call :findpython
if errorlevel 1 goto :failed
%PY_CMD% "%~dp0tools\studio_install.py" --resume "%CD%"
goto :done

:source
call :findpython
if errorlevel 1 goto :failed
%PY_CMD% "%~dp0tools\studio_install.py" --launch-installed --action %ACTION% %BROWSER_FLAG%
goto :done

:findpython
set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=py -3"
)
if defined PY_CMD exit /b 0
where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)
if defined PY_CMD exit /b 0
echo Python 3.11+ not found. Install it from https://www.python.org/downloads/windows/
exit /b 1

:failed
set "RESULT=1"
goto :exit
:done
set "RESULT=%ERRORLEVEL%"
:exit
if not "%RESULT%"=="0" (
 echo AI Agent Studio could not start. Please see the error above.
 if "%~1"=="" pause
)
exit /b %RESULT%
