"""Arkestrabot — main entry point."""

import json
import logging
import random
import sys
from datetime import datetime, timedelta, timezone

import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PollAnswerHandler,
    PollHandler,
    filters,
)

import storage
from scheduler import (
    create_scheduler,
    run_daily_poll,
    run_daily_prompt,
    run_weekly_poll,
    thread_kwargs,
)

logger = logging.getLogger(__name__)

# Global references set at startup
CONFIG: dict = {}
SCHEDULER = None

# Load sarcastic thank-you lines
with open("assets/thanks.txt", "r", encoding="utf-8") as _f:
    THANKS_LINES = [line.strip() for line in _f if line.strip()]

# Load daily prompt lines
with open("assets/daily_prompts.txt", "r", encoding="utf-8") as _f:
    PROMPT_LINES = [line.strip() for line in _f if line.strip()]

# ConversationHandler states
AWAITING_BAND_NAME = 0


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
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✏️ Предложить название",
                url=f"https://t.me/{CONFIG['bot_username']}?start=suggest",
            )
        ]])
        await update.effective_message.reply_text(
            "✏️ Нажми кнопку — напишешь название в личке боту.\n"
            "Или: /suggest <название> прямо здесь.",
            reply_markup=keyboard,
        )
        return

    name = " ".join(context.args).strip()
    if not name:
        await update.effective_message.reply_text("🫥 Название не может быть пустым.")
        return

    if len(name) > 100:
        await update.effective_message.reply_text(
            f"🚫 Слишком длинное название ({len(name)} символов). "
            "Telegram ограничивает варианты в опросе до 100 символов.")
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


def format_results(config: dict) -> str | None:
    """Build results text (current week + past championships), filtering 0-vote entries.

    Returns the formatted string or None if there are no results.
    """
    tz = pytz.timezone(config["timezone"])
    weekly_results = storage.get_all_weekly_results()
    medals = ["🥇", "🥈", "🥉"]

    # --- Current week section ---
    if weekly_results:
        latest_created = datetime.fromisoformat(weekly_results[0]["created_at"])
        since_utc = latest_created
    else:
        since = datetime.now(tz) - timedelta(days=7)
        since_utc = since.astimezone(timezone.utc)

    scores = storage.get_daily_scores_since(since_utc)
    sections = []

    if scores:
        now = datetime.now(tz)
        since_local = since_utc.astimezone(tz) if weekly_results else (now - timedelta(days=7))
        date_from = since_local.strftime("%-d %b").lower()
        date_to = now.strftime("%-d %b").lower()
        ranked = []
        for sid, votes in scores.items():
            if votes <= 0:
                continue
            suggestion = storage.get_suggestion_by_id(sid)
            if suggestion:
                ranked.append((suggestion["name"], votes))
        ranked.sort(key=lambda x: -x[1])
        if ranked:
            lines = [f"📊 Текущая неделя ({date_from} — {date_to}):\n"]
            for i, (name, votes) in enumerate(ranked, 1):
                lines.append(f"{i}. {name} — {votes} гол.")
            sections.append("\n".join(lines))

    # --- Past weekly championships ---
    for weekly in weekly_results:
        poll = storage.get_poll(weekly["poll_id"])
        final_counts = {}
        if poll:
            for opt in poll["options"]:
                final_counts[opt["suggestion_id"]] = opt.get("voter_count", 0)

        created = datetime.fromisoformat(weekly["created_at"]).astimezone(tz)
        week_start = (created - timedelta(days=7)).strftime("%-d %b").lower()
        week_end = created.strftime("%-d %b").lower()

        ranked_top = sorted(
            weekly["top"],
            key=lambda e: final_counts.get(e["suggestion_id"], e["votes"]),
            reverse=True,
        )
        ranked_top = [
            e for e in ranked_top
            if final_counts.get(e["suggestion_id"], e["votes"]) > 0
        ]
        if not ranked_top:
            continue
        lines = [f"🏆 Неделя {week_start} — {week_end}:\n"]
        for i, entry in enumerate(ranked_top):
            votes = final_counts.get(entry["suggestion_id"], entry["votes"])
            medal = medals[i] if i < len(medals) else f"{i+1}."
            name = entry["name"]
            if weekly.get("revealed"):
                name += f" (автор: {entry['author_name']})"
            lines.append(f"{medal} {name} — {votes} гол.")
        sections.append("\n".join(lines))

    if not sections:
        return None
    return "\n\n".join(sections)


async def cmd_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /results — current week standings + past weekly championships."""
    text = format_results(CONFIG)
    if not text:
        await update.effective_message.reply_text(
            "😶 Нет результатов голосований за эту неделю.")
        return
    await update.effective_message.reply_text(text)


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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start in private chat — deep link entry for suggest flow."""
    user = update.effective_user
    storage.add_subscriber(user.id, user.first_name)

    if context.args and context.args[0] == "suggest":
        await update.effective_message.reply_text(
            "✏️ Напиши название группы. Просто текстом. Без команд.")
        return AWAITING_BAND_NAME

    await cmd_about(update, context)
    return ConversationHandler.END


async def receive_band_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive a band name in private chat (ConversationHandler state)."""
    name = update.message.text.strip()
    if not name:
        await update.effective_message.reply_text("🫥 Пустое название? Попробуй ещё раз.")
        return AWAITING_BAND_NAME

    if len(name) > 100:
        await update.effective_message.reply_text(
            f"🚫 Слишком длинное ({len(name)} символов). "
            "Максимум 100. Попробуй короче.")
        return AWAITING_BAND_NAME

    user = update.effective_user
    result = storage.add_suggestion(name, user.id, user.first_name)

    if result is None:
        await update.effective_message.reply_text(
            f"🔁 \"{name}\" уже предложено. Попробуй другое.")
        return AWAITING_BAND_NAME

    thanks = random.choice(THANKS_LINES)
    await update.effective_message.reply_text(
        f"🤘 Принято: \"{name}\"\n\n{thanks}")
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    await update.effective_message.reply_text("🚪 Ладно, в другой раз.")
    return ConversationHandler.END


async def cmd_forceprompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forceprompt — admin only, trigger daily prompt now."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return
    await update.effective_message.reply_text("⚡ Отправляю промпт...")
    await run_daily_prompt(context.bot, CONFIG, PROMPT_LINES)


async def cmd_close_polls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /closepolls — admin only, close all open polls."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return
    open_polls = storage.get_open_polls()
    if not open_polls:
        await update.effective_message.reply_text("🤷 Нет открытых опросов.")
        return
    closed = 0
    for poll_id, poll in open_polls.items():
        try:
            await context.bot.stop_poll(CONFIG["chat_id"], poll["message_id"])
            closed += 1
        except Exception:
            logger.exception("Не удалось закрыть опрос %s", poll_id)
    await update.effective_message.reply_text(f"🔒 Закрыто опросов: {closed}/{len(open_polls)}")


async def cmd_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribers — admin only, list all subscribers."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return
    subs = storage.get_all_subscribers()
    if not subs:
        await update.effective_message.reply_text("📭 Нет подписчиков.")
        return
    lines = [f"👥 Подписчики ({len(subs)}):\n"]
    for i, s in enumerate(subs, 1):
        lines.append(f"{i}. {s['first_name']} (id: {s['user_id']})")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_reset_votes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resetvotes — admin only, clear all votes and reuse suggestions."""
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("🔒 Эта команда только для админов.")
        return
    storage.reset_all_votes()
    _previous_answers.clear()
    await update.effective_message.reply_text(
        "🔄 Все голосования сброшены. Предложения снова доступны для опросов.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    lines = [
        "📌 Команды:\n",
        "✏️ /suggest — предложить название (кнопка или /suggest <название>)",
        "📊 /results — текущий рейтинг недели",
        "ℹ️ /about — как всё устроено",
        "❓ /help — этот список",
    ]
    if is_admin(update.effective_user.id):
        lines.append(
            "\n🔧 Админ:\n"
            "📋 /suggestions — неиспользованные предложения\n"
            "🗑️ /delete <номер> — удалить предложение\n"
            "⚡ /forcedaily — запустить ежедневное голосование\n"
            "⚡ /forceweekly — запустить еженедельный финал\n"
            "📢 /forceprompt — отправить промпт дня\n"
            "👥 /subscribers — список подписчиков\n"
            "🔒 /closepolls — закрыть все открытые опросы\n"
            "🔄 /resetvotes — сбросить все голосования"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about and /start — explain how the bot works."""
    text = (
        "Бот для выбора названия группы, которая не может выбрать себе название. "
        "Уже долго не может. Я тут чтобы это как-то закончилось. 🫠\n\n"
        "1. Утром приходит промпт — жмёте кнопку, пишете название в личке. "
        "Или /suggest в чате.\n"
        "2. В 12:00 — голосование за накопившиеся варианты.\n"
        "3. В пятницу в 18:00 — финал: топ-10 за неделю.\n"
        "4. Повторять до победного. Или до распада группы.\n\n"
        "⚠️ Бот груб, не учтив и плохо шутит. Это не баг.\n\n"
        "/help — список команд."
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

    # Register handlers — ConversationHandler first (private /start deep link)
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start, filters=filters.ChatType.PRIVATE),
        ],
        states={
            AWAITING_BAND_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_band_name),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("start", cmd_start),
        ],
        conversation_timeout=300,
    )
    app.add_handler(conv_handler)

    app.add_handler(CommandHandler("suggest", cmd_suggest))
    app.add_handler(CommandHandler("suggestions", cmd_suggestions))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("results", cmd_results))
    app.add_handler(CommandHandler("forcedaily", cmd_forcedaily))
    app.add_handler(CommandHandler("forceweekly", cmd_forceweekly))
    app.add_handler(CommandHandler("forceprompt", cmd_forceprompt))
    app.add_handler(CommandHandler("subscribers", cmd_subscribers))
    app.add_handler(CommandHandler("resetvotes", cmd_reset_votes))
    app.add_handler(CommandHandler("closepolls", cmd_close_polls))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("start", cmd_about))
    app.add_handler(PollAnswerHandler(on_poll_answer))
    app.add_handler(PollHandler(on_poll_update))

    # Start scheduler
    SCHEDULER = create_scheduler(app.bot, CONFIG, PROMPT_LINES)
    SCHEDULER.start()
    logger.info("Планировщик запущен.")

    # Run
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
