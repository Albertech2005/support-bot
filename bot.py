#!/usr/bin/env python3
"""
Support Ticket Bot
------------------
- Users DM the bot  →  bot creates a Forum Topic in the staff group
- Staff reply in the topic  →  bot forwards reply back to the user
- Staff close the topic  →  user gets a "ticket closed" notification

Staff commands (inside a topic):
  /close  — close the ticket and notify the user
  /ban    — block the user from opening new tickets
  /info   — show the user's info card again
"""

import json
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN      = "8910708576:AAE3n6jZ9H2fB9JirrKb4VvjM9EpOuIrbGA"
STAFF_GROUP_ID = -1004403000187

WELCOME_MSG = (
    "👋 Hi! Send your message and our support team will get back to you shortly."
)
TICKET_CLOSED_MSG = (
    "✅ Your ticket has been closed. Feel free to message again if you need more help!"
)
BANNED_MSG = (
    "🚫 You have been blocked from submitting support tickets."
)

DATA_FILE = Path("tickets.json")

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Persistence ──────────────────────────────────────────────────────────────
def load_data() -> dict:
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())
    else:
        data = {}
    data.setdefault("user_to_topic", {})
    data.setdefault("topic_to_user", {})
    data.setdefault("topic_to_userinfo", {})
    data.setdefault("banned_users", [])
    return data


def save_data(data: dict):
    DATA_FILE.write_text(json.dumps(data, indent=2))


def is_staff_group(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.id == STAFF_GROUP_ID


# ── User handlers ─────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — always send the welcome message."""
    await update.effective_message.reply_text(WELCOME_MSG)


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sent a DM → forward to staff group topic (create one if needed)."""
    user = update.effective_user
    msg  = update.effective_message
    data = load_data()
    uid  = str(user.id)

    # Blocked user
    if user.id in data["banned_users"]:
        await msg.reply_text(BANNED_MSG)
        return

    # First message → create topic
    if uid not in data["user_to_topic"]:
        display_name = user.full_name
        if user.username:
            display_name += f" (@{user.username})"

        topic = await context.bot.create_forum_topic(
            chat_id=STAFF_GROUP_ID,
            name=display_name[:128],
        )
        topic_id = topic.message_thread_id

        data["user_to_topic"][uid]                   = topic_id
        data["topic_to_user"][str(topic_id)]          = user.id
        data["topic_to_userinfo"][str(topic_id)]      = {
            "full_name": user.full_name,
            "username":  user.username or "N/A",
            "user_id":   user.id,
        }
        save_data(data)

        info = (
            f"🎫 <b>New Ticket</b>\n"
            f"👤 <b>Name:</b> {user.full_name}\n"
            f"🔗 <b>Username:</b> @{user.username or 'N/A'}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>"
        )
        await context.bot.send_message(
            chat_id=STAFF_GROUP_ID,
            message_thread_id=topic_id,
            text=info,
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"Created topic {topic_id} for user {user.id} ({display_name})")

    topic_id = data["user_to_topic"][uid]

    await context.bot.copy_message(
        chat_id=STAFF_GROUP_ID,
        from_chat_id=msg.chat_id,
        message_id=msg.message_id,
        message_thread_id=topic_id,
    )


# ── Staff commands ────────────────────────────────────────────────────────────
async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/close — close the ticket, notify user, clean up."""
    if not is_staff_group(update):
        return

    msg = update.effective_message
    tid = str(msg.message_thread_id) if msg.message_thread_id else None

    if not tid:
        await msg.reply_text("⚠️ Use this command inside a ticket topic.")
        return

    data = load_data()

    if tid not in data["topic_to_user"]:
        await msg.reply_text("⚠️ This topic is not linked to any active ticket.")
        return

    user_id     = data["topic_to_user"][tid]
    user_id_str = str(user_id)

    # Notify the user
    try:
        await context.bot.send_message(chat_id=user_id, text=TICKET_CLOSED_MSG)
    except Exception as e:
        logger.warning(f"Could not notify user {user_id}: {e}")

    # Close the forum topic
    try:
        await context.bot.close_forum_topic(
            chat_id=STAFF_GROUP_ID,
            message_thread_id=int(tid),
        )
    except Exception as e:
        logger.warning(f"Could not close forum topic {tid}: {e}")

    # Clean up
    data["topic_to_user"].pop(tid, None)
    data["topic_to_userinfo"].pop(tid, None)
    data["user_to_topic"].pop(user_id_str, None)
    save_data(data)

    await msg.reply_text("✅ Ticket closed and user notified.")
    logger.info(f"Ticket closed by staff — topic {tid}, user {user_id}")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ban — block the user from opening new tickets."""
    if not is_staff_group(update):
        return

    msg = update.effective_message
    tid = str(msg.message_thread_id) if msg.message_thread_id else None

    if not tid:
        await msg.reply_text("⚠️ Use this command inside a ticket topic.")
        return

    data = load_data()

    if tid not in data["topic_to_user"]:
        await msg.reply_text("⚠️ This topic is not linked to any active ticket.")
        return

    user_id = data["topic_to_user"][tid]

    if user_id in data["banned_users"]:
        await msg.reply_text("ℹ️ This user is already banned.")
        return

    data["banned_users"].append(user_id)

    # Also close the ticket
    user_id_str = str(user_id)
    data["topic_to_user"].pop(tid, None)
    data["topic_to_userinfo"].pop(tid, None)
    data["user_to_topic"].pop(user_id_str, None)
    save_data(data)

    try:
        await context.bot.close_forum_topic(
            chat_id=STAFF_GROUP_ID,
            message_thread_id=int(tid),
        )
    except Exception as e:
        logger.warning(f"Could not close forum topic {tid}: {e}")

    try:
        await context.bot.send_message(chat_id=user_id, text=BANNED_MSG)
    except Exception:
        pass

    await msg.reply_text(f"🚫 User <code>{user_id}</code> has been banned.", parse_mode=ParseMode.HTML)
    logger.info(f"User {user_id} banned by staff")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unban <user_id> — unblock a previously banned user."""
    if not is_staff_group(update):
        return

    msg = update.effective_message

    if not context.args:
        await msg.reply_text("⚠️ Usage: /unban <user_id>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await msg.reply_text("⚠️ Invalid user ID. Usage: /unban <user_id>")
        return

    data = load_data()

    if user_id not in data["banned_users"]:
        await msg.reply_text(f"ℹ️ User <code>{user_id}</code> is not banned.", parse_mode=ParseMode.HTML)
        return

    data["banned_users"].remove(user_id)
    save_data(data)

    await msg.reply_text(
        f"✅ User <code>{user_id}</code> has been unbanned. They can now open tickets again.",
        parse_mode=ParseMode.HTML,
    )
    logger.info(f"User {user_id} unbanned by staff")


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/info — show the user's info card again."""
    if not is_staff_group(update):
        return

    msg = update.effective_message
    tid = str(msg.message_thread_id) if msg.message_thread_id else None

    if not tid:
        await msg.reply_text("⚠️ Use this command inside a ticket topic.")
        return

    data = load_data()

    if tid not in data["topic_to_userinfo"]:
        await msg.reply_text("⚠️ No user info found for this topic.")
        return

    u = data["topic_to_userinfo"][tid]
    info = (
        f"🎫 <b>Ticket Info</b>\n"
        f"👤 <b>Name:</b> {u['full_name']}\n"
        f"🔗 <b>Username:</b> @{u['username']}\n"
        f"🆔 <b>User ID:</b> <code>{u['user_id']}</code>"
    )
    await msg.reply_text(info, parse_mode=ParseMode.HTML)


# ── Staff reply forwarding ────────────────────────────────────────────────────
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch all group messages and forward staff replies to users."""
    msg = update.effective_message

    if msg.forum_topic_created or msg.forum_topic_closed or msg.forum_topic_reopened:
        return

    if msg.from_user and msg.from_user.is_bot:
        return

    if not msg.message_thread_id:
        return

    data = load_data()
    tid  = str(msg.message_thread_id)

    if tid not in data["topic_to_user"]:
        return

    user_id = data["topic_to_user"][tid]

    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id,
        )
        logger.info(f"Reply forwarded to user {user_id}")
    except Exception as e:
        logger.warning(f"Could not deliver reply to user {user_id}: {e}")


async def handle_topic_closed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forum topic manually closed → notify user and clean up."""
    msg = update.effective_message

    if not msg.message_thread_id:
        return

    data = load_data()
    tid  = str(msg.message_thread_id)

    if tid not in data["topic_to_user"]:
        return

    user_id     = data["topic_to_user"][tid]
    user_id_str = str(user_id)

    try:
        await context.bot.send_message(chat_id=user_id, text=TICKET_CLOSED_MSG)
    except Exception as e:
        logger.warning(f"Could not notify user {user_id}: {e}")

    data["topic_to_user"].pop(tid, None)
    data["topic_to_userinfo"].pop(tid, None)
    data["user_to_topic"].pop(user_id_str, None)
    save_data(data)

    logger.info(f"Ticket closed (manual) — topic {tid}, user {user_id}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Private: /start
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))

    # Private: user messages
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_user_message,
    ))

    # Group: staff commands
    app.add_handler(CommandHandler("close",  cmd_close,  filters=filters.Chat(STAFF_GROUP_ID)))
    app.add_handler(CommandHandler("ban",    cmd_ban,    filters=filters.Chat(STAFF_GROUP_ID)))
    app.add_handler(CommandHandler("unban",  cmd_unban,  filters=filters.Chat(STAFF_GROUP_ID)))
    app.add_handler(CommandHandler("info",   cmd_info,   filters=filters.Chat(STAFF_GROUP_ID)))

    # Group: staff replies
    app.add_handler(MessageHandler(
        filters.Chat(STAFF_GROUP_ID),
        handle_group_message,
    ))

    # Group: topic closed manually
    app.add_handler(MessageHandler(
        filters.Chat(STAFF_GROUP_ID) & filters.StatusUpdate.FORUM_TOPIC_CLOSED,
        handle_topic_closed,
    ))

    logger.info("✅ Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
