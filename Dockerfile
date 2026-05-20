FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STOCKFISH_PATH=/usr/games/stockfish \
    PORT=10000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && if [ -x /usr/games/stockfish ]; then ln -sf /usr/games/stockfish /usr/local/bin/stockfish; fi \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD python manage.py collectstatic --no-input \
    && python manage.py migrate \
    && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT}
