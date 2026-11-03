@echo off
rem Neira's textbook (31.10). 1) the sealed variant B without the textbook - the baseline of the live scheme, like
rem variant A. 2) dev: the brain's numbers 8, 22, 23, 24, 26, 10 tasks each from half A of razbor, the same tasks
rem without (EGE_BOOK=0) and with the chapter (EGE_BOOK=1).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
set ORGANS=words,units,russkiy
set PY=D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe
cd /d D:\AI\neira-tools\council
set EGE_BOOK=0
%PY% ege_exam.py D:\AI\datasets\ege_sealed\claude_B.json base > runs\sealed_B_base.log 2>&1
set EGE_TASKS=8,22,23,24,26
%PY% ege_exam.py dev nobook10 10 > runs\ege_exam_dev_nobook10.log 2>&1
set EGE_BOOK=1
%PY% ege_exam.py dev book10 10 > runs\ege_exam_dev_book10.log 2>&1
echo done > runs\book_dev.done
