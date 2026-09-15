@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import struct,sys; assert sys.version_info >= (3,9) and struct.calcsize('P') * 8 == 64" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if defined PYTHON_CMD goto python_found

where python >nul 2>&1
if not errorlevel 1 (
  python -c "import struct,sys; assert sys.version_info >= (3,9) and struct.calcsize('P') * 8 == 64" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if defined PYTHON_CMD goto python_found

where python3 >nul 2>&1
if not errorlevel 1 (
  python3 -c "import struct,sys; assert sys.version_info >= (3,9) and struct.calcsize('P') * 8 == 64" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python3"
)
if not defined PYTHON_CMD goto error

:python_found
%PYTHON_CMD% -m venv .venv
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not exist "bot_config.json" copy "bot_config.example.json" "bot_config.json" >nul
if not exist "填写API密钥.txt" echo API_KEY=请在这里粘贴你的API_KEY>"填写API密钥.txt"
echo.
echo 安装完成。填写“填写API密钥.txt”后，双击“启动管理界面.bat”。
pause
exit /b 0
:error
echo 没有找到可用的 64 位 Python 3.9 或更高版本。
echo 请从 https://www.python.org/downloads/windows/ 安装，并勾选 Add Python to PATH。
pause
