@echo off
rem Сборка Qt/QML клиента Нейры (после установки Qt в D:\Qt).
setlocal
set QT=D:\Qt\6.8.2\mingw_64
set SRC=D:\AI\neira-tools\qt_neira
set CXX=D:\Programs\w64devkit\bin\g++.exe
set MOC=%QT%\bin\moc.exe

if not exist "%QT%\bin\moc.exe" (
  echo Qt не найден: %QT%
  exit /b 1
)

"%MOC%" -I"%QT%\include" -I"%QT%\include\QtCore" "%SRC%\neira_brain.h" -o "%SRC%\moc_neira_brain.cpp"

"%CXX%" -std=c++17 -O2 -fPIC "%SRC%\main.cpp" "%SRC%\neira_brain.cpp" "%SRC%\moc_neira_brain.cpp" ^
  -o "%SRC%\neira_qt.exe" ^
  -I"%QT%\include" -I"%QT%\include\QtCore" -I"%QT%\include\QtGui" ^
  -I"%QT%\include\QtQml" -I"%QT%\include\QtQuick" -I"%QT%\include\QtQuickControls2" ^
  -L"%QT%\lib" -lQt6Core -lQt6Gui -lQt6Qml -lQt6Quick -lQt6QuickControls2 -lws2_32 -lwinmm -lcomdlg32 -mwindows

if errorlevel 1 (
  echo СБОРКА ОШИБКА
  exit /b 1
)
echo OK: %SRC%\neira_qt.exe
