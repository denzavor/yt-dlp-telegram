# AGENTS.md

## Project Overview

- This repository contains a small Telegram bot built around `pyTelegramBotAPI` and `yt-dlp`.
- Runtime entrypoint: `main.py`.
- Docker deployment: `docker-compose.yml`.
- Persistent runtime data lives in `./data` on the host and `/data` in the container.

## Important Runtime Files

- `config.py` is server-local and must never be committed.
- `data/db.db` stores encrypted per-user cookies.
- `data/*.txt` may contain shared cookie exports for the bot and must never be committed.

## Private Bot Notes

- Access control is configured through `allowed_usernames` in `config.py`.
- Shared authenticated downloads are configured through `shared_cookie_file` in `config.py`.
- `shared_cookie_file` should point to a file inside `/data`, for example `/data/instagram_cookies.txt`.
- If `allowed_usernames` is empty, the bot is public.

## Deployment Notes

- Toronto server path: `/opt/yt-dlp-telegram`.
- Deploy by pulling the current `origin/main` and running `docker compose up -d --build` inside `/opt/yt-dlp-telegram`.
- Preserve `config.py` and everything under `data/` across deploys.

## Verification

- Run tests with `python3 -m unittest discover -s tests -v`.
- When investigating auth failures, check both `data/db.db` and the configured `shared_cookie_file`.
