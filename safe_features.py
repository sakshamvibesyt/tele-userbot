"""Safe add-on commands for the existing Pyrogram userbot.

Commands:
  .type <text>       Animate text by editing one message
  .stoptype          Stop the active .type animation in this chat
  .typing on|off     Show/hide a temporary typing indicator in this chat
  .bots              Send the saved Bots & Services message
  .botsset           Reply to a text message with .botsset to save it
  .botsedit          Reply to your previously sent bots message to edit it
  .botspreview       Preview the saved Bots & Services message

This module does not send mass messages or target other users.
"""
import asyncio
import logging
import os
from pathlib import Path

from pyrogram import filters, enums
from pyrogram.errors import FloodWait, MessageNotModified, RPCError

log = logging.getLogger(__name__)
DATA_DIR = Path(os.getenv("USERBOT_DATA_DIR", "."))
BOTS_TEXT_FILE = DATA_DIR / "bots_message.txt"

_type_tasks = {}
_typing_tasks = {}


def _load_bots_text():
    try:
        return BOTS_TEXT_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _save_bots_text(text):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BOTS_TEXT_FILE.write_text(text.strip() + "\n", encoding="utf-8")


async def _stop_task(task_map, chat_id):
    task = task_map.pop(chat_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def register_safe_features(app):
    @app.on_message(filters.command("type", prefixes=".") & filters.me)
    async def type_animation(client, message):
        if len(message.command) < 2:
            return await message.edit_text("Usage: `.type Hello brother`")

        text = message.text.split(maxsplit=1)[1]
        chat_id = message.chat.id
        await _stop_task(_type_tasks, chat_id)

        async def animate():
            current = ""
            try:
                # Keep edit pace modest to avoid Telegram flood limits.
                for char in text[:3500]:
                    current += char
                    try:
                        await message.edit_text(current, parse_mode=enums.ParseMode.DISABLED)
                    except MessageNotModified:
                        pass
                    except FloodWait as e:
                        await asyncio.sleep(min(e.value, 10))
                        await message.edit_text(current, parse_mode=enums.ParseMode.DISABLED)
                    await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                raise
            except RPCError as e:
                log.warning("Type animation stopped due to Telegram error: %s", e)
            finally:
                _type_tasks.pop(chat_id, None)

        task = asyncio.create_task(animate())
        _type_tasks[chat_id] = task

    @app.on_message(filters.command("stoptype", prefixes=".") & filters.me)
    async def stop_type(client, message):
        await _stop_task(_type_tasks, message.chat.id)
        await message.edit_text("Typing animation stopped.")

    @app.on_message(filters.command("typing", prefixes=".") & filters.me)
    async def typing_indicator(client, message):
        if len(message.command) < 2 or message.command[1].lower() not in {"on", "off"}:
            return await message.edit_text("Usage: `.typing on` or `.typing off`")

        chat_id = message.chat.id
        mode = message.command[1].lower()
        if mode == "off":
            await _stop_task(_typing_tasks, chat_id)
            return await message.edit_text("Typing indicator stopped in this chat.")

        await _stop_task(_typing_tasks, chat_id)

        async def keep_typing():
            try:
                while True:
                    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                raise
            except RPCError as e:
                log.warning("Typing indicator stopped due to Telegram error: %s", e)
            finally:
                _typing_tasks.pop(chat_id, None)

        _typing_tasks[chat_id] = asyncio.create_task(keep_typing())
        await message.edit_text(
            "Typing indicator enabled for this chat. Telegram may expire or ignore it; "
            "this is not guaranteed to stay active continuously."
        )

    @app.on_message(filters.command("botsset", prefixes=".") & filters.me)
    async def bots_set(client, message):
        replied = message.reply_to_message
        if not replied or not (replied.text or replied.caption):
            return await message.edit_text(
                "Reply to a text message containing your Bots & Services list, then send `.botsset`."
            )
        text = replied.text or replied.caption
        if len(text) > 4000:
            return await message.edit_text("The template is too long. Keep it under 4000 characters.")
        _save_bots_text(text)
        await message.edit_text("Bots & Services message saved. Use `.bots` to send it.")

    @app.on_message(filters.command("bots", prefixes=".") & filters.me)
    async def bots_send(client, message):
        text = _load_bots_text()
        if not text:
            return await message.edit_text(
                "No Bots & Services template saved yet. Reply to your template text with `.botsset` first."
            )
        replied = message.reply_to_message
        try:
            if replied:
                await client.send_message(
                    message.chat.id, text, reply_to_message_id=replied.id,
                    parse_mode=enums.ParseMode.DISABLED
                )
            else:
                await client.send_message(
                    message.chat.id, text, parse_mode=enums.ParseMode.DISABLED
                )
            await message.delete()
        except RPCError as e:
            await message.edit_text(f"Could not send the saved message: {e}")

    @app.on_message(filters.command("botsedit", prefixes=".") & filters.me)
    async def bots_edit(client, message):
        replied = message.reply_to_message
        text = _load_bots_text()
        if not text:
            return await message.edit_text("No saved template. Save one with `.botsset` first.")
        if not replied:
            return await message.edit_text(
                "Reply to a message you sent with `.bots`, then use `.botsedit`."
            )
        try:
            await replied.edit_text(text, parse_mode=enums.ParseMode.DISABLED)
            await message.delete()
        except RPCError as e:
            await message.edit_text(
                "Couldn't edit that message. Reply to a text message you sent yourself.\n"
                f"Details: {e}"
            )

    @app.on_message(filters.command("botspreview", prefixes=".") & filters.me)
    async def bots_preview(client, message):
        text = _load_bots_text()
        if not text:
            return await message.edit_text(
                "No saved template. Reply to your Bots & Services text with `.botsset` first."
            )
        await message.edit_text(text, parse_mode=enums.ParseMode.DISABLED)

    log.info("Safe userbot feature add-on registered.")
