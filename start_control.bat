@echo off
setlocal
set "PYW=C:\Users\ofera\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
if not exist "%PYW%" set "PYW=C:\Users\ofera\AppData\Local\Python\bin\pythonw.exe"

cd /d "%~dp0"
start "" "%PYW%" -m control.app

timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8787"

endlocal
