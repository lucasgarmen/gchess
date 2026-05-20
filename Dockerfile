FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    STOCKFISH_PATH=/usr/local/bin/stockfish \
    PORT=10000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && if [ -x /usr/games/stockfish ]; then ln -sf /usr/games/stockfish /usr/local/bin/stockfish; elif [ -x /usr/bin/stockfish ]; then ln -sf /usr/bin/stockfish /usr/local/bin/stockfish; else echo "Stockfish binary was not installed"; exit 1; fi \
    && test -x /usr/local/bin/stockfish \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD command -v "$STOCKFISH_PATH" \
    && python manage.py collectstatic --no-input \
    && python manage.py migrate \
    && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT}
