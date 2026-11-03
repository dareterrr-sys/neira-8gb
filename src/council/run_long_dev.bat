@echo off
rem 31.10: the matching tasks 8 and 22 with 2500 tokens of thinking instead of 750 (dev, the same 10 tasks each as
rem nobook10/book10; with the textbook chapter).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
set ORGANS=words,units,russkiy
set PY=D:\AI\Open-LLM-VTuber\.venv\Scripts\python.exe
cd /d D:\AI\neira-tools\council
set EGE_TASKS=8,22
set EGE_BOOK=1
set EGE_ONE_THINK_LONG=2500
%PY% ege_exam.py dev long2500 10 > runs\ege_exam_dev_long2500.log 2>&1
echo done > runs\long_dev.done
