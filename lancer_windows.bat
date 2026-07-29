@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   NormaGrid - Installation et lancement
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
    echo.
    echo Cause frequente : sur certains PC, taper "python" ouvre le Microsoft
    echo Store au lieu de lancer Python -- ce qui veut dire que Python n'est
    echo pas reellement installe.
    echo.
    echo Solution : installez Python depuis https://www.python.org/downloads/
    echo IMPORTANT : cochez la case "Add python.exe to PATH" pendant
    echo l'installation, puis relancez ce script.
    echo.
    pause
    exit /b 1
)

echo Python detecte : %PYCMD%
echo.
echo Installation des dependances ^(Flask, pywebview^)...
%PYCMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERREUR: l'installation des dependances a echoue.
    echo Verifiez votre connexion internet, puis relancez ce script.
    pause
    exit /b 1
)

echo.
echo Verification qu'aucun ancien serveur n'occupe deja le port 5000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    echo Arret de l'ancien processus ^(PID %%a^)...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Demarrage de NormaGrid (fenetre native)...
echo Une fenetre d'application va s'ouvrir. Fermez-la pour quitter.
echo.

%PYCMD% desktop.py

echo.
echo NormaGrid s'est ferme.
pause
