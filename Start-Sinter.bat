@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ERRORLEVEL="
cd /d "%~dp0"
if defined SINTER_FIXTURE_BATCH_STAGES call :trace batch_entered
if exist ".venv\Scripts\python.exe" (
  if defined SINTER_FIXTURE_BATCH_STAGES call :trace start_dispatch_begin
  ".venv\Scripts\python.exe" start.py %*
  goto :done
)
set "SINTER_PYTHON="
set "SINTER_PY_LAUNCHER="
if defined SINTER_FIXTURE_BATCH_STAGES call :trace python_lookup_begin
for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" $PATH:python.exe 2^>nul') do (
  set "SINTER_CANDIDATE=%%P"
  call :probe_candidate
)
if defined SINTER_FIXTURE_BATCH_STAGES call :trace python_lookup_end
if defined SINTER_PYTHON goto :launch
rem Listing installed runtimes never requests a download. Do not launch py -3.
if defined SINTER_FIXTURE_BATCH_STAGES call :trace launcher_lookup_begin
for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" $PATH:py.exe 2^>nul') do (
  if not defined SINTER_PY_LAUNCHER set "SINTER_PY_LAUNCHER=%%P"
)
if defined SINTER_FIXTURE_BATCH_STAGES call :trace launcher_lookup_end
if not defined SINTER_PY_LAUNCHER goto :missing
if defined SINTER_FIXTURE_BATCH_STAGES call :trace launcher_listing_begin
for /f "tokens=1,*" %%T in ('""%SINTER_PY_LAUNCHER%" -0p 2^>nul"') do (
  set "SINTER_LIST_TAG=%%T"
  set "SINTER_CANDIDATE=%%U"
  call :listed_candidate
)
if defined SINTER_FIXTURE_BATCH_STAGES call :trace launcher_listing_end
if defined SINTER_PYTHON goto :launch
:missing
echo Sinter needs Python 3.10 or newer from python.org.
echo During installation, select Add Python to PATH.
echo For a custom runtime, run its python.exe with this folder's start.py.
set "SINTER_EXIT=1"
goto :finish
:launch
if defined SINTER_FIXTURE_BATCH_STAGES call :trace start_dispatch_begin
"%SINTER_PYTHON%" start.py %*
:done
set "SINTER_EXIT=%errorlevel%"
if defined SINTER_FIXTURE_BATCH_STAGES call :trace start_dispatch_end
:finish
if defined SINTER_FIXTURE_BATCH_STAGES call :trace batch_finish
if not "%SINTER_EXIT%"=="0" pause
endlocal & exit /b %SINTER_EXIT%

:listed_candidate
if defined SINTER_FIXTURE_BATCH_STAGES call :trace listed_candidate_entered
if defined SINTER_PYTHON exit /b 0
rem Admit complete ordinary CPython tags, not headers or arbitrary commands.
if defined SINTER_FIXTURE_BATCH_STAGES call :trace tag_filter_begin
set SINTER_LIST_TAG| "%SystemRoot%\System32\findstr.exe" /r /x /c:"SINTER_LIST_TAG=-V:3\.[0-9][0-9]*[-0-9]*" /c:"SINTER_LIST_TAG=-3\.[0-9][0-9]*[-0-9]*" >nul
if defined SINTER_FIXTURE_BATCH_STAGES call :trace tag_filter_end
if not "%errorlevel%"=="0" exit /b 0
rem Before expansion, admit no quotes or exactly one complete outer quote pair.
if defined SINTER_FIXTURE_BATCH_STAGES call :trace quote_filter_begin
set SINTER_CANDIDATE| "%SystemRoot%\System32\findstr.exe" /r /x ^
  /c:"SINTER_CANDIDATE=[^\"]*" /c:"SINTER_CANDIDATE=\"[^\"]*\"" ^
  /c:"SINTER_CANDIDATE=\* [^\"]*" /c:"SINTER_CANDIDATE=\* \"[^\"]*\"" >nul
if defined SINTER_FIXTURE_BATCH_STAGES call :trace quote_filter_end
if not "%errorlevel%"=="0" exit /b 0
set "SINTER_CANDIDATE=%SINTER_CANDIDATE:"=%"
for /f "tokens=1,*" %%P in ("%SINTER_CANDIDATE%") do (
  if "%%P"=="*" set "SINTER_CANDIDATE=%%Q"
)
call :probe_candidate
exit /b 0

:probe_candidate
if defined SINTER_PYTHON exit /b 0
if not "%SINTER_CANDIDATE:~1,2%"==":\" if not "%SINTER_CANDIDATE:~0,2%"=="\\" exit /b 0
if /i not "%SINTER_CANDIDATE:~-4%"==".exe" exit /b 0
if not exist "%SINTER_CANDIDATE%" exit /b 0
if exist "%SINTER_CANDIDATE%\*" exit /b 0
rem Positive runtime landmarks keep Store/manager aliases out of the probe.
set "SINTER_RUNTIME_PRESENT="
for %%P in ("%SINTER_CANDIDATE%") do (
  if exist "%%~dpPLib\os.py" set "SINTER_RUNTIME_PRESENT=1"
  if exist "%%~dpPpython3*.zip" set "SINTER_RUNTIME_PRESENT=1"
  if exist "%%~dpPpyvenv.cfg" set "SINTER_RUNTIME_PRESENT=1"
  if exist "%%~dpP..\pyvenv.cfg" set "SINTER_RUNTIME_PRESENT=1"
)
if not defined SINTER_RUNTIME_PRESENT exit /b 0
if defined SINTER_FIXTURE_BATCH_STAGES call :trace runtime_probe_begin
"%SINTER_CANDIDATE%" -I -S -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if "%errorlevel%"=="0" set "SINTER_PYTHON=%SINTER_CANDIDATE%"
if defined SINTER_FIXTURE_BATCH_STAGES call :trace runtime_probe_end
exit /b 0

:trace
set "SINTER_TRACE_STATUS=%errorlevel%"
rem Opt-in fixture diagnostics contain fixed phase names, never runtime values.
2>nul >>"%SINTER_FIXTURE_BATCH_STAGES%" echo %~1
exit /b %SINTER_TRACE_STATUS%
