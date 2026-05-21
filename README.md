# GChess

GChess is a Django chess web app built as a portfolio project. It supports local accounts, online games, invitations, ratings, chat, clocks, PGN analysis, and play against a Stockfish-powered bot.

## Features

- User registration, login, and player profiles.
- Online chess games between registered users.
- Direct, random, and shareable-link invitations.
- Server-side move validation with `python-chess`.
- Elo updates for finished multiplayer games.
- Draw offers, resignation, clocks, and timeout handling.
- In-game chat with unread counters.
- PGN/internal move analyzer with Stockfish feedback.
- Bot games with configurable Elo levels.
- Trainer chat and coach comments for played moves.

## Tech Stack

- Python 3
- Django 6
- SQLite for local development
- PostgreSQL for production through `DATABASE_URL`
- python-chess / chess
- Stockfish
- WhiteNoise for static files
- Gunicorn for production serving
- Render for deployment

## Screenshots

Add screenshots here before publishing the portfolio page:

- Home / dashboard
- Game board
- Invitation flow
- PGN analyzer
- Bot or trainer view

## Local Setup

Create a virtual environment and install dependencies:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create your `.env` file from the example:

```bash
copy .env.example .env
```

Set at least:

```env
DJANGO_SECRET_KEY=your-local-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=
DATABASE_URL=
DJANGO_SECURE_SSL_REDIRECT=False
STOCKFISH_PATH=C:\Users\lucas\Downloads\stockfish-windows-x86-64-avx2\stockfish\stockfish-windows-x86-64-avx2.exe
EMAIL_BACKEND=
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=GChess <noreply@example.com>
```

Run migrations and start the app:

```bash
python manage.py migrate
python manage.py runserver
```

Run checks and tests:

```bash
python manage.py check
python manage.py test
```

## Environment Variables

- `DJANGO_SECRET_KEY`: required. Use a long random value in production.
- `DJANGO_DEBUG`: `False` in production.
- `DJANGO_ALLOWED_HOSTS`: comma-separated hosts, for example `gchess.onrender.com`.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: comma-separated HTTPS origins, for example `https://gchess.onrender.com`.
- `DATABASE_URL`: PostgreSQL URL in production. If empty, local SQLite is used.
- `STOCKFISH_PATH`: path to the Stockfish executable.
- `EMAIL_BACKEND`: optional email backend override. Leave empty to use SMTP when `EMAIL_HOST` is set, or console email when it is not.
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`: SMTP server settings for password recovery emails.
- `EMAIL_USE_TLS`, `EMAIL_USE_SSL`: SMTP security settings.
- `DEFAULT_FROM_EMAIL`: sender address used by password recovery emails.
- `DJANGO_SECURE_SSL_REDIRECT`: use `True` in production on Render.
- `DJANGO_SECURE_HSTS_SECONDS`: optional, defaults to `31536000` when `DEBUG=False`.

## Stockfish

Local development:

1. Download Stockfish for your OS.
2. Put the executable somewhere stable.
3. Set `STOCKFISH_PATH` in `.env`.

Render:

- `build.sh` tries to install Stockfish with `apt-get`.
- Set `STOCKFISH_PATH=/usr/games/stockfish` in Render when using the apt package.
- If Stockfish is not installed or the path is wrong, bot/analysis endpoints return a clear JSON error instead of crashing the app.
- If Render cannot install the package, deploy still continues; engine features stay unavailable until `STOCKFISH_PATH` points to a real binary.

## Deploy on Render

Create a Render Web Service connected to this repository.

Build command:

```bash
bash build.sh
```

Start command:

```bash
gunicorn config.wsgi:application
```

The included `Procfile` also defines:

```bash
web: gunicorn config.wsgi:application
```

Recommended Render environment variables:

```env
DJANGO_SECRET_KEY=your-production-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-service-name.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-service-name.onrender.com
DATABASE_URL=postgres://...
DJANGO_SECURE_SSL_REDIRECT=True
STOCKFISH_PATH=/usr/games/stockfish
```

`build.sh` runs:

```bash
apt-get update
apt-get install -y stockfish
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
```

## Project Status

Portfolio-ready production preparation is in progress. The core game logic is preserved, and recent hardening focuses on deployment configuration, server-side validation, invitation safety, and regression tests.

## Next Improvements

- Add polished screenshots and a short demo video.
- Add persistent background job support if analysis grows slower.
- Improve real-time multiplayer with WebSockets.
- Add more chess rule regression tests.
- Package Stockfish installation more cleanly for production.
- Add CI for `manage.py check` and `manage.py test`.
