@echo off
REM HanvonAgent Start Script
REM Exe'yi konsol penceresi göstermeden çalıştır

cd /d "%~dp0"

REM dist\HanvonAgent.exe varsa (production), onu çalıştır
if exist "..\dist\HanvonAgent.exe" (
    REM VBScript ile exe'yi gizli modda çalıştır
    cscript.exe "%~dp0run_hidden.vbs" "%~dp0..\dist\HanvonAgent.exe"
    exit /b %errorlevel%
)

REM Yoksa dev mode (Python)
echo Python yok kontrol ediliyor...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python yok!
    pause
    exit /b 1
)

REM venv check
if not exist "venv" (
    echo venv olusturuluyor...
    python -m venv venv
)

REM activate
call venv\Scripts\activate.bat

REM install
pip install -q -r requirements.txt 2>nul

REM Logs klasörü oluştur
if not exist "data\logs" (
    mkdir "data\logs"
)

REM run (GUI mode — terminal yok)
REM pythonw.exe ile çalıştır (console penceresiz)
pythonw.exe main.py

REM pythonw ile exit kodu alınamadığından, direkt çık
exit /b 0
