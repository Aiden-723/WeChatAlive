@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not exist "bot_config.json" copy "bot_config.example.json" "bot_config.json" >nul
if not exist "填写千问密钥.txt" echo DASHSCOPE_API_KEY=请在这里粘贴你的API_KEY>"填写千问密钥.txt"
echo.
echo 安装完成。填写“填写千问密钥.txt”后，双击“启动管理界面.bat”。
pause
exit /b 0
:error
echo 没有找到可用的 Python 3，请先安装 64 位 Python 3.9 或更高版本。
pause

