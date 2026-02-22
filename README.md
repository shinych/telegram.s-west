# Arkestrabot

A Telegram bot that collects band name suggestions, runs daily polls, and holds a weekly championship with author reveals.

## Features

- `/suggest <name>` — anyone can submit a band name
- Daily polls at a configured time with all new suggestions
- Weekly championship poll with the top 5 names from the week
- Author reveal 48 hours after the weekly poll
- Forum/topic thread support
- Admin commands for managing suggestions and forcing polls

## Quick Start

```bash
cp config.example.json config.json   # edit with your values
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

See **[DEPLOY.md](DEPLOY.md)** for the full setup guide — creating the bot, getting your chat ID, configuring systemd, and troubleshooting.

## Commands

| Command | Access | Description |
|---------|--------|-------------|
| `/suggest <name>` | Anyone | Submit a band name suggestion |
| `/suggestions` | Admin | List all unused suggestions |
| `/results` | Anyone | Show this week's voting leaderboard |
| `/forcedaily` | Admin | Trigger a daily poll immediately |
| `/forceweekly` | Admin | Trigger a weekly poll immediately |
| `/help` | Anyone | Show usage help |

