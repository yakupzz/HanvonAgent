@echo off
REM Windows Server 2016 / Windows 10 1607 icin HanvonAgent.exe olustur
REM Python 3.12 (tasinabilir NuGet paketi, sisteme kurulmaz) + PySide6 6.7.3
REM Neden ayri derleme: bkz. requirements-server2016.txt (BUG-020)
REM Cikti: dist\server2016\HanvonAgent.exe

setlocal

echo.
echo ========================================
echo   HanvonAgent - Server 2016 Build
echo ========================================
echo.

set PROJECT_DIR=%~dp0
set WORK=%PROJECT_DIR%.build-server2016
set PY_VERSION=3.12.10
set PY_DIR=%WORK%\python312
set PY_EXE=%PY_DIR%\tools\python.exe
set VENV=%WORK%\venv
set VENV_PYTHON=%VENV%\Scripts\python.exe

if not exist "%WORK%" mkdir "%WORK%"

REM 1. Tasinabilir Python 3.12 (yoksa NuGet'ten indir)
if not exist "%PY_EXE%" (
    echo [KURULUM] Python %PY_VERSION% ^(NuGet^) indiriliyor...
    powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://www.nuget.org/api/v2/package/python/%PY_VERSION%' -OutFile '%WORK%\python312.zip'"
    if errorlevel 1 goto :hata
    powershell -NoProfile -Command "Expand-Archive -Force '%WORK%\python312.zip' '%PY_DIR%'"
    if errorlevel 1 goto :hata
    del "%WORK%\python312.zip"
)
echo [OK] Python: %PY_EXE%

REM 2. Ayri sanal ortam + sabit bagimliliklar
if not exist "%VENV_PYTHON%" (
    echo [KURULUM] Sanal ortam olusturuluyor...
    "%PY_EXE%" -m venv "%VENV%"
    if errorlevel 1 goto :hata
)
echo [KURULUM] Bagimliliklar ^(requirements-server2016.txt^)...
"%VENV_PYTHON%" -m pip install -q -r "%PROJECT_DIR%requirements-server2016.txt"
if errorlevel 1 goto :hata
"%VENV_PYTHON%" -c "import sys, PySide6; print('[OK] Python', sys.version.split()[0], '/ PySide6', PySide6.__version__)"
if errorlevel 1 goto :hata

REM 3. Build
echo.
echo [BUILD] dist\server2016\HanvonAgent.exe olusturuluyor...
cd /d "%PROJECT_DIR%"
"%VENV_PYTHON%" -m PyInstaller --clean --noconfirm ^
    --distpath "%PROJECT_DIR%dist\server2016" ^
    --workpath "%PROJECT_DIR%build\server2016" ^
    "%PROJECT_DIR%HanvonAgent.spec"
if errorlevel 1 goto :hata

echo.
echo [OK] Build tamamlandi: %PROJECT_DIR%dist\server2016\HanvonAgent.exe
echo.
if not "%1"=="--no-pause" pause
exit /b 0

:hata
echo [HATA] Server 2016 build basarisiz
if not "%1"=="--no-pause" pause
exit /b 1
