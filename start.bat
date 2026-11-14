@echo off
REM Lance DocEdit (Windows). Double-cliquez sur ce fichier.
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python est introuvable. Installez-le depuis https://www.python.org/downloads/
  echo en cochant la case "Add python.exe to PATH", puis relancez ce fichier.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Premiere utilisation : preparation de DocEdit ^(1 a 3 minutes^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Impossible de creer l'environnement Python.
    pause
    exit /b 1
  )
)
if not exist ".venv\installe.txt" (
  echo Installation des composants necessaires...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
  if errorlevel 1 (
    echo Linstallation a echoue. Verifiez votre connexion Internet puis relancez.
    pause
    exit /b 1
  )
  echo ok> ".venv\installe.txt"
)
".venv\Scripts\python.exe" run.py
pause
