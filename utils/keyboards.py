from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Создать розыгрыш", callback_data="create_giveaway")],
        [InlineKeyboardButton(text="📋 Мои розыгрыши", callback_data="my_giveaways")],
        [InlineKeyboardButton(text="📢 Мои каналы", callback_data="my_channels")],
    ])


def channels_menu_keyboard(has_channels: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_channels:
        buttons.append([InlineKeyboardButton(text="📋 Мои добавленные каналы", callback_data="list_channels")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить новый канал", callback_data="add_channel")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_keyboard(callback: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback)]
    ])


def channel_actions_keyboard(channel_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить канал", callback_data=f"delete_channel:{channel_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="list_channels")],
    ])


def giveaway_actions_keyboard(giveaway_id: int, is_active: bool = True) -> InlineKeyboardMarkup:
    buttons = []
    if is_active:
        buttons.append([InlineKeyboardButton(text="🏁 Завершить розыгрыш", callback_data=f"end_giveaway:{giveaway_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="my_giveaways")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def end_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ По времени", callback_data="end_type:time")],
        [InlineKeyboardButton(text="👥 По количеству участников", callback_data="end_type:count")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")],
    ])


def required_channels_keyboard(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['channel_name']}",
            callback_data=f"req_channel:{ch['channel_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="✅ Готово (без обязательных каналов)", callback_data="req_channel:none")])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard(confirm_cb: str, cancel_cb: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=confirm_cb),
            InlineKeyboardButton(text="❌ Нет", callback_data=cancel_cb),
        ]
    ])


# Admin keyboards

def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Каналы", callback_data="adm_channels")],
        [InlineKeyboardButton(text="🎁 Розыгрыши", callback_data="adm_giveaways")],
        [InlineKeyboardButton(text="📝 Логи", callback_data="adm_logs")],
        [InlineKeyboardButton(text="🔨 Забанить канал", callback_data="adm_ban_channel")],
        [InlineKeyboardButton(text="🔨 Забанить пользователя", callback_data="adm_ban_user")],
        [InlineKeyboardButton(text="✅ Разбанить канал", callback_data="adm_unban_channel")],
        [InlineKeyboardButton(text="✅ Разбанить пользователя", callback_data="adm_unban_user")],
    ])


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в админ панель", callback_data="adm_back")]
    ])
