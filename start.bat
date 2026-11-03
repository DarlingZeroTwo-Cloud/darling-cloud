@echo off
chcp 65001 >nul
rem ============================================
rem  Darling Cloud v2  -  Windows CMD 一键启动
rem  用法：双击 start.bat  或  cmd 里执行 start.bat [端口]
rem ============================================
cd /d "%~dp0"
set PORT=%1
if "%PORT%"=="" set PORT=8080

where python >nul 2>nul
if errorlevel 1 (
  echo [Darling Cloud] 未检测到 Python，请先安装 Python 3.10+（勾选 Add to PATH）
  echo   下载: https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist "server\requirements.installed" (
  echo [Darling Cloud] 首次运行：安装依赖（华为云镜像）...
  python -m pip install -r server\requirements.txt -i https://mirrors.huaweicloud.com/repository/pypi/simple
  if errorlevel 1 (
    echo [Darling Cloud] 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
  )
  echo ok > server\requirements.installed
)

echo [Darling Cloud] 启动服务端 http://127.0.0.1:%PORT%
echo   公开广场免登录；首个注册账号自动管理员；帮助页 /help
start "" http://127.0.0.1:%PORT%
cd server
python cli.py start --host 0.0.0.0 --port %PORT% --data ..\data
pause
