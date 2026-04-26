"""
Admin panel - /admin command.
Access is granted only to users in ADMIN_IDS list.
If not in list: "Нет доступа"
"""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS
from database.db import (
    get_all_channels, get_all_giveaways, get_all_logs,
    get_stats, ban_channel, unban_channel, ban_user, unban_user,
    get_participants_count
)
from utils.keyboards import admin_main_keyboard, admin_back_keyboard

router = Router()
logger = logging.getLogger(__name__)


class AdminStates(StatesGroup):
    waiting_ban_channel_id = State()
    waiting_unban_channel_id = State()
    waiting_ban_user_id = State()
    waiting_unban_user_id = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return

    await message.answer(
        "🔐 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_back")
async def adm_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "🔐 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    stats = await get_stats()
    text = (
        "📊 <b>Статистика системы</b>\n\n"
        f"👥 Пользователей всего: <b>{stats['total_users']}</b>\n"
        f"🚫 Заблокировано: <b>{stats['banned_users']}</b>\n\n"
        f"📢 Каналов всего: <b>{stats['total_channels']}</b>\n"
        f"🚫 Заблокировано: <b>{stats['banned_channels']}</b>\n\n"
        f"🎁 Розыгрышей всего: <b>{stats['total_giveaways']}</b>\n"
        f"✅ Активных: <b>{stats['active_giveaways']}</b>\n\n"
        f"🙋 Участий всего: <b>{stats['total_participants']}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "adm_channels")
async def adm_channels(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    channels = await get_all_channels(limit=30)

    if not channels:
        await callback.message.edit_text(
            "📢 Нет добавленных каналов.",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return

    lines = ["📢 <b>Каналы (последние 30):</b>\n"]
    for ch in channels:
        status = "🚫" if ch["is_banned"] else "✅"
        owner = f"@{ch['username']}" if ch.get("username") else ch.get("first_name", "?")
        lines.append(
            f"{status} <code>{ch['channel_id']}</code> — {ch['channel_name']}\n"
            f"   👤 Владелец: {owner} | 📅 {ch['added_at'][:10]}"
        )

    text = "\n".join(lines)
    # Truncate if too long
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (обрезано)"

    await callback.message.edit_text(
        text,
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "adm_giveaways")
async def adm_giveaways(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    giveaways = await get_all_giveaways(limit=20)

    if not giveaways:
        await callback.message.edit_text(
            "🎁 Нет созданных розыгрышей.",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return

    from database.db import get_user
    lines = ["🎁 <b>Розыгрыши (последние 20):</b>\n"]
    for g in giveaways:
        status = "✅ Активен" if g["is_active"] else "🏁 Завершён"
        owner = f"@{g['username']}" if g.get("username") else g.get("first_name", "?")
        count = await get_participants_count(g["id"])
        winner_str = ""
        if not g["is_active"]:
            if g.get("winner_id"):
                w = await get_user(g["winner_id"])
                if w:
                    wname = f"@{w['username']}" if w.get("username") else (w.get("first_name") or str(w["user_id"]))
                    winner_str = f"\n   🏆 Победитель: {wname}"
                else:
                    winner_str = f"\n   🏆 Победитель: id={g['winner_id']}"
            else:
                winner_str = "\n   🏆 Победитель: не определён"
        lines.append(
            f"#{g['id']} {status}\n"
            f"   📢 {g['channel_id']} | 👤 {owner}\n"
            f"   👥 Участников: {count} | 📅 {g['created_at'][:10]}"
            + winner_str
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (обрезано)"

    await callback.message.edit_text(
        text,
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "adm_logs")
async def adm_logs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    logs = await get_all_logs(limit=50)

    if not logs:
        await callback.message.edit_text(
            "📝 Нет записей в логах.",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return

    EVENT_ICONS = {
        "new_user": "👤",
        "start_new_user": "🆕",
        "start_existing_user": "🔄",
        "channel_added": "📢",
        "channel_deleted": "🗑️",
        "channel_banned": "🚫",
        "channel_unbanned": "✅",
        "giveaway_created": "🎁",
        "giveaway_published": "📤",
        "giveaway_ended": "🏁",
        "giveaway_entry_failed": "❌",
        "participant_joined": "🙋",
        "user_banned": "🔨",
        "user_unbanned": "🔓",
    }

    lines = ["📝 <b>Логи (последние 50):</b>\n"]
    for log in logs:
        icon = EVENT_ICONS.get(log["event_type"], "📌")
        user = f"@{log['username']}" if log.get("username") else f"id={log.get('user_id', '?')}"
        extra = f" | {log['extra_data']}" if log.get("extra_data") else ""
        lines.append(
            f"{icon} <b>{log['event_type']}</b>\n"
            f"   👤 {user} | 🕒 {log['created_at'][5:16]}{extra}"
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (обрезано)"

    await callback.message.edit_text(
        text,
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ---- Ban / Unban Channel ----

@router.callback_query(F.data == "adm_ban_channel")
async def adm_ban_channel_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_ban_channel_id)
    await callback.message.edit_text(
        "🔨 Введите ID канала для блокировки (например: <code>-1001234567890</code>):",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_ban_channel_id)
async def do_ban_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    channel_id = message.text.strip()
    await ban_channel(channel_id)
    await state.clear()
    await message.answer(
        f"✅ Канал <code>{channel_id}</code> заблокирован.",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_unban_channel")
async def adm_unban_channel_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_unban_channel_id)
    await callback.message.edit_text(
        "✅ Введите ID канала для разблокировки:",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_unban_channel_id)
async def do_unban_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    channel_id = message.text.strip()
    await unban_channel(channel_id)
    await state.clear()
    await message.answer(
        f"✅ Канал <code>{channel_id}</code> разблокирован.",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


# ---- Ban / Unban User ----

@router.callback_query(F.data == "adm_ban_user")
async def adm_ban_user_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_ban_user_id)
    await callback.message.edit_text(
        "🔨 Введите Telegram user_id пользователя для блокировки:",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_ban_user_id)
async def do_ban_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer("❌ Введите числовой ID пользователя.")
        return
    user_id = int(message.text.strip())
    await ban_user(user_id)
    await state.clear()
    await message.answer(
        f"✅ Пользователь <code>{user_id}</code> заблокирован.",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_unban_user")
async def adm_unban_user_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_unban_user_id)
    await callback.message.edit_text(
        "✅ Введите Telegram user_id пользователя для разблокировки:",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_unban_user_id)
async def do_unban_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer("❌ Введите числовой ID пользователя.")
        return
    user_id = int(message.text.strip())
    await unban_user(user_id)
    await state.clear()
    await message.answer(
        f"✅ Пользователь <code>{user_id}</code> разблокирован.",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )
