"""
Telegram bot integration for Tayfa.

Sends AskUserQuestion notifications to Telegram with inline keyboard buttons.
Receives answers via callback_query and forwards them back to the agent.
Free-text messages (without "agent:" prefix) are sent to boss by default.
When last message to an agent was from Telegram, agent replies are forwarded back.

Uses raw Telegram Bot API via httpx (no extra dependencies).
Long-polling runs in an asyncio background task.
"""

import asyncio
import json
import logging
from typing import Callable, Awaitable

import httpx

logger = logging.getLogger("tayfa.telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}"

# Default agent to send messages to when no agent is specified
DEFAULT_AGENT = "boss"


class TayfaTelegramBot:
    """Lightweight Telegram bot using long-polling."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self.base_url = TELEGRAM_API.format(token=token)
        self._offset = 0
        self._task: asyncio.Task | None = None
        self._running = False
        self._client: httpx.AsyncClient | None = None
        # Callback: called when user clicks an inline button or sends text
        # signature: async callback(agent_name: str, answer_text: str) -> None
        self._on_answer: Callable[[str, str], Awaitable[None]] | None = None
        # Pending questions: { callback_data_prefix -> { agent, question_text } }
        self._pending: dict[str, dict] = {}
        self._question_counter = 0
        # Track which agents were last messaged from Telegram
        # If agent_name is in this set, forward agent's reply back to Telegram
        self._from_telegram: set[str] = set()

    def set_answer_callback(self, callback: Callable[[str, str], Awaitable[None]]):
        """Register a callback for when user answers a question via Telegram."""
        self._on_answer = callback

    def mark_from_telegram(self, agent_name: str):
        """Mark that the last message to this agent came from Telegram."""
        self._from_telegram.add(agent_name)

    def mark_from_web(self, agent_name: str):
        """Mark that the last message to this agent came from Web UI (not Telegram)."""
        self._from_telegram.discard(agent_name)

    def is_from_telegram(self, agent_name: str) -> bool:
        """Check if the last message to this agent was from Telegram."""
        return agent_name in self._from_telegram

    async def _safe_on_answer(self, agent_name: str, answer_text: str):
        """Wrapper for _on_answer that catches exceptions (used with create_task)."""
        try:
            await self._on_answer(agent_name, answer_text)
        except Exception as e:
            logger.error(f"[TelegramBot] on_answer error for '{agent_name}': {e}")

    async def start(self):
        """Start the long-polling loop."""
        if self._running:
            return
        self._running = True
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("[TelegramBot] Started long-polling")

    async def stop(self):
        """Stop the long-polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[TelegramBot] Stopped")

    async def send_question(self, agent_name: str, questions: list[dict]) -> bool:
        """
        Send an AskUserQuestion to Telegram as a message with inline keyboard.

        Args:
            agent_name: Name of the agent asking the question.
            questions: List of question dicts from AskUserQuestion input.
                       Each has 'question' (str) and 'options' (list of {label, description}).

        Returns:
            True if message was sent successfully.
        """
        if not self._client:
            return False

        self._question_counter += 1
        prefix = f"q{self._question_counter}"

        # Build message text
        text_parts = [f"❓ <b>{agent_name}</b> asks:"]

        # Build inline keyboard
        keyboard_rows = []

        for q in questions:
            question_text = q.get("question", "(no question)")
            text_parts.append(f"\n{question_text}")

            options = q.get("options", [])
            for i, opt in enumerate(options):
                label = opt.get("label", f"Option {i+1}")
                desc = opt.get("description", "")
                callback_data = f"{prefix}:{i}"

                # Store the mapping
                self._pending[callback_data] = {
                    "agent": agent_name,
                    "answer": label,
                }

                keyboard_rows.append([{
                    "text": f"{label}" + (f" — {desc[:30]}" if desc else ""),
                    "callback_data": callback_data,
                }])

        message_text = "\n".join(text_parts)

        payload = {
            "chat_id": self.chat_id,
            "text": message_text,
            "parse_mode": "HTML",
        }
        if keyboard_rows:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": keyboard_rows,
            })

        try:
            resp = await self._client.post(
                f"{self.base_url}/sendMessage",
                data=payload,
            )
            if resp.status_code == 200:
                logger.info(f"[TelegramBot] Sent question from {agent_name} to chat {self.chat_id}")
                return True
            else:
                logger.error(f"[TelegramBot] sendMessage failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[TelegramBot] sendMessage error: {e}")
            return False

    async def send_agent_reply(self, agent_name: str, reply_text: str) -> bool:
        """Send an agent's reply back to Telegram (when last message was from TG)."""
        if not self._client or not reply_text:
            return False

        # Truncate very long replies
        if len(reply_text) > 4000:
            reply_text = reply_text[:4000] + "\n\n…(truncated)"

        text = f"💬 <b>{agent_name}</b>:\n\n{_escape_html(reply_text)}"

        try:
            resp = await self._client.post(
                f"{self.base_url}/sendMessage",
                data={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            if resp.status_code == 200:
                logger.info(f"[TelegramBot] Forwarded reply from {agent_name}")
                return True
            else:
                logger.error(f"[TelegramBot] sendMessage reply failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[TelegramBot] send_agent_reply error: {e}")
            return False

    async def send_notification(self, text: str) -> bool:
        """Send a simple text notification to Telegram."""
        if not self._client:
            return False
        try:
            resp = await self._client.post(
                f"{self.base_url}/sendMessage",
                data={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"[TelegramBot] notification error: {e}")
            return False

    async def _poll_loop(self):
        """Long-polling loop for incoming updates."""
        logger.info("[TelegramBot] Poll loop started")
        while self._running:
            try:
                resp = await self._client.get(
                    f"{self.base_url}/getUpdates",
                    params={
                        "offset": self._offset,
                        "timeout": 30,
                        "allowed_updates": json.dumps(["callback_query", "message"]),
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"[TelegramBot] getUpdates: {resp.status_code}")
                    await asyncio.sleep(5)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    logger.warning(f"[TelegramBot] getUpdates not ok: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    await self._handle_update(update)

            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                # Normal for long-polling
                continue
            except Exception as e:
                logger.error(f"[TelegramBot] poll error: {e}")
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict):
        """Handle a single Telegram update."""
        # Handle callback_query (inline button press)
        callback = update.get("callback_query")
        if callback:
            callback_data = callback.get("data", "")
            callback_id = callback.get("id", "")

            pending = self._pending.pop(callback_data, None)
            if pending and self._on_answer:
                agent_name = pending["agent"]
                answer_text = pending["answer"]

                # Mark this agent as "last messaged from Telegram"
                self.mark_from_telegram(agent_name)

                # Answer the callback to remove "loading" state
                try:
                    await self._client.post(
                        f"{self.base_url}/answerCallbackQuery",
                        data={
                            "callback_query_id": callback_id,
                            "text": f"Sent: {answer_text}",
                        },
                    )
                except Exception:
                    pass

                # Edit the message to show which option was selected
                message = callback.get("message", {})
                msg_id = message.get("message_id")
                msg_chat_id = message.get("chat", {}).get("id")
                if msg_id and msg_chat_id:
                    original_text = message.get("text", "")
                    try:
                        await self._client.post(
                            f"{self.base_url}/editMessageText",
                            data={
                                "chat_id": msg_chat_id,
                                "message_id": msg_id,
                                "text": f"{original_text}\n\n✅ <b>Selected: {answer_text}</b>",
                                "parse_mode": "HTML",
                            },
                        )
                    except Exception:
                        pass

                # Forward the answer to the agent (fire-and-forget — don't block poll_loop)
                logger.info(f"[TelegramBot] User selected '{answer_text}' for agent '{agent_name}'")
                asyncio.create_task(self._safe_on_answer(agent_name, answer_text))
            else:
                # Unknown callback — just acknowledge
                try:
                    await self._client.post(
                        f"{self.base_url}/answerCallbackQuery",
                        data={
                            "callback_query_id": callback_id,
                            "text": "Question expired or already answered",
                        },
                    )
                except Exception:
                    pass
            return

        # Handle text message
        msg = update.get("message")
        if msg and msg.get("text"):
            text = msg["text"].strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            # Only process messages from the configured chat
            if chat_id != self.chat_id:
                return

            # Ignore bot commands
            if text.startswith("/"):
                return

            # Determine target agent and message text
            agent_name = None
            answer = None

            if ":" in text and not text.startswith(":"):
                # "agent_name: message" format
                parts = text.split(":", 1)
                candidate = parts[0].strip().lower()
                # Only treat as agent prefix if it looks like an agent name (short, no spaces)
                if len(candidate) <= 20 and " " not in candidate:
                    agent_name = candidate
                    answer = parts[1].strip()

            if not agent_name or not answer:
                # No agent prefix — check pending questions first, then default to boss
                if self._pending:
                    last_key = list(self._pending.keys())[-1]
                    agent_name = self._pending[last_key]["agent"]
                else:
                    agent_name = DEFAULT_AGENT
                answer = text

            if self._on_answer and answer:
                # Mark this agent as "last messaged from Telegram"
                self.mark_from_telegram(agent_name)
                logger.info(f"[TelegramBot] Message to '{agent_name}': {answer[:50]}")
                # Fire-and-forget — don't block poll_loop while agent thinks
                asyncio.create_task(self._safe_on_answer(agent_name, answer))


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Module-level singleton ────────────────────────────────────────────────────

_bot: TayfaTelegramBot | None = None


def get_bot() -> TayfaTelegramBot | None:
    """Get the current bot instance (or None if not configured)."""
    return _bot


async def start_telegram_bot(token: str, chat_id: str, on_answer: Callable[[str, str], Awaitable[None]]) -> TayfaTelegramBot | None:
    """Create and start the Telegram bot. Returns the bot instance or None if token/chat_id is empty."""
    global _bot
    if not token or not chat_id:
        logger.info("[TelegramBot] No token or chat_id configured — skipping")
        return None

    _bot = TayfaTelegramBot(token, chat_id)
    _bot.set_answer_callback(on_answer)
    await _bot.start()
    return _bot


async def stop_telegram_bot():
    """Stop the Telegram bot if running."""
    global _bot
    if _bot:
        await _bot.stop()
        _bot = None
