@echo off
rem Neira-gui.bat — запуск нативного оконного клиента Нейры.
chcp 65001 >nul
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1

rem The old brain Qwen3-VL (alias qwen3-vl, -n 1536) must not hold 8080, else it is reused below (03.11): stop it
curl -s http://127.0.0.1:8080/v1/models | find /I "qwen3-vl" >nul && (
  echo The old brain Qwen3-VL holds port 8080 - stopping it...
  for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:"127.0.0.1:8080 " ^| findstr LISTENING') do taskkill /PID %%p /F >nul
  timeout /t 3 /nobreak >nul
)

tasklist /FI "IMAGENAME eq llama-server.exe" | find /I "llama-server.exe" >nul || start "Neira brain" /MIN cmd /c "D:\AI\llama-neira-hot\brain-v40.bat > D:\AI\llama-neira-hot\brain_chat.log 2>&1"

:wait_brain
curl -s http://127.0.0.1:8080/health | find "ok" >nul || (timeout /t 3 /nobreak >nul & goto wait_brain)

start "" "D:\AI\neira-tools\neira_gui.exe"
