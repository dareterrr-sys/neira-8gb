@echo off
rem Brain with vision (+ voice, if conf.yaml uses it) WITHOUT touching Neira-start.bat. Use only while holding GPU.lock.
rem Variant by variables, e.g.:  set VISION_OFFLOAD=1 & run_vision_stack.bat
chcp 65001 >nul
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
if not "%NEIRA_NO_VOICE%"=="1" (
  findstr /R /C:"tts_model: *'*openai_tts" D:\AI\Open-LLM-VTuber\conf.yaml >nul && call D:\AI\voices\server\start-voice.bat
)
tasklist /FI "IMAGENAME eq llama-server.exe" | find /I "llama-server.exe" >nul && (echo llama-server already runs - stop it first & exit /b 1)
start "Neira brain vision" /MIN cmd /c "D:\AI\llama-neira-hot\brain-v40-live-vision.bat > D:\AI\llama-neira-hot\brain_vision.log 2>&1"
echo Waiting for the brain...
:wait_brain
curl -s http://127.0.0.1:8080/health | find "ok" >nul || (timeout /t 3 /nobreak >nul & goto wait_brain)
echo brain ready
