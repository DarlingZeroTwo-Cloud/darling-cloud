@echo off
chcp 65001 >nul
title Darling Zero Two 极速测速自适应下载器
color 0A
md 下载 2>nul
cls

echo.
echo ==========================================================
echo          ██╗  ██╗ █████╗ ██████╗ ██╗     ███████╗
echo          ██║  ██║██╔══██╗██╔══██╗██║     ██╔════╝
echo          ███████║███████║██████╔╝██║     █████╗  
echo          ██╔══██║██╔══██║██╔══██╗██║     ██╔══╝  
echo          ██║  ██║██║  ██║██║  ██║███████╗███████╗
echo          ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝
echo         Darling Zero Two 极速测速｜2秒测1-256线程
echo ==========================================================
echo.
echo 规则：2秒极速测试1~256线程 → 取最高稳定线程 → 全速下载
echo 实时显示：总进度｜总速度MB/s｜各线程速度
echo 保存目录：当前文件夹→【下载】
echo.
set /p "link=请粘贴下载链接："
echo.

:: 自动安装 aria2
if not exist aria2c.exe (
    echo 正在安装高速下载引擎 aria2...
    powershell -Command "$wc=New-Object Net.WebClient;$wc.DownloadFile('https://mirror.ghproxy.com/https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip','aria2.zip')"
    powershell Expand-Archive aria2.zip -Force
    copy aria2-1.37.0-win-64bit-build1\aria2c.exe . >nul
    rd /s /q aria2-1.37.0-win-64bit-build1
    del aria2.zip
)

set stable=1
echo ==============================================
echo 【极速测速中 2秒内完成 1~256线程】
echo ==============================================
echo.
for /L %%t in (1,1,256) do (
    aria2c -x%%t -s%%t -k1M -d "下载" --timeout=1 --max-tries=1 --dry-run "%link%" >nul 2>&1
    if errorlevel 28 goto endtest
    set stable=%%t
)
:endtest

echo.
echo ==============================================
echo 测速完成｜最高稳定线程：%stable%
echo 开始全速下载｜实时显示进度+速度+各线程速度
echo ==============================================
echo.
aria2c -x%stable% -s%stable% -k1M -d "下载" --timeout=8 --enable-color=true "%link%"
set final_err=%errorlevel%

echo.
if %final_err% equ 0 (
    echo ==============================================
    echo ✅ 下载成功！文件保存在【下载】文件夹
    echo ==============================================
) else (
    echo ❌ 下载失败，错误码：%final_err%
)
pause