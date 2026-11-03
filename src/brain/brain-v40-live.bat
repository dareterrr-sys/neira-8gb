@echo off
rem Neira's brain for live talk next to her voice (28.10): brain-v40 with a 16k context and 512-token batches - 3.2 GB
rem of VRAM instead of 4.0 (measured: compute buffer 738 -> 418 MiB, MTP draft 438 -> 242, context cache 340 -> 170),
rem so brain + int8 voice (~3.2 GB) fit in 8 GB without Windows pushing memory out to RAM. The hot expert pool gets
rem whatever VRAM is still free. Start the voice FIRST. For tasks without the voice use brain-v40.bat.
rem Roll back: brain-v39.bat in D:\AI\llama-neira.
set NEIRA_PROBE=D:\AI\expert-map\probe16.json
set NEIRA_HOT_EXPERTS=D:\AI\llama-neira-hot\hot_experts.bin
rem keep 700 MiB free (not the default 2600 for games): the voice grows ~350 MiB after its first sentence (CUDA graphs)
set NEIRA_HOT_RESERVE_MIB=700
rem the real free VRAM (games and browsers included) before the brain loads: CUDA on Windows does not see them
for /f %%a in ('nvidia-smi --query-gpu^=memory.free --format^=csv^,noheader^,nounits') do set NEIRA_HOT_FREE_MIB=%%a
rem Лимит генерации (токенов за ответ): по умолчанию 16384; переопределяется через N_PREDICT
if not defined N_PREDICT set N_PREDICT=16384
cd /d D:\AI\expert-map
D:\AI\llama-neira-hot\llama-server.exe -m D:\AI\gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ^
  -ngl 99 --n-cpu-moe 99 -c 16384 --parallel 1 --context-shift -fa on -ctk q8_0 -ctv q8_0 ^
  --jinja --reasoning off -ub 512 -b 512 -n %N_PREDICT% ^
  --temp 0.7 --top-p 0.8 --top-k 20 --repeat-penalty 1.1 --spec-type draft-mtp --cache-ram 1024 ^
  --host 127.0.0.1 --port 8080 --alias brain
