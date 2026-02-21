# Band Name Voting Bot

A Telegram bot that collects band name suggestions, runs daily polls, and holds a weekly championship with author reveals.

## Features

- `/suggest <name>` — anyone can submit a band name
- Daily polls at a configured time with all new suggestions
- Weekly championship poll with the top 5 names from the week
- Author reveal 48 hours after the weekly poll
- Forum/topic thread support
- Admin commands for managing suggestions and forcing polls

## Setup

### 1. Create the bot

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram
2. `/newbot` — follow the prompts, save the token
3. `/mybots` → your bot → **Bot Settings** → **Group Privacy** → **Turn off** (so the bot can read commands in groups)
4. Add the bot to your group as an **admin**

### 2. Find your `chat_id` and `thread_id`

Send a message in the group (in the desired topic if using forum mode), then run:

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | python3 -m json.tool
```

Look for `"chat": {"id": -100...}` — that's your `chat_id`.

If the group has topics enabled, look for `"message_thread_id"` — that's your `thread_id`.

### 3. Configure

```bash
cp config.example.json config.json
```

Edit `config.json` with your values:

| Key | Description |
|-----|-------------|
| `bot_token` | Token from BotFather |
| `chat_id` | Group chat ID (negative number) |
| `thread_id` | Topic thread ID, or `null` if not using topics |
| `admin_user_ids` | List of Telegram user IDs who can use admin commands |
| `daily_poll_hour/minute` | Time for daily polls (in configured timezone) |
| `weekly_poll_day` | Day for weekly poll (`mon`, `tue`, ..., `sun`) |
| `weekly_poll_hour/minute` | Time for weekly poll |
| `timezone` | Timezone string (e.g. `Europe/Berlin`) |

### 4. Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Run

```bash
python bot.py
```

## Commands

| Command | Access | Description |
|---------|--------|-------------|
| `/suggest <name>` | Anyone | Submit a band name suggestion |
| `/suggestions` | Admin | List all unused suggestions |
| `/results` | Anyone | Show this week's voting leaderboard |
| `/forcedaily` | Admin | Trigger a daily poll immediately |
| `/forceweekly` | Admin | Trigger a weekly poll immediately |
| `/help` | Anyone | Show usage help |

## Production Deployment (systemd)

Create `/etc/systemd/system/band-name-bot.service`:

```ini
[Unit]
Description=Band Name Voting Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/band-name-bot
ExecStart=/path/to/band-name-bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now band-name-bot
sudo journalctl -u band-name-bot -f   # view logs
```

### Alternative: screen

```bash
screen -S bot
source venv/bin/activate
python bot.py
# Ctrl+A, D to detach
# screen -r bot to reattach
```

## Troubleshooting

- **Bot doesn't respond to commands**: Make sure Group Privacy is turned off in BotFather settings, and the bot is a group admin.
- **Polls appear in wrong topic**: Check that `thread_id` in `config.json` matches the desired topic. Send a message in the topic and use `getUpdates` to verify.
- **"No suggestions" on /forcedaily**: All existing suggestions have been used. Submit new ones with `/suggest`.
- **Duplicate name rejected**: The bot checks all suggestions ever submitted (case-insensitive). This is intentional to prevent repeats.
