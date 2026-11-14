#!/usr/bin/env bash
# Lance DocEdit (Mac / Linux). Double-cliquez ou tapez : ./start.sh
cd "$(dirname "$0")" || exit 1

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3 est introuvable. Installez-le depuis https://www.python.org/downloads/ puis relancez ce script."
  read -r -p "Appuyez sur Entrée pour fermer..." _; exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Première utilisation : préparation de DocEdit (1 à 3 minutes)..."
  "$PY" -m venv .venv || { echo "Impossible de créer l'environnement Python."; read -r -p "Entrée pour fermer..." _; exit 1; }
fi

if [ ! -f ".venv/.installe" ] || [ requirements.txt -nt ".venv/.installe" ]; then
  echo "Installation des composants nécessaires..."
  .venv/bin/python -m pip install --upgrade pip --quiet --disable-pip-version-check
  if .venv/bin/python -m pip install -r requirements.txt --quiet --disable-pip-version-check; then
    touch .venv/.installe
  else
    echo "L'installation a échoué. Vérifiez votre connexion Internet puis relancez."
    read -r -p "Appuyez sur Entrée pour fermer..." _; exit 1
  fi
fi

exec .venv/bin/python run.py "$@"
