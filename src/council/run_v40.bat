@echo off
rem Council v4.0 on work3 and hard (29.10): without and with the calculator note before it. The voice is parked for
rem the run (the council needs the GPU) and comes back at the end.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set ORGANS=words,units,russkiy
set PY=D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe
cd /d D:\AI\neira-tools\council
curl -s -X POST http://127.0.0.1:8090/park
for %%C in (0 1) do (
  set COUNCIL_CALC=%%C
  set QSET=work3_questions.json
  call %PY% eval_brain.py runs\council_v40_work3_calc%%C.json council > runs\council_v40_work3_calc%%C.log 2>&1
  set QSET=hard_questions.json
  call %PY% eval_brain.py runs\council_v40_hard_calc%%C.json council > runs\council_v40_hard_calc%%C.log 2>&1
)
curl -s -X POST http://127.0.0.1:8090/unpark
echo done > runs\council_v40.done
