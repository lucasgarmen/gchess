#!/usr/bin/env bash
set -o errexit

echo "Installing system dependencies..."
if command -v apt-get >/dev/null 2>&1; then
    if apt-get update && apt-get install -y stockfish; then
        echo "Stockfish installed successfully."
    else
        echo "ERROR: Stockfish could not be installed with apt-get."
        exit 1
    fi
else
    echo "ERROR: apt-get is not available. Cannot install Stockfish."
    exit 1
fi

if [ -x "/usr/games/stockfish" ]; then
    echo "Stockfish binary found at /usr/games/stockfish."
elif [ -x "/usr/bin/stockfish" ]; then
    echo "Stockfish binary found at /usr/bin/stockfish."
elif command -v stockfish >/dev/null 2>&1; then
    echo "Stockfish binary found at $(command -v stockfish)."
else
    echo "ERROR: Stockfish binary was not found after install step."
    exit 1
fi

echo "Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Running database migrations..."
python manage.py migrate
