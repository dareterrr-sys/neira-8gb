@echo off
setlocal
rem ============================================================
rem  Neira-auto.bat - autonomous (headless) OpenCode runner
rem  Uses: opencode-cli run ... --auto
rem  Permissions are auto-approved except explicitly denied ones
rem  in ~/.config/opencode/opencode.json (permissions block).
rem ============================================================
set CLI=D:\AppData1\ai.opencode.desktop\cli\2.1.4-x64\opencode-cli.exe

if not exist "%CLI%" (
  echo ERROR: CLI not found: %CLI%
  exit /b 1
)

rem --- Interactive mode when no task given (double-click) ---
if "%~1"=="" (
  set "TASK="
  set /p TASK=Enter task for the agent: 
  if not defined TASK (
    echo No task entered. Exiting.
    exit /b 1
  )
  "%CLI%" run "%TASK%" --auto
  exit /b %errorlevel%
)

rem --- Command-line mode: pass all arguments through ---
"%CLI%" run %* --auto
exit /b %errorlevel%
