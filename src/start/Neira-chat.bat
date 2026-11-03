@echo off
chcp 65001 >nul
set UV_PYTHON_INSTALL_DIR=D:\Programs\uv\python
set UV_CACHE_DIR=D:\Cache\uv
set HF_HUB_DISABLE_XET=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PYTHONIOENCODING=utf-8
rem local services go direct, not through a VPN's system proxy
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
set PATH=D:\Programs\uv;D:\Programs\ffmpeg-shared\bin;D:\Programs\ffmpeg\bin;D:\Programs\node;%PATH%

set BRAIN=D:\AI\llama-neira-hot\brain-v40.bat
set PY=D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe
set WARMUP=D:\AI\fastqwen\.venv\Scripts\python.exe

echo ============================================
echo   Neira - chat mode
echo ============================================
echo.

rem 1. Start the brain (llama-server) in its own minimized window if it is not running yet
tasklist /FI "IMAGENAME eq llama-server.exe" | find /I "llama-server.exe" >nul || start "Neira brain" /MIN cmd /c "%BRAIN% > D:\AI\llama-neira-hot\brain_chat.log 2>&1"

echo Waiting for the brain to load...
:wait_brain
curl -s http://127.0.0.1:8080/health | find "ok" >nul || (timeout /t 3 /nobreak >nul & goto wait_brain)

rem Warm the brain up in the background (model file into OS cache + one long throwaway prompt)
start "Neira brain warm-up" /MIN "%WARMUP%" -I D:\AI\voices\server\warm_brain.py

rem 2. Text chat (no browser, no voice, no Live2D)
cd /d D:\AI\neira-tools
%PY% neira_chat_cli.py

echo.
set /p KILL="Close the brain too? (Y/N) "
if /I "%KILL%"=="Y" (
    taskkill /IM llama-server.exe /F >nul 2>&1
    echo Brain stopped.
) else (
    echo Brain is still running on http://127.0.0.1:8080
)
pause
