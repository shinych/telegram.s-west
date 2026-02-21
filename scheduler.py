"""APScheduler cron/date jobs for daily and weekly polls."""

import logging
from datetime import datetime, timedelta, timezone

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

import storage

logger = logging.getLogger(__name__)

# Telegram limits polls to 10 options
MAX_POLL_OPTIONS = 10


def thread_kwargs(config: dict) -> dict:
    """Return message_thread_id kwarg if the group uses topics."""
    tid = config.get("thread_id")
    return {"message_thread_id": tid} if tid else {}


# ---------------------------------------------------------------------------
# Daily poll
# ---------------------------------------------------------------------------

async def run_daily_poll(bot, config: dict):
    """Send daily poll(s) with unused suggestions."""
    unused = storage.get_unused_suggestions()
    if not unused:
        logger.info("Нет новых предложений для ежедневного голосования.")
        return

    chunks = [unused[i:i + MAX_POLL_OPTIONS]
              for i in range(0, len(unused), MAX_POLL_OPTIONS)]
    total_chunks = len(chunks)

    for idx, chunk in enumerate(chunks, 1):
        title = "🗳️ Ежедневное голосование"
        if total_chunks > 1:
            title += f" ({idx}/{total_chunks})"

        options = [s["name"] for s in chunk]

        msg = await bot.send_poll(
            chat_id=config["chat_id"],
            question=title,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=True,
            open_period=86400,  # 24 hours
            **thread_kwargs(config),
        )

        poll_options = [
            {
                "text": s["name"],
                "suggestion_id": s["id"],
                "voter_count": 0,
            }
            for s in chunk
        ]
        storage.save_poll(msg.poll.id, msg.message_id, poll_options, "daily")
        storage.mark_suggestions_used([s["id"] for s in chunk])

        logger.info("Ежедневный опрос отправлен: %s (%d вариантов)",
                     title, len(options))


# ---------------------------------------------------------------------------
# Weekly poll
# ---------------------------------------------------------------------------

async def run_weekly_poll(bot, config: dict, scheduler: AsyncIOScheduler):
    """Send weekly championship poll with top 5 names from the past week."""
    tz = pytz.timezone(config["timezone"])
    since = datetime.now(tz) - timedelta(days=7)
    since_utc = since.astimezone(timezone.utc)
    scores = storage.get_daily_scores_since(since_utc)

    if not scores:
        logger.info("Нет результатов ежедневных голосований за неделю.")
        return

    # Build list with suggestion details, sort by votes desc then recency
    ranked = []
    for sid, votes in scores.items():
        suggestion = storage.get_suggestion_by_id(sid)
        if suggestion:
            ranked.append({
                "suggestion_id": sid,
                "name": suggestion["name"],
                "author_id": suggestion["author_id"],
                "author_name": suggestion["author_name"],
                "votes": votes,
                "submitted_at": suggestion["submitted_at"],
            })

    ranked.sort(key=lambda x: (-x["votes"], x["submitted_at"]))
    top = ranked[:5]

    if not top:
        return

    options = [entry["name"] for entry in top]

    msg = await bot.send_poll(
        chat_id=config["chat_id"],
        question="🏆 Еженедельный чемпионат",
        options=options,
        is_anonymous=False,
        allows_multiple_answers=True,
        open_period=config.get("reveal_delay_hours", 6) * 3600,
        **thread_kwargs(config),
    )

    poll_options = [
        {
            "text": entry["name"],
            "suggestion_id": entry["suggestion_id"],
            "voter_count": 0,
        }
        for entry in top
    ]
    storage.save_poll(msg.poll.id, msg.message_id, poll_options, "weekly")

    # Save weekly result (revealed later)
    weekly_result = {
        "poll_id": msg.poll.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "top": top,
        "revealed": False,
    }
    storage.add_weekly_result(weekly_result)

    # Schedule author reveal
    reveal_hours = config.get("reveal_delay_hours", 6)
    reveal_time = datetime.now(tz) + timedelta(hours=reveal_hours)
    scheduler.add_job(
        run_author_reveal,
        trigger=DateTrigger(run_date=reveal_time, timezone=tz),
        args=[bot, config],
        id=f"reveal_{msg.poll.id}",
        replace_existing=True,
    )
    logger.info("Еженедельный опрос отправлен, ревил запланирован на %s",
                 reveal_time.isoformat())


# ---------------------------------------------------------------------------
# Author reveal
# ---------------------------------------------------------------------------

async def run_author_reveal(bot, config: dict):
    """Announce weekly results with author names revealed."""
    weekly = storage.get_latest_weekly()
    if not weekly or weekly.get("revealed"):
        return

    # Re-read poll results to get final vote counts
    poll = storage.get_poll(weekly["poll_id"])
    final_counts = {}
    if poll:
        for opt in poll["options"]:
            final_counts[opt["suggestion_id"]] = opt.get("voter_count", 0)

    lines = ["🎉 Результаты еженедельного чемпионата:\n"]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]

    for i, entry in enumerate(weekly["top"]):
        votes = final_counts.get(entry["suggestion_id"], entry["votes"])
        medal = medals[i] if i < len(medals) else f"{i+1}."
        lines.append(
            f"{medal} {entry['name']} — {votes} гол. "
            f"(автор: {entry['author_name']})"
        )

    await bot.send_message(
        chat_id=config["chat_id"],
        text="\n".join(lines),
        **thread_kwargs(config),
    )
    storage.mark_weekly_revealed()
    logger.info("Авторы еженедельного голосования раскрыты.")


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def create_scheduler(bot, config: dict) -> AsyncIOScheduler:
    """Create and return an AsyncIOScheduler with daily & weekly cron jobs."""
    tz = pytz.timezone(config["timezone"])
    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(
        run_daily_poll,
        trigger=CronTrigger(
            hour=config["daily_poll_hour"],
            minute=config["daily_poll_minute"],
            timezone=tz,
        ),
        args=[bot, config],
        id="daily_poll",
        replace_existing=True,
    )

    scheduler.add_job(
        run_weekly_poll,
        trigger=CronTrigger(
            day_of_week=config["weekly_poll_day"],
            hour=config["weekly_poll_hour"],
            minute=config["weekly_poll_minute"],
            timezone=tz,
        ),
        args=[bot, config, scheduler],
        id="weekly_poll",
        replace_existing=True,
    )

    return scheduler
