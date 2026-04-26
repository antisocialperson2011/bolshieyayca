import logging
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import get_or_create_user, is_user_banned, get_giveaway_by_ref, log_event
from utils.keyboards import main_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    args = message.text.split()

    # Check if user is banned
    if await is_user_banned(user.id):
        await message.answer("⛔ Вы заблокированы в данном боте.")
        return

    # --- FLOWCHART 1 ---
    # Check if user came via ref link from giveaway post
    ref_token = args[1] if len(args) > 1 else None

    if ref_token:
        # User arrived via bot-generated ref link for giveaway -> go to flowchart 2 logic
        await state.update_data(ref_token=ref_token)
        from handlers.giveaway_entry import handle_giveaway_entry
        await handle_giveaway_entry(message, state, bot, ref_token)
        return

    # No ref link - normal /start
    # Get or create user
    db_user = await get_or_create_user(
        user.id, user.username or "", user.first_name or "", user.last_name or ""
    )

    is_new = False
    # If user was just created (registered_at == now) we consider them new
    # We detect new vs existing by checking if get_or_create returned existing
    # Simple check: compare registration time proximity
    from datetime import datetime, timezone
    reg_time = datetime.fromisoformat(db_user["registered_at"])
    now = datetime.utcnow()
    diff = (now - reg_time).total_seconds()
    is_new = diff < 5  # registered less than 5 seconds ago

    if is_new:
        await message.answer(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            "Вы зарегистрированы в системе. Теперь вы можете создавать розыгрыши и управлять своими каналами.",
            reply_markup=main_menu_keyboard()
        )
        await log_event("start_new_user", user.id)
    else:
        await message.answer(
            f"👋 С возвращением, {user.first_name}!\n\nВыберите действие:",
            reply_markup=main_menu_keyboard()
        )
        await log_event("start_existing_user", user.id)


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()
