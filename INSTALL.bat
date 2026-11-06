@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Agent Studio - Install
if not exist "%~dp0tools\studio_install.py" goto :incomplete
if not exist "%~dp0tools\studio_gui.py" goto :incomplete

rem Keep advanced command-line operations for safe resume and automation.
if not "%~1"=="" goto :command_line

rem Detached Python Windows launcher: installation GUI remains open when this
rem short-lived batch window closes. No additional BAT files are created.
where py >nul 2>nul
if errorlevel 1 goto :python
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto :python
where pyw >nul 2>nul
if errorlevel 1 goto :console_py
start "" /D "%~dp0" pyw -3 "%~dp0tools\studio_gui.py"
if errorlevel 1 goto :launch_failed
exit /b 0

:console_py
py -3 "%~dp0tools\studio_gui.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%

:python
where python >nul 2>nul
if errorlevel 1 goto :missing
python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto :missing
where pythonw >nul 2>nul
if errorlevel 1 goto :console_python
start "" /D "%~dp0" pythonw "%~dp0tools\studio_gui.py"
if errorlevel 1 goto :launch_failed
exit /b 0

:console_python
python "%~dp0tools\studio_gui.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%

:command_line
where py >nul 2>nul
if errorlevel 1 goto :command_python
py -3 "%~dp0tools\studio_install.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
:command_python
where python >nul 2>nul
if errorlevel 1 goto :missing
python "%~dp0tools\studio_install.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%

:launch_failed
echo ERROR: Could not open the installer window.
echo Run this command in PowerShell to view errors:
echo py -3 "%~dp0tools\studio_gui.py"
pause
exit /b 1
:incomplete
echo ERROR: Extract the complete AI Agent Studio source ZIP first.
pause
exit /b 1
:missing
echo ERROR: Python 3.11 or newer is required; install Python and re-run INSTALL.bat.
echo https://www.python.org/downloads/windows/
pause
exit /b 1
