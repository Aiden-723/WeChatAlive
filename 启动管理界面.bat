@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 请先运行“首次安装.bat”
  pause
  exit /b 1
)
start "微信 AI 机器人管理" ".venv\Scripts\pythonw.exe" "bot_dashboard.py"

