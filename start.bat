@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PORT=%1
if "%PORT%"=="" set PORT=8080

if exist "darling-cloud.exe" goto run_exe

where python >nul 2>nul
if errorlevel 1 (
  echo [Darling Cloud] Python not found. Install Python 3.10+ first.
  pause
  exit /b 1
)
if not exist "server\requirements.installed" (
  echo [Darling Cloud] First run: installing deps...
  python -m pip install -r server\requirements.txt -i https://mirrors.huaweicloud.com/repository/pypi/simple
  if errorlevel 1 ( echo Install failed. & pause & exit /b 1 )
  echo ok > server\requirements.installed
)
echo [Darling Cloud] http://127.0.0.1:%PORT%
start "" http://127.0.0.1:%PORT%
cd server
python cli.py start --host 0.0.0.0 --port %PORT% --data ..\data
pause
exit /b 0

:run_exe
echo [Darling Cloud] http://127.0.0.1:%PORT%
echo aria2c bundled, auto-started.
start "" http://127.0.0.1:%PORT%
darling-cloud.exe start --host 0.0.0.0 --port %PORT% --data .\data
pause
