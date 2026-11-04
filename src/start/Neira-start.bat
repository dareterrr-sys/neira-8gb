@echo off
chcp 65001 >nul
set UV_PYTHON_INSTALL_DIR=D:\Programs\uv\python
set UV_CACHE_DIR=D:\Cache\uv
set HF_HUB_DISABLE_XET=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PYTHONIOENCODING=utf-8
rem local services go direct, not through a VPN's system proxy (xray on 127.0.0.1:10809 answered 503 for them)
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
set PATH=D:\Programs\uv;D:\Programs\ffmpeg-shared\bin;D:\Programs\ffmpeg\bin;D:\Programs\node;%PATH%

rem Neira's voice FIRST (fine-tuned Qwen3-TTS server, int8, ~3.2 GB VRAM) when conf.yaml uses it, then the brain:
rem the brain sizes its hot expert pool by the VRAM left free at its start. With the voice the brain runs in live-talk
rem mode (brain-v40-live: 16k context, 512 batches, 3.2 GB); without it the full brain-v40 (32k, 2048 batches).
rem Switch the voice with D:\AI\voices\server\switch_voice.py
rem The old brain Qwen3-VL (alias qwen3-vl, -n 1536) must not hold 8080, else it is reused below (03.11): stop it
curl -s http://127.0.0.1:8080/v1/models | find /I "qwen3-vl" >nul && (
  echo The old brain Qwen3-VL holds port 8080 - stopping it...
  for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:"127.0.0.1:8080 " ^| findstr LISTENING') do taskkill /PID %%p /F >nul
  timeout /t 3 /nobreak >nul
)
set BRAIN=D:\AI\llama-neira-hot\brain-v40.bat
findstr /R /C:"tts_model: *'*openai_tts" D:\AI\Open-LLM-VTuber\conf.yaml >nul && (call D:\AI\voices\server\start-voice.bat & set BRAIN=D:\AI\llama-neira-hot\brain-v40-live.bat)

rem Start Neira's brain (Qwen3.6-35B-A3B, our llama.cpp build) in its own minimized window if it is not running yet
tasklist /FI "IMAGENAME eq llama-server.exe" | find /I "llama-server.exe" >nul || start "Neira brain" /MIN cmd /c "%BRAIN% > D:\AI\llama-neira-hot\brain_live.log 2>&1"
echo Waiting for the brain to load...
:wait_brain
curl -s http://127.0.0.1:8080/health | find "ok" >nul || (timeout /t 3 /nobreak >nul & goto wait_brain)
rem Warm the brain up in the background: the model file into the OS cache (else the first answer after a start
rem reads ~20 GB of experts from disk, minutes) + one long throwaway prompt
start "Neira brain warm-up" /MIN D:\AI\fastqwen\.venv\Scripts\python.exe -I D:\AI\voices\server\warm_brain.py


rem The council as the author designed it (his register, items 1 and 8, 04.11; live Neira too): the specialists
rem write the EXPRESSION, the calculator computes it, its result is the answer (council.py EXPR). 0 = v4.0 as before
set COUNCIL_EXPR=1

cd /d D:\AI\Open-LLM-VTuber
rem Dependencies are installed already (CUDA torch, faster-whisper...).
rem Never run "uv sync" here: it would replace the CUDA torch with the CPU one from uv.lock.
rem Neira in her own app window (Edge --app: no tabs, no address bar), not a browser tab (29.10, the author)
start "Neira window" /MIN cmd /c D:\AI\neira-tools\open_neira_window.bat
uv run --no-sync run_server.py
pause
