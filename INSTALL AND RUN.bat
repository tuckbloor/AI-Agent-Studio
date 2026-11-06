@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Agent Studio - One Complete Installer

echo ==========================================
echo AGENT STUDIO v2.2 - COMPLETE INSTALL
echo ==========================================
echo Your existing AI App Server database and configuration are preserved.
echo.
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "INSTALL_AND_RUN.py" %*
    set "RESULT=!ERRORLEVEL!"
    goto :finish
)
where python >nul 2>nul
if not errorlevel 1 (
    python "INSTALL_AND_RUN.py" %*
    set "RESULT=!ERRORLEVEL!"
    goto :finish
)
echo Python 3.11 or newer is required.
set "RESULT=1"
:finish
if "%RESULT%"=="2" echo Installation was verified, but server startup did not succeed. Check the message above.
if not "%RESULT%"=="0" if not "%RESULT%"=="2" echo INSTALLATION WAS NOT VERIFIED. See the error above; existing data was not reset.
echo.
pause
exit /b %RESULT%
