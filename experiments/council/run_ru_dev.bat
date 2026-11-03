@echo off
rem 31.10 (the author's idea): thinking begun in Russian + a growing budget 750 -> 2000 -> time is up; no textbook.
rem The same dev tasks as nobook10 / long2500 (numbers 8 and 22, 10 each).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
set ORGANS=words,units,russkiy
set PY=D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe
cd /d D:\AI\neira-tools\council
:wait
if not exist runs\long_dev.done (timeout /t 10 /nobreak >nul & goto wait)
set EGE_TASKS=8,22
set EGE_BOOK=0
set EGE_THINK_RU=1
set EGE_BUDGETS=750,2000
%PY% ege_exam.py dev ru750_2000 10 > runs\ege_exam_dev_ru750_2000.log 2>&1
echo done > runs\ru_dev.done
