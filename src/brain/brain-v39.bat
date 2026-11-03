@echo off
rem Neira's brain M2.1 for council v3.9: Qwen3.6-35B-A3B on the llama-neira hybrid (the developers' llama.cpp release
rem + our llama-server-impl.dll: per-request "cvec" control vector and the "probe" doubt sensor), 8 GB VRAM recipe.
rem vec_abstain.gguf (the В«РЅРµ Р·РЅР°СЋВ» vector, off unless a request asks) and probe16.json live in D:\AI\expert-map;
rem the server runs there because a "D:" in the vector path breaks llama.cpp's FILE:SCALE parser.
set NEIRA_PROBE=D:\AI\expert-map\probe16.json
cd /d D:\AI\expert-map
D:\AI\llama-neira\llama-server.exe -m D:\AI\gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ^
  -ngl 99 --n-cpu-moe 99 -c 32768 --parallel 1 --context-shift -fa on -ctk q8_0 -ctv q8_0 ^
  --jinja --chat-template-kwargs "{\"enable_thinking\":false}" -ub 512 -b 512 -n 8192 ^
  --temp 0.7 --top-p 0.8 --top-k 20 --spec-type draft-mtp --cache-ram 4096 ^
  --host 127.0.0.1 --port 8080 --alias brain
