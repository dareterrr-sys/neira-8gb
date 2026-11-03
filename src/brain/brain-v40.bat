@echo off
rem Neira's brain M2.2 (28.10): brain-v39 + the mixed CPU/GPU split of the experts (llama-neira-hot, our llama.cpp
rem build 1431019 + llama-neira-hot.cpp): the most used experts by the expert map (chat, Neira's answers, tasks, EGE)
rem are also kept in VRAM and computed there, the rest on the CPU - nothing is copied per token. The pool size
rem follows the free VRAM at start (NEIRA_HOT_RESERVE_MIB stays free, default 2600): start the voice first, the brain
rem after it, and the pool shrinks or switches itself off. -ub 2048: long prompts read twice as fast.
rem Measured (same test, 28.10): writing 32 -> 42.7 tokens/s, long prompt reading 285 -> 580 tokens/s.
rem Roll back: brain-v39.bat in D:\AI\llama-neira.
set NEIRA_PROBE=D:\AI\expert-map\probe16.json
set NEIRA_HOT_EXPERTS=D:\AI\llama-neira-hot\hot_experts.bin
rem the real free VRAM (games and browsers included) before the brain loads: CUDA on Windows does not see them
for /f %%a in ('nvidia-smi --query-gpu^=memory.free --format^=csv^,noheader^,nounits') do set NEIRA_HOT_FREE_MIB=%%a
rem Лимит генерации (токенов за ответ): по умолчанию 16384; переопределяется через N_PREDICT
if not defined N_PREDICT set N_PREDICT=16384
cd /d D:\AI\expert-map
D:\AI\llama-neira-hot\llama-server.exe -m D:\AI\gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ^
  -ngl 99 --n-cpu-moe 99 -c 32768 --parallel 1 --context-shift -fa on -ctk q8_0 -ctv q8_0 ^
  --jinja --reasoning off -ub 2048 -b 2048 -n %N_PREDICT% ^
  --temp 0.7 --top-p 0.8 --top-k 20 --repeat-penalty 1.1 --spec-type draft-mtp --cache-ram 1024 ^
  --host 127.0.0.1 --port 8080 --alias brain
