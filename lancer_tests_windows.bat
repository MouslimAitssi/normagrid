@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   NormaGrid - Suite de tests automatiques
echo ============================================
echo.

set PYCMD=
for %%P in (python py) do (
    if "!PYCMD!"=="" (
        %%P --version >nul 2>&1
        if not errorlevel 1 (
            for /f "delims=" %%v in ('%%P --version 2^>^&1') do set VEROUT=%%v
            echo !VEROUT! | findstr /i "Python" >nul
            if not errorlevel 1 set PYCMD=%%P
        )
    )
)

if "%PYCMD%"=="" (
    echo ERREUR: Python n'a pas ete trouve sur ce PC.
    echo Installez Python depuis https://www.python.org/downloads/
    echo IMPORTANT : cochez la case "Add python.exe to PATH" pendant l'installation.
    echo.
    pause
    exit /b 1
)

echo Python detecte : %PYCMD%
echo.
echo Installation de Playwright (necessaire uniquement pour les tests)...
%PYCMD% -m pip install playwright
if errorlevel 1 (
    echo.
    echo ERREUR: l'installation de Playwright a echoue.
    echo Verifiez votre connexion internet, puis relancez ce script.
    pause
    exit /b 1
)

echo.
echo Installation du navigateur Chromium pour les tests (peut prendre 1-2 minutes)...
%PYCMD% -m playwright install chromium
if errorlevel 1 (
    echo.
    echo ERREUR: l'installation de Chromium a echoue.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Lancement de la suite de tests
echo ============================================
echo.

set CANECO_ARG=
if not "%~1"=="" (
    echo Fichier Caneco fourni : %~1
    set CANECO_ARG=--caneco-pdf "%~1"
) else (
    echo Astuce : vous pouvez glisser-deposer un fichier PDF Caneco sur ce
    echo script pour tester aussi l'import Caneco. Sans fichier, ce test
    echo sera simplement ignore ^(SKIP^), le reste de la suite s'execute quand meme.
)
echo.

%PYCMD% test_normagrid_e2e.py %CANECO_ARG%

echo.
echo ============================================
echo   Tests termines - voir le rapport ci-dessus
echo ============================================
pause
