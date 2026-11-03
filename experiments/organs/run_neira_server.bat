@echo off
rem Neira's app server alone (no browser, no brain/voice start) - for tests; same environment as Neira-start.bat
chcp 65001 >nul
set UV_PYTHON_INSTALL_DIR=D:\Programs\uv\python
set UV_CACHE_DIR=D:\Cache\uv
set HF_HUB_DISABLE_XET=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PYTHONIOENCODING=utf-8
set TTS_HOME=D:\AI\tts-models
set COQUI_TOS_AGREED=1
set PATH=D:\Programs\uv;D:\Programs\ffmpeg-shared\bin;D:\Programs\ffmpeg\bin;D:\Programs\node;%PATH%
cd /d D:\AI\Open-LLM-VTuber
uv run --no-sync run_server.py
