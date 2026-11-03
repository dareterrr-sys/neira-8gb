@echo off
rem Neira-api.bat — отправить промпт мозгу Нейры напрямую (обход чат-клиента).
rem Использование: Neira-api.bat "текст задачи"  |  echo "текст" | Neira-api.bat
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PY=D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe
set SCRIPT=D:\AI\neira-tools\neira_api.py
if "%~1"=="" (
  "%PY%" "%SCRIPT%"
) else (
  "%PY%" "%SCRIPT%" %*
)
