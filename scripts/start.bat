@echo off
rem Run MockTest Maker.
rem
rem   scripts\start.bat        Python server on http://localhost:8000
rem                            (serves app/web/dist if built, else the legacy UI)
rem   scripts\start.bat dev    + Vite dev server on http://localhost:5173 (HMR, /api proxied)
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "SERVER=%ROOT%\app\server.py"
set "WEB=%ROOT%\app\web"
set "DIST=%WEB%\dist\index.html"

set "DEV="
if /i "%~1"=="dev"  set "DEV=1"
if /i "%~1"=="-dev" set "DEV=1"

rem --- pick an interpreter: %PYTHON% > .venv > py -3 > python ----------------
set "PYEXE="
set "PYARGS="
if defined PYTHON (
  set "PYEXE=%PYTHON%"
) else if exist "%ROOT%\.venv\Scripts\python.exe" (
  set "PYEXE=%ROOT%\.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARGS=-3"
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
  )
)

if not defined PYEXE (
  echo [start] Python not found. Install Python 3.10+ or set PYTHON.
  pause
  exit /b 1
)

rem --- dev: API + Vite, and take the API down again when Vite exits ----------
if defined DEV (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [dev] npm not found on PATH. Install Node.js 20+ first.
    pause
    exit /b 1
  )
  rem The API is torn down by port when Vite exits, so a server that was
  rem already running on :8000 is reused and left alone.
  set "API_STARTED="
  set "BUSY="
  for /f "delims=" %%L in ('netstat -ano ^| findstr /c:":8000" ^| findstr /i "LISTENING"') do set "BUSY=1"
  if defined BUSY (
    echo [dev] port 8000 already in use - reusing the running server.
  ) else (
    echo [dev] Python API on http://localhost:8000 ...
    start "MockTest API" /min /d "%ROOT%" "%PYEXE%" %PYARGS% "%SERVER%"
    set "API_STARTED=1"
  )
  pushd "%WEB%"
  call npm run dev
  popd
  if defined API_STARTED (
    for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:":8000" ^| findstr /i "LISTENING"') do taskkill /PID %%P /T /F >nul 2>nul
  )
  exit /b 0
)

rem --- normal: one process on :8000 ------------------------------------------
if not exist "%DIST%" (
  echo [start] app\web\dist not built - serving legacy UI. Run scripts\build.bat for the React app.
)

set "BUSY="
for /f "delims=" %%L in ('netstat -ano ^| findstr /c:":8000" ^| findstr /i "LISTENING"') do set "BUSY=1"
if defined BUSY (
  echo [start] port 8000 is already in use - opening the browser instead.
  start "" http://localhost:8000
  exit /b 0
)

echo [start] http://localhost:8000
%PYEXE% %PYARGS% "%SERVER%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [start] server exited with code %RC%
  pause
)
exit /b %RC%
