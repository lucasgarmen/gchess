#!/usr/bin/env bash
set -o errexit

echo "Installing system dependencies..."
if command -v apt-get >/dev/null 2>&1; then
    if apt-get update && apt-get install -y stockfish; then
        echo "Stockfish installed successfully."
    else
        echo "WARNING: Stockfish could not be installed with apt-get. Deploy will continue."
        echo "WARNING: Set STOCKFISH_PATH to an existing Stockfish binary before using engine features."
    fi
else
    echo "WARNING: apt-get is not available. Skipping Stockfish system install."
fi

if [ -x "/usr/games/stockfish" ]; then
    echo "Stockfish binary found at /usr/games/stockfish."
elif command -v stockfish >/dev/null 2>&1; then
    echo "Stockfish binary found at $(command -v stockfish)."
else
    echo "WARNING: Stockfish binary was not found after install step."
fi

echo "Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Running database migrations..."
python manage.py migrate
