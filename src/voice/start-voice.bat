@echo off
rem Neira's voice: our fine-tuned Qwen3-TTS (RefVoice's timbre, native Russian) as a speech service on port 8090.
rem Started by D:\AI\Neira-start.bat in its own minimized window.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set HF_HUB_OFFLINE=1
set PATH=D:\Programs\ffmpeg-shared\bin;D:\Programs\ffmpeg\bin;%PATH%

rem Stress marks (RUAccent, its own venv; the voice k7 follows them). Optional: without it the voice speaks unmarked.
curl -s http://127.0.0.1:8093/health | find "ok" >nul || start "Neira stress" /MIN /D D:\AI\ruaccent D:\AI\ruaccent\.venv\Scripts\python.exe -W ignore D:\AI\ruaccent\stress_service.py 8093
set STRESS_WAIT=0
:wait_stress
curl -s http://127.0.0.1:8093/health | find "ok" >nul || (timeout /t 2 /nobreak >nul & set /a STRESS_WAIT+=1 & if not "%STRESS_WAIT%"=="45" goto wait_stress)

curl -s http://127.0.0.1:8090/health | find "ok" >nul || start "Neira voice" /MIN D:\AI\fastqwen\.venv\Scripts\python.exe -I D:\AI\voices\server\neira_voice_server.py 8090

echo Waiting for the voice to load...
:wait_tts
curl -s http://127.0.0.1:8090/health | find "ok" >nul || (timeout /t 3 /nobreak >nul & goto wait_tts)
echo Voice is ready.
