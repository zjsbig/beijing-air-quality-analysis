@echo off
chcp 65001 >nul
cd /d "%~dp0"
"D:\Python312\python.exe" analyze_air_quality.py
echo.
echo 运行结束，按任意键关闭窗口
pause >nul
