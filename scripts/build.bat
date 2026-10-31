@echo off
rem Build the React front-end (app/web) into app/web/dist.
rem The Python server (app/server.py) serves that folder at "/" when present.
rem
rem Usage:  scripts\build.bat
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "WEB=%ROOT%\app\web"

where npm >nul 2>nul
if errorlevel 1 (
  echo [build] npm not found on PATH. Install Node.js 20+ first.
  pause
  exit /b 1
)

pushd "%WEB%"
if errorlevel 1 (
  echo [build] cannot enter "%WEB%"
  pause
  exit /b 1
)

if not exist "node_modules" (
  if exist "package-lock.json" (
    echo [build] npm ci
    call npm ci
  ) else (
    echo [build] npm install
    call npm install
  )
  if errorlevel 1 (
    popd
    echo [build] dependency install failed
    pause
    exit /b 1
  )
)

echo [build] npm run build
call npm run build
set "RC=%ERRORLEVEL%"
popd

if not "%RC%"=="0" (
  echo [build] failed with exit code %RC%
  pause
  exit /b %RC%
)
echo [build] done -^> app\web\dist
exit /b 0
