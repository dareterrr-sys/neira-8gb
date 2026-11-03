@echo off
rem Opens Neira's app window (Edge --app) once her server answers on 12393 - started by Neira-start.bat before the
rem server itself, which would otherwise show "page not available" (29.10)
:wait
curl -s -o nul http://localhost:12393 || (timeout /t 2 /nobreak >nul & goto wait)
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app=http://localhost:12393 --window-size=1280,800
