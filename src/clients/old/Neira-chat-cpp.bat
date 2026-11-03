@echo off
rem Neira-chat-cpp.bat — запуск чата Нейры. Если есть Windows Terminal — открывает в нём
rem (эмодзи и юникод отображаются корректно), иначе — в обычной консоли.
set "INNER=D:\AI\Neira-chat-cpp-inner.bat"
where wt.exe >nul 2>&1
if not errorlevel 1 (
    start "" wt.exe new-tab --title "Нейра" cmd /c "%INNER%"
    exit /b
)
call "%INNER%"
