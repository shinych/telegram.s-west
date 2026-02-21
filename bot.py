"""Telegram Band Name Voting Bot — main entry point."""

import json
import logging
import random
import sys
from datetime import datetime, timedelta, timezone

import pytz
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
    PollHandler,
)

import storage
from scheduler import (
    create_scheduler,
    run_daily_poll,
    run_weekly_poll,
    thread_kwargs,
)

logger = logging.getLogger(__name__)

# Global references set at startup
CONFIG: dict = {}
SCHEDULER = None

# Load sarcastic thank-you lines
with open("thanks.txt", "r", encoding="utf-8") as _f:
    THANKS_LINES = [line.strip() for line in _f if line.strip()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_admin(user_id: int) -> bool:
    return user_id in CONFIG.get("admin_user_ids", [])


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_suggest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /suggest <name>."""
    if not context.args:
        await update.effective_message.reply_text(
            "✏️ Использование: /suggest <название группы>")
        return

    name = " ".join(context.args).strip()
    if not name:
        await update.effective_message.reply_text("🫥 Название не может быть пустым.")
        return

    user = update.effective_user
    result = storage.add_suggestion(name, user.id, user.first_name)

    if result is None:
        await update.effective_message.reply_text(
            f"🔁 Название \"{name}\" уже было предложено.")
    else:
        thanks = random.choice(THANKS_LINES)
        await update.effective_message.reply_text(
            f"🤘 Принято: \"{name}\"\n\n{thanks}")


async def cmd_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /suggestions — admin only, show pending suggestions."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return

    unused = storage.get_unused_suggestions()
    if not unused:
        await update.effective_message.reply_text("📭 Нет неиспользованных предложений.")
        return

    lines = ["📋 Неиспользованные предложения:\n"]
    for i, s in enumerate(unused, 1):
        lines.append(f"{i}. {s['name']} (от {s['author_name']})")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete <number> — admin only, delete an unused suggestion by number."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "✏️ Использование: /delete <номер>\n"
            "Номер из списка /suggestions.")
        return

    index = int(context.args[0])
    removed = storage.delete_suggestion(index)

    if removed is None:
        await update.effective_message.reply_text(
            f"❌ Предложение с номером {index} не найдено.")
    else:
        await update.effective_message.reply_text(
            f"🗑️ Удалено: \"{removed['name']}\" (от {removed['author_name']}).")


async def cmd_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /results — show current week's aggregated leaderboard."""
    tz = pytz.timezone(CONFIG["timezone"])
    since = datetime.now(tz) - timedelta(days=7)
    since_utc = since.astimezone(timezone.utc)
    scores = storage.get_daily_scores_since(since_utc)

    if not scores:
        await update.effective_message.reply_text(
            "😶 Нет результатов голосований за эту неделю.")
        return

    ranked = []
    for sid, votes in scores.items():
        suggestion = storage.get_suggestion_by_id(sid)
        if suggestion:
            ranked.append((suggestion["name"], votes))
    ranked.sort(key=lambda x: -x[1])

    lines = ["📊 Результаты за неделю:\n"]
    for i, (name, votes) in enumerate(ranked, 1):
        lines.append(f"{i}. {name} — {votes} гол.")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_forcedaily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forcedaily — admin only, trigger daily poll now."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return
    await update.effective_message.reply_text("⚡ Запускаю ежедневное голосование...")
    await run_daily_poll(context.bot, CONFIG)


async def cmd_forceweekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forceweekly — admin only, trigger weekly poll now."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return
    await update.effective_message.reply_text("⚡ Запускаю еженедельное голосование...")
    await run_weekly_poll(context.bot, CONFIG, SCHEDULER)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    text = (
        "🎸 Ладно, раз уж вы спросили.\n\n"
        "🤘 /suggest <название> — предложить название группы. "
        "Да, ещё одно. Мы верим в вас.\n"
        "📊 /results — посмотреть, кто побеждает. Спойлер: не ваш вариант.\n"
        "📖 /about — как вообще всё это работает (если вам правда интересно)\n"
        "❓ /help — вы сейчас здесь. Поздравляем.\n\n"
        "🔒 Только для админов (вы, скорее всего, не админ):\n"
        "📋 /suggestions — список предложений в очереди\n"
        "🗑️ /delete <номер> — удалить предложение\n"
        "⚡ /forcedaily — запустить ежедневное голосование вручную\n"
        "⚡ /forceweekly — запустить еженедельное голосование вручную"
    )
    await update.effective_message.reply_text(text)


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about and /start — explain how the bot works."""
    text = (
        "🎤 Итак. Вы в группе, которая не может выбрать себе название. "
        "Бывает. Для этого я здесь.\n\n"
        "Как это работает:\n\n"
        "1️⃣ Вы придумываете гениальное название и пишете /suggest. "
        "Бот делает вид, что впечатлён.\n\n"
        "2️⃣ Каждый день бот запускает голосование из накопившихся предложений. "
        "Демократия в действии, да.\n\n"
        "3️⃣ В конце недели — чемпионат: топ-5 названий по итогам "
        "ежедневных голосований сражаются в финале. 🏆\n\n"
        "4️⃣ Через 48 часов после финала бот раскрывает авторов. "
        "Чтобы вы знали, кого благодарить. Или винить. 🕵️\n\n"
        "Вот и всё. Пишите /help, если хотите список команд."
    )
    await update.effective_message.reply_text(text)


# ---------------------------------------------------------------------------
# Poll answer tracking (non-anonymous polls)
# ---------------------------------------------------------------------------

# Track previous answers per (user_id, poll_id) to compute deltas
_previous_answers: dict[tuple[int, str], list[int]] = {}


async def on_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track votes in real time via PollAnswer updates."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    new_options = answer.option_ids  # list of selected option indices

    key = (user_id, poll_id)
    old_options = _previous_answers.get(key, [])

    # Retracted options: were selected, now aren't
    retracted = [o for o in old_options if o not in new_options]
    # Added options: weren't selected, now are
    added = [o for o in new_options if o not in old_options]

    if retracted:
        storage.update_poll_voter_counts(poll_id, retracted, -1)
    if added:
        storage.update_poll_voter_counts(poll_id, added, +1)

    if new_options:
        _previous_answers[key] = list(new_options)
    else:
        _previous_answers.pop(key, None)

    logger.debug("PollAnswer: user=%d poll=%s added=%s retracted=%s",
                 user_id, poll_id, added, retracted)


async def on_poll_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Poll updates (e.g. when a poll is closed)."""
    poll = update.poll
    if poll.is_closed:
        counts = [opt.voter_count for opt in poll.options]
        storage.set_poll_option_counts(poll.id, counts)
        storage.close_poll(poll.id)
        logger.info("Опрос %s закрыт, финальные результаты сохранены.", poll.id)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global CONFIG, SCHEDULER

    # Load config
    with open("config.json", "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("bot.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )

    logger.info("Запуск бота...")

    # Build application
    app = Application.builder().token(CONFIG["bot_token"]).build()

    # Register handlers
    app.add_handler(CommandHandler("suggest", cmd_suggest))
    app.add_handler(CommandHandler("suggestions", cmd_suggestions))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("results", cmd_results))
    app.add_handler(CommandHandler("forcedaily", cmd_forcedaily))
    app.add_handler(CommandHandler("forceweekly", cmd_forceweekly))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("start", cmd_about))
    app.add_handler(PollAnswerHandler(on_poll_answer))
    app.add_handler(PollHandler(on_poll_update))

    # Start scheduler
    SCHEDULER = create_scheduler(app.bot, CONFIG)
    SCHEDULER.start()
    logger.info("Планировщик запущен.")

    # Run
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
