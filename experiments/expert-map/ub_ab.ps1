# Live brain with 512 vs 256 batches (28.10): VRAM taken and the reading speed of a ~2.9k-token prompt (cold, twice)
# plus writing speed, on port 8081 with the voice parked. Restarts the live brain on 8080 afterwards (with -ub $final).
param([int]$final = 0)
$py = "D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe"
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
curl.exe -s -X POST http://127.0.0.1:8090/park | Out-Null
Start-Sleep 3
foreach ($ub in 512, 256) {
    $free0 = [int](nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
    $env:NEIRA_HOT_EXPERTS = ""
    $a = "-m D:\AI\gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf -ngl 99 --n-cpu-moe 99 -c 16384 --parallel 1 " +
         "--context-shift -fa on -ctk q8_0 -ctv q8_0 --jinja -ub $ub -b $ub -n 8192 --spec-type draft-mtp " +
         "--host 127.0.0.1 --port 8081"
    $p = Start-Process D:\AI\llama-neira-hot\llama-server.exe -ArgumentList $a -WorkingDirectory D:\AI\expert-map `
         -RedirectStandardError "D:\AI\expert-map\ub_$ub.log" -RedirectStandardOutput "D:\AI\expert-map\ub_$ub.out" -PassThru -WindowStyle Hidden
    do { Start-Sleep 3 } until ((curl.exe -s -m 2 http://127.0.0.1:8081/health) -match "ok" -or $p.HasExited)
    $free1 = [int](nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
    "== -ub $ub : VRAM taken $($free0 - $free1) MiB"
    & $py D:\AI\expert-map\long_read.py 8081
    Stop-Process -Id $p.Id -Force
    Start-Sleep 3
}
if ($final) {
    (Get-Content D:\AI\llama-neira-hot\brain-v40-live.bat) -replace '-ub \d+ -b \d+', "-ub $final -b $final" |
        Set-Content -Encoding ascii D:\AI\llama-neira-hot\brain-v40-live.bat
}
Start-Process cmd.exe -ArgumentList '/c D:\AI\llama-neira-hot\brain-v40-live.bat > D:\AI\llama-neira-hot\brain_live.log 2>&1' -WindowStyle Minimized
do { Start-Sleep 3 } until ((curl.exe -s -m 2 http://127.0.0.1:8080/health) -match "ok")
curl.exe -s -X POST http://127.0.0.1:8090/unpark | Out-Null
"live brain back on 8080"
