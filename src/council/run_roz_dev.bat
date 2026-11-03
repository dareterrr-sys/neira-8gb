@echo off
rem 31.10: Russian staged thinking (750 -> 2000) + the original textbook: Rozental's points about the kinds the task
rem names (knowledge/rozental.py). The same dev tasks (numbers 8 and 22, 10 each).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
set ORGANS=words,units,russkiy
set PY=D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe
cd /d D:\AI\neira-tools\council
:wait
if not exist runs\ru_dev.done (timeout /t 10 /nobreak >nul & goto wait)
set EGE_TASKS=8,22
set EGE_BOOK=roz
set EGE_THINK_RU=1
set EGE_BUDGETS=750,2000
%PY% ege_exam.py dev roz_ru 10 > runs\ege_exam_dev_roz_ru.log 2>&1
echo done > runs\roz_dev.done
