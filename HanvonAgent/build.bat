@echo off
REM PyInstaller ile HanvonAgent.exe olustur
REM Kurulum: pip install pyinstaller

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   HanvonAgent - EXE Build Script
echo ========================================
echo.

REM Proje dizini
set PROJECT_DIR=%~dp0
set VENV_PYTHON=%PROJECT_DIR%venv\Scripts\python.exe

REM PyInstaller check
%VENV_PYTHON% -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [KURULUM] PyInstaller kuruluyor...
    %VENV_PYTHON% -m pip install -q pyinstaller
)

echo [OK] PyInstaller ready

REM Build
echo.
echo [BUILD] HanvonAgent.exe olusturuluyor...
echo.

cd /d "%PROJECT_DIR%"

%VENV_PYTHON% -m PyInstaller ^
    --clean ^
    "%PROJECT_DIR%HanvonAgent.spec"

if errorlevel 1 (
    echo [HATA] Build basarisiz
    pause
    exit /b 1
)

echo.
echo [OK] Build tamamlandi!
echo.
echo Dosya: %PROJECT_DIR%dist\HanvonAgent.exe
echo.
echo Kurulum gerekmez - calistiravabilirsin!
echo.

pause
