@echo off
chcp 65001 >nul
cd /d "%~dp0"

where pyw >nul 2>nul
if errorlevel 1 goto use_python
start "" pyw -3 tools\content_manager.py
exit /b 0

:use_python
python tools\content_manager.py

:end
if errorlevel 1 (
  echo.
  echo 無法啟動內容管理器，請先安裝 Python 3.10 以上版本。
  pause
)
