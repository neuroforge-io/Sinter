@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" start.py %*
  goto :done
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3 start.py %*
  goto :done
)
where python >nul 2>&1
if not errorlevel 1 (
  python start.py %*
  goto :done
)
echo Sinter needs Python 3.10 or newer from python.org.
echo During installation, select Add Python to PATH.
:done
if errorlevel 1 pause
endlocal
