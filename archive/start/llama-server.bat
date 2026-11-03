@echo off
rem Neira's brain: Qwen3-VL-30B-A3B (text + vision) on llama.cpp, OpenAI-compatible API at http://127.0.0.1:8080/v1
rem --n-cpu-moe N keeps the MoE experts of the first N layers in RAM; the rest of the model stays on the GPU.
rem Lower N = faster but more VRAM. 48 = all experts in RAM (minimum VRAM). Leave ~2 GB VRAM for the voice.
rem Context: 32768 tokens (~1.6 GB VRAM with q8 KV cache); --context-shift drops the oldest tokens instead of failing.
rem The values can be overridden by the caller (Neira-start.bat lowers them when the Qwen voice needs the VRAM).
if not defined NCPUMOE set NCPUMOE=46
if not defined CTX set CTX=32768
rem MMPROJ_GPU=0 keeps the vision encoder in RAM (slower image reading, ~1 GB less VRAM)
set MMPROJ_OPT=
if "%MMPROJ_GPU%"=="0" set MMPROJ_OPT=--no-mmproj-offload
D:\Programs\llama.cpp\llama-server.exe ^
  -m D:\AI\gguf\Qwen3-VL-30B-A3B-Instruct-UD-Q4_K_XL.gguf ^
  --mmproj D:\AI\gguf\mmproj-F16.gguf %MMPROJ_OPT% ^
  -ngl 99 --n-cpu-moe %NCPUMOE% ^
  -c %CTX% --context-shift -fa on -ctk q8_0 -ctv q8_0 ^
  --jinja -n 1536 --temp 0.7 --top-p 0.8 --top-k 20 ^
  --host 127.0.0.1 --port 8080 --alias qwen3-vl %LLAMA_EXTRA%
