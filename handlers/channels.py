"""
Channels management (Flowchart 1 - "Мои каналы" branch):
- If user has added channels before -> show list / add new
- Functional channel selection with bot admin check
- Add/remove channels
"""
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from database.db import (
    get_user_channels, add_channel, delete_channel,
    get_channel_by_id, log_event
)
from utils.keyboards import (
    channels_menu_keyboard, back_keyboard, channel_actions_keyboard,
    main_menu_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


class ChannelStates(StatesGroup):
    waiting_channel_link = State()


@router.callback_query(F.data == "my_channels")
async def my_channels(callback: CallbackQuery):
    channels = await get_user_channels(callback.from_user.id)
    has_channels = len(channels) > 0

    text = "📢 <b>Мои каналы</b>\n\n"
    if has_channels:
        text += f"У вас добавлено каналов: <b>{len(channels)}</b>\n"
        text += "Выберите действие:"
    else:
        text += "У вас пока нет добавленных каналов.\nДобавьте канал, чтобы начать!"

    await callback.message.edit_text(
        text,
        reply_markup=channels_menu_keyboard(has_channels),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "list_channels")
async def list_channels(callback: CallbackQuery):
    channels = await get_user_channels(callback.from_user.id)

    if not channels:
        await callback.message.edit_text(
            "У вас нет добавленных каналов.",
            reply_markup=back_keyboard("my_channels")
        )
        await callback.answer()
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['channel_name']} ({ch['added_at'][:10]})",
            callback_data=f"channel_info:{ch['channel_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="my_channels")])

    await callback.message.edit_text(
        "📋 <b>Ваши каналы:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("channel_info:"))
async def channel_info(callback: CallbackQuery):
    channel_id = callback.data.split(":")[1]
    ch = await get_channel_by_id(channel_id)

    if not ch:
        await callback.answer("Канал не найден.", show_alert=True)
        return

    text = (
        f"📢 <b>Информация о канале</b>\n\n"
        f"🏷️ Название: {ch['channel_name']}\n"
        f"🔗 Username: @{ch['channel_username'] or '—'}\n"
        f"🆔 ID: <code>{ch['channel_id']}</code>\n"
        f"📅 Дата добавления: {ch['added_at'][:16]}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=channel_actions_keyboard(channel_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "add_channel")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChannelStates.waiting_channel_link)
    await callback.message.edit_text(
        "📢 <b>Добавление канала</b>\n\n"
        "Перешлите любое сообщение из вашего канала или введите username канала (@channel_name).\n\n"
        "⚠️ Убедитесь, что бот уже добавлен в канал как администратор с правом отправки сообщений!",
        reply_markup=back_keyboard("my_channels"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ChannelStates.waiting_channel_link)
async def process_channel_link(message: Message, state: FSMContext, bot: Bot):
    channel_id = None
    channel_name = None
    channel_username = None

    # Check if forwarded from channel
    if message.forward_from_chat:
        chat = message.forward_from_chat
        channel_id = str(chat.id)
        channel_name = chat.title
        channel_username = chat.username or ""
    elif message.text:
        username = message.text.strip().lstrip("@").lstrip("https://t.me/")
        try:
            chat = await bot.get_chat(f"@{username}")
            channel_id = str(chat.id)
            channel_name = chat.title
            channel_username = chat.username or ""
        except Exception:
            await message.answer(
                "❌ Канал не найден. Проверьте username и убедитесь, что бот является администратором канала.",
                reply_markup=back_keyboard("my_channels")
            )
            return
    else:
        await message.answer(
            "❌ Перешлите сообщение из канала или введите @username канала.",
            reply_markup=back_keyboard("my_channels")
        )
        return

    # Check bot is admin in channel
    try:
        bot_member = await bot.get_chat_member(chat_id=channel_id, user_id=(await bot.get_me()).id)
        if bot_member.status not in ("administrator", "creator"):
            await message.answer(
                "❌ Вы не дали требуемые права доступа боту. Совершите действие добавления снова "
                "или добавьте права доступа боту вручную.\n\n"
                "Бот должен быть администратором канала с правом отправки сообщений.",
                reply_markup=back_keyboard("my_channels")
            )
            return
    except TelegramBadRequest as e:
        await message.answer(
            f"❌ Не удалось проверить права бота в канале.\n"
            f"Убедитесь, что бот добавлен как администратор.\n\nОшибка: {e}",
            reply_markup=back_keyboard("my_channels")
        )
        return

    # Add channel to DB
    added = await add_channel(
        owner_id=message.from_user.id,
        channel_id=channel_id,
        channel_name=channel_name,
        channel_username=channel_username
    )

    await state.clear()

    if added:
        await message.answer(
            f"✅ Канал был успешно добавлен, теперь в нём можно создать розыгрыш!\n\n"
            f"📢 <b>{channel_name}</b>\n"
            f"🆔 ID: <code>{channel_id}</code>",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "⚠️ Этот канал уже добавлен.",
            reply_markup=main_menu_keyboard()
        )


@router.callback_query(F.data.startswith("delete_channel:"))
async def confirm_delete_channel(callback: CallbackQuery):
    channel_id = callback.data.split(":")[1]
    from utils.keyboards import confirm_keyboard
    await callback.message.edit_text(
        f"❓ Вы уверены, что хотите удалить канал <code>{channel_id}</code>?",
        reply_markup=confirm_keyboard(f"confirm_delete_channel:{channel_id}", "list_channels"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_channel:"))
async def do_delete_channel(callback: CallbackQuery, bot: Bot):
    channel_id = callback.data.split(":")[1]

    # Remove bot from channel (optional - just remove from DB for now)
    await delete_channel(callback.from_user.id, channel_id)

    # Try to remove bot as admin
    try:
        bot_info = await bot.get_me()
        await bot.ban_chat_member(chat_id=channel_id, user_id=bot_info.id)
        await bot.unban_chat_member(chat_id=channel_id, user_id=bot_info.id)
    except Exception:
        pass  # Bot might not be in the channel anymore

    await callback.message.edit_text(
        "✅ Канал был успешно удалён.",
        reply_markup=back_keyboard("my_channels")
    )
    await callback.answer()
