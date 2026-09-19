@echo off
rem ============================================
rem  重新打包 DarlingGUI（内置 Python 运行时 + aria2c）
rem  依赖：已安装 Python（含 tkinter、pip）
rem  产物：
rem    dist\DarlingGUI\       文件夹版（exe + _internal，启动快）
rem    dist\DarlingGUI.exe    单文件版（推荐分发，拷贝单个 exe 即可，双击自动解压运行）
rem ============================================
setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -m pip install --no-input pyinstaller || goto :err
set "VC=%LOCALAPPDATA%\Programs\Python\Python314\vcruntime140_1.dll"
"%PY%" -m PyInstaller --noconfirm --clean --onedir --windowed --icon "icon.ico" --name DarlingGUI --add-binary "aria2c.exe;." --add-binary "%VC%;." --add-data "icon.ico;." gui.py || goto :err
"%PY%" -m PyInstaller --noconfirm --onefile --windowed --icon "icon.ico" --name DarlingGUI --add-binary "aria2c.exe;." --add-binary "%VC%;." --add-data "icon.ico;." gui.py || goto :err

echo.
echo 打包完成：
echo   文件夹版：dist\DarlingGUI\DarlingGUI.exe（想保留 _internal 结构用这个）
echo   单文件版：dist\DarlingGUI.exe         （推荐，拷这一个文件就能跑）
pause
exit /b 0

:err
echo 打包失败，请检查上方报错信息。
pause
exit /b 1