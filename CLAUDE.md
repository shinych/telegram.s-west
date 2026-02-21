# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot for band name voting. Users suggest names via `/suggest`, the bot runs daily polls with those names, then a weekly championship with the top 5. Authors are revealed 48 hours after the weekly poll.

All UI text is in **Russian**.

## Running

```bash
source venv/bin/activate
python bot.py
```

No test suite or linter is configured.

## Architecture

Three Python modules, no frameworks beyond `python-telegram-bot` and `APScheduler`:

- **bot.py** — Entry point. Loads config, registers Telegram command/poll handlers, starts the scheduler, runs polling. All command handlers (`/suggest`, `/results`, `/forcedaily`, etc.) live here. Tracks real-time vote deltas via `PollAnswer` updates in an in-memory dict `_previous_answers`.
- **scheduler.py** — APScheduler cron jobs for daily and weekly polls, plus the one-shot author reveal job. `create_scheduler()` wires up the cron triggers using config timezone/times. `run_daily_poll` splits suggestions into chunks of 10 (Telegram poll limit). `run_weekly_poll` picks the top 5 by aggregated daily votes and schedules a `DateTrigger` reveal 48h later.
- **storage.py** — All persistence via flat JSON files (`suggestions.json`, `poll_results.json`, `weekly_results.json`). Writes are atomic (write to `.tmp`, then `os.replace`). No database. Every read re-loads the full file; every write re-saves the full file.

## Key Data Flow

1. `/suggest` → `storage.add_suggestion()` → appends to `suggestions.json` (deduped case-insensitively)
2. Daily cron → `run_daily_poll()` → sends Telegram poll(s), saves poll record to `poll_results.json`, marks suggestions as used
3. `PollAnswer` updates → `on_poll_answer()` → incremental vote count updates in `poll_results.json`
4. Weekly cron → `run_weekly_poll()` → aggregates daily scores from last 7 days, sends championship poll, saves to `weekly_results.json`, schedules reveal
5. Reveal job → `run_author_reveal()` → posts results with author names, marks revealed

## Config

`config.json` (gitignored) — see `config.example.json` for schema. Key fields: `bot_token`, `chat_id`, `thread_id` (nullable, for forum topics), `admin_user_ids`, timezone, and cron schedule settings.

## Files to Never Commit

`config.json`, `token.txt`, and the `*.json` data files are gitignored. They contain secrets or runtime state.
