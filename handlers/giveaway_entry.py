"""
Flowchart 2: User arrives via giveaway ref link
- Check if came via ref link from giveaway post (YES branch)
- Check if giveaway requires subscription to channels
- If yes: check user subscriptions
  - If subscribed: add as participant, output success message
  - If not subscribed: output "you haven't fulfilled all conditions"
- If no required channels: add as participant directly
"""
import logging
import json
from aiogram import Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from database.db import (
    get_or_create_user, get_giveaway_by_ref, add_participant,
    is_participant, get_channel_by_id, log_event
)

logger = logging.getLogger(__name__)


async def check_channel_subscription(bot: Bot, user_id: int, channel_id: str) -> bool:
    """Check if user is subscribed to a channel."""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramBadRequest:
        return False
    except Exception as e:
        logger.error(f"Error checking subscription for {user_id} in {channel_id}: {e}")
        return False


async def handle_giveaway_entry(message: Message, state: FSMContext, bot: Bot, ref_token: str):
    """
    Main entry point for Flowchart 2.
    Called when user starts bot with a giveaway ref link.
    """
    user = message.from_user

    # Ensure user is registered
    await get_or_create_user(
        user.id, user.username or "", user.first_name or "", user.last_name or ""
    )

    # Get giveaway by ref link token
    giveaway = await get_giveaway_by_ref(ref_token)

    if not giveaway:
        await message.answer("❌ Розыгрыш не найден или уже завершён.")
        return

    # Check if already a participant
    if await is_participant(giveaway["id"], user.id):
        await message.answer(
            f"ℹ️ Вы уже участвуете в розыгрыше!\n\n"
            f"📢 Канал: {giveaway.get('channel_id', '')}\n"
            f"⏰ Окончание: {giveaway.get('end_value', 'не указано')}"
        )
        return

    # --- FLOWCHART 2 LOGIC ---

    # Check if giveaway requires subscription to channels
    required_channels_raw = giveaway.get("required_channels")

    if required_channels_raw:
        # Parse required channels
        try:
            required_channels = json.loads(required_channels_raw)
        except Exception:
            required_channels = [required_channels_raw] if required_channels_raw else []

        if required_channels:
            # Check subscription for each required channel
            all_subscribed = True
            not_subscribed = []

            for ch_id in required_channels:
                subscribed = await check_channel_subscription(bot, user.id, ch_id)
                if not subscribed:
                    all_subscribed = False
                    not_subscribed.append(ch_id)

            if not all_subscribed:
                # User not subscribed to all required channels
                channels_text = "\n".join([f"• {ch}" for ch in not_subscribed])
                await message.answer(
                    f"❌ Вы не выполнили все условия розыгрыша.\n\n"
                    f"Для участия необходимо подписаться на:\n{channels_text}\n\n"
                    f"После подписки нажмите /start снова."
                )
                await log_event("giveaway_entry_failed", user.id,
                                f"giveaway_id={giveaway['id']} not_subscribed={not_subscribed}")
                return

    # All conditions met - add user as participant
    added = await add_participant(giveaway["id"], user.id)

    if added:
        await log_event("participant_joined", user.id, f"giveaway_id={giveaway['id']}")

    # Output success message
    await message.answer(
        f"🎉 Теперь вы участвуете в розыгрыше!\n\n"
        f"📢 Канал, где проводится розыгрыш: {giveaway.get('channel_id', '')}\n"
        f"⏰ Дата окончания розыгрыша: {giveaway.get('end_value', 'не указано')}"
    )
