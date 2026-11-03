@echo off
rem Neira-qt.bat — запуск Qt/QML клиента (v4).
set QT=D:\Qt\6.8.2\mingw_64
set PATH=%QT%\bin;%PATH%
set QML2_IMPORT_PATH=%QT%\qml
set QT_QPA_PLATFORM_PLUGIN_PATH=%QT%\plugins\platforms
start "" "D:\AI\neira-tools\qt_neira\neira_qt.exe"
