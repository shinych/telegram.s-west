# Deployment Guide

Step-by-step instructions for setting up and deploying the Band Name Voting Bot.

## 1. Create the bot via BotFather

1. Open Telegram, search for **@BotFather**, start a chat
2. Send `/newbot`
3. Follow the prompts — pick a display name and a username (must end in `bot`)
4. BotFather will reply with your **token** — looks like `7123456789:AAHx...`. Copy it.
5. Configure group privacy:
   - Send `/mybots` → select your bot → **Bot Settings** → **Group Privacy** → **Turn off**
6. Add the bot to your group as an **admin**

## 2. Get your chat ID and thread ID

1. Send any message in the group (in the specific topic/thread if your group uses forum mode)
2. Run this in your terminal (replace `<TOKEN>` with your actual token):

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool
```

3. In the JSON output, look for:
   - **`"chat": {"id": -100...}`** — that negative number is your `chat_id`
   - **`"message_thread_id": 123`** — that's your `thread_id` (only present if your group uses topics/forum mode; set to `null` in config if it doesn't)

## 3. Get your admin user ID

Send a message to **@userinfobot** on Telegram — it will reply with your numeric user ID. Put that in the `admin_user_ids` array.

## 4. Configure

```bash
cp config.example.json config.json
```

Edit `config.json` with your real values:

```json
{
  "bot_token": "7123456789:AAHxYourActualTokenHere",
  "chat_id": -1001234567890,
  "thread_id": null,
  "admin_user_ids": [your_user_id],
  "daily_poll_hour": 21,
  "daily_poll_minute": 0,
  "weekly_poll_day": "sun",
  "weekly_poll_hour": 20,
  "weekly_poll_minute": 0,
  "timezone": "Europe/Berlin"
}
```

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

## 5. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 6. Test run

```bash
python bot.py
```

Verify the bot responds to `/help` in your group, then stop it with Ctrl+C.

## 7. Deploy with systemd

Create the service file:

```bash
sudo nano /etc/systemd/system/band-name-bot.service
```

Paste this (adjust `User` and `WorkingDirectory` to match your setup):

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

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable band-name-bot    # start on boot
sudo systemctl start band-name-bot     # start now
```

Verify:

```bash
sudo systemctl status band-name-bot    # check status
sudo journalctl -u band-name-bot -f    # tail live logs
```

### Alternative: screen

If you don't have systemd or prefer a simpler approach:

```bash
screen -S bot
source venv/bin/activate
python bot.py
# Ctrl+A, D to detach
# screen -r bot to reattach
```

## Managing the service

| Command | What it does |
|---------|-------------|
| `sudo systemctl stop band-name-bot` | Stop the bot |
| `sudo systemctl restart band-name-bot` | Restart after code changes |
| `sudo systemctl status band-name-bot` | Check if running |
| `sudo journalctl -u band-name-bot -n 50` | Last 50 log lines |
| `sudo journalctl -u band-name-bot --since "1 hour ago"` | Recent logs |

## Troubleshooting

- **Bot doesn't respond to commands**: Make sure Group Privacy is turned off in BotFather settings, and the bot is a group admin.
- **Polls appear in wrong topic**: Check that `thread_id` in `config.json` matches the desired topic. Send a message in the topic and use `getUpdates` to verify.
- **"No suggestions" on /forcedaily**: All existing suggestions have been used. Submit new ones with `/suggest`.
- **Duplicate name rejected**: The bot checks all suggestions ever submitted (case-insensitive). This is intentional to prevent repeats.
- **`getUpdates` returns empty array**: Send a new message in the group after adding the bot, then try again.
