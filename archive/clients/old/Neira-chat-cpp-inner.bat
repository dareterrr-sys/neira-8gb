@echo off
rem Neira-chat-cpp-inner.bat — внутренний запуск: мозг + C++ клиент.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1

tasklist /FI "IMAGENAME eq llama-server.exe" | find /I "llama-server.exe" >nul || start "Neira brain" /MIN cmd /c "D:\AI\llama-neira-hot\brain-v40.bat > D:\AI\llama-neira-hot\brain_chat.log 2>&1"

:wait_brain
curl -s http://127.0.0.1:8080/health | find "ok" >nul || (timeout /t 3 /nobreak >nul & goto wait_brain)

cd /d D:\AI\neira-tools
neira_chat_cli.exe
