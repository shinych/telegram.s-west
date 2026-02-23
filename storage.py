"""Atomic JSON storage helpers and data queries."""

import json
import os
import uuid
from datetime import datetime, timezone


SUGGESTIONS_FILE = "data/suggestions.json"
POLL_RESULTS_FILE = "data/poll_results.json"
WEEKLY_RESULTS_FILE = "data/weekly_results.json"
SUBSCRIBERS_FILE = "data/subscribers.json"


# ---------------------------------------------------------------------------
# Low-level I/O
# ---------------------------------------------------------------------------

def load_json(path: str):
    """Load JSON from *path*, returning [] or {} if file is missing."""
    if not os.path.exists(path):
        return [] if path in (SUGGESTIONS_FILE, WEEKLY_RESULTS_FILE, SUBSCRIBERS_FILE) else {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    """Atomically write *data* as JSON to *path*."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def add_suggestion(name: str, author_id: int, author_name: str):
    """Add a suggestion. Returns the new record, or None if duplicate."""
    suggestions = load_json(SUGGESTIONS_FILE)
    normalized = name.strip().lower()
    for s in suggestions:
        if s["name"].strip().lower() == normalized:
            return None
    record = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "author_id": author_id,
        "author_name": author_name,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "used_in_daily": False,
    }
    suggestions.append(record)
    save_json(SUGGESTIONS_FILE, suggestions)
    return record


def get_unused_suggestions() -> list:
    """Return suggestions that haven't been included in a daily poll yet."""
    suggestions = load_json(SUGGESTIONS_FILE)
    return [s for s in suggestions if not s["used_in_daily"]]


def mark_suggestions_used(ids: list[str]):
    """Flag suggestions by id as used in a daily poll."""
    id_set = set(ids)
    suggestions = load_json(SUGGESTIONS_FILE)
    for s in suggestions:
        if s["id"] in id_set:
            s["used_in_daily"] = True
    save_json(SUGGESTIONS_FILE, suggestions)


def reset_all_votes():
    """Clear all poll results and mark every suggestion as unused."""
    save_json(POLL_RESULTS_FILE, {})
    save_json(WEEKLY_RESULTS_FILE, [])
    suggestions = load_json(SUGGESTIONS_FILE)
    for s in suggestions:
        s["used_in_daily"] = False
    save_json(SUGGESTIONS_FILE, suggestions)


def get_all_suggestions() -> list:
    """Return every suggestion ever submitted."""
    return load_json(SUGGESTIONS_FILE)


def get_suggestion_by_id(suggestion_id: str):
    """Look up a single suggestion by its UUID."""
    for s in load_json(SUGGESTIONS_FILE):
        if s["id"] == suggestion_id:
            return s
    return None


def delete_suggestion(index: int) -> dict | None:
    """Delete an unused suggestion by 1-based index. Returns the removed record, or None."""
    unused = [s for s in load_json(SUGGESTIONS_FILE) if not s["used_in_daily"]]
    if index < 1 or index > len(unused):
        return None
    target_id = unused[index - 1]["id"]
    suggestions = load_json(SUGGESTIONS_FILE)
    removed = None
    new_list = []
    for s in suggestions:
        if s["id"] == target_id:
            removed = s
        else:
            new_list.append(s)
    save_json(SUGGESTIONS_FILE, new_list)
    return removed


# ---------------------------------------------------------------------------
# Poll results
# ---------------------------------------------------------------------------

def save_poll(telegram_poll_id: str, message_id: int, options: list,
              poll_type: str):
    """Register a new poll (daily or weekly)."""
    results = load_json(POLL_RESULTS_FILE)
    results[telegram_poll_id] = {
        "message_id": message_id,
        "options": options,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": poll_type,
        "closed": False,
    }
    save_json(POLL_RESULTS_FILE, results)


def update_poll_voter_counts(telegram_poll_id: str, option_ids: list[int],
                              delta: int):
    """Increment/decrement voter_count for the given option indices."""
    results = load_json(POLL_RESULTS_FILE)
    poll = results.get(telegram_poll_id)
    if not poll:
        return
    for idx in option_ids:
        if 0 <= idx < len(poll["options"]):
            poll["options"][idx]["voter_count"] = (
                poll["options"][idx].get("voter_count", 0) + delta
            )
    save_json(POLL_RESULTS_FILE, results)


def set_poll_option_counts(telegram_poll_id: str, counts: list[int]):
    """Set absolute voter_count for each option (from Poll update)."""
    results = load_json(POLL_RESULTS_FILE)
    poll = results.get(telegram_poll_id)
    if not poll:
        return
    for i, count in enumerate(counts):
        if i < len(poll["options"]):
            poll["options"][i]["voter_count"] = count
    save_json(POLL_RESULTS_FILE, results)


def close_poll(telegram_poll_id: str):
    """Mark a poll as closed."""
    results = load_json(POLL_RESULTS_FILE)
    if telegram_poll_id in results:
        results[telegram_poll_id]["closed"] = True
        save_json(POLL_RESULTS_FILE, results)


def get_daily_scores_since(since_dt: datetime) -> dict:
    """Aggregate votes per suggestion_id from daily polls since *since_dt*.

    Returns {suggestion_id: total_votes}.
    """
    results = load_json(POLL_RESULTS_FILE)
    scores: dict[str, int] = {}
    for poll in results.values():
        if poll["type"] != "daily":
            continue
        created = datetime.fromisoformat(poll["created_at"])
        if created < since_dt:
            continue
        for opt in poll["options"]:
            sid = opt.get("suggestion_id")
            if sid:
                scores[sid] = scores.get(sid, 0) + opt.get("voter_count", 0)
    return scores


def get_poll(telegram_poll_id: str):
    """Return a single poll record or None."""
    return load_json(POLL_RESULTS_FILE).get(telegram_poll_id)


# ---------------------------------------------------------------------------
# Weekly results
# ---------------------------------------------------------------------------

def add_weekly_result(result: dict):
    """Append a weekly result summary."""
    results = load_json(WEEKLY_RESULTS_FILE)
    results.append(result)
    save_json(WEEKLY_RESULTS_FILE, results)


def get_latest_weekly():
    """Return the most recent weekly result, or None."""
    results = load_json(WEEKLY_RESULTS_FILE)
    return results[-1] if results else None


def mark_weekly_revealed(index: int = -1):
    """Set revealed=True on a weekly result (default: latest)."""
    results = load_json(WEEKLY_RESULTS_FILE)
    if results:
        results[index]["revealed"] = True
        save_json(WEEKLY_RESULTS_FILE, results)


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------

def add_subscriber(user_id: int, first_name: str):
    """Idempotently add a subscriber. Returns True if new, False if already present."""
    subscribers = load_json(SUBSCRIBERS_FILE)
    for s in subscribers:
        if s["user_id"] == user_id:
            return False
    subscribers.append({
        "user_id": user_id,
        "first_name": first_name,
        "subscribed_at": datetime.now(timezone.utc).isoformat(),
    })
    save_json(SUBSCRIBERS_FILE, subscribers)
    return True


def remove_subscriber(user_id: int):
    """Remove a subscriber by user_id."""
    subscribers = load_json(SUBSCRIBERS_FILE)
    new_list = [s for s in subscribers if s["user_id"] != user_id]
    if len(new_list) != len(subscribers):
        save_json(SUBSCRIBERS_FILE, new_list)


def get_all_subscribers() -> list:
    """Return all subscribers."""
    return load_json(SUBSCRIBERS_FILE)
