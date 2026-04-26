"""
Giveaway creation flow (Flowchart 1 - "Создать розыгрыш" branch):
1. Check if user has added a channel -> if not, ask to add first
2. Add description (text/image/gif/video)
3. Select channel to publish
4. Add button name
5. Select required channels for participation
6. Select end type (time or count)
7. Enter channels (URLs) for required subscriptions
8. Publish post, generate ref link
"""
import json
import logging
import secrets
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database.db import (
    get_user_channels, create_giveaway, get_active_giveaways,
    get_giveaway_by_id, end_giveaway, get_participants_count,
    get_random_winner, get_all_participants, get_user, log_event
)
from utils.keyboards import (
    main_menu_keyboard, back_keyboard, end_type_keyboard,
    required_channels_keyboard, giveaway_actions_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


class GiveawayStates(StatesGroup):
    waiting_description = State()
    waiting_media = State()
    waiting_channel_select = State()
    waiting_button_name = State()
    waiting_required_channels = State()
    waiting_end_type = State()
    waiting_end_value = State()


# ---- My Giveaways ----

@router.callback_query(F.data == "my_giveaways")
async def my_giveaways(callback: CallbackQuery):
    giveaways = await get_active_giveaways(callback.from_user.id)
    from database.db import get_all_user_giveaways
    all_giveaways = await get_all_user_giveaways(callback.from_user.id)

    if not all_giveaways:
        await callback.message.edit_text(
            "📋 У вас нет розыгрышей.",
            reply_markup=back_keyboard("back_main")
        )
        await callback.answer()
        return

    text = "📋 <b>Ваши розыгрыши:</b>\n\n"
    for g in all_giveaways:
        count = await get_participants_count(g["id"])
        text += (
            f"🎁 <b>ID #{g['id']}</b>\n"
            f"📢 Канал: {g['channel_id']}\n"
            f"👥 Участников: {count}\n"
            f"📅 Создан: {g['created_at'][:10]}\n"
            f"⏰ Окончание: {g.get('end_value', 'не указано')}\n"
            f"🔗 Реф. ссылка: <code>t.me/{{bot_username}}?start={g['ref_link']}</code>\n\n"
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for g in all_giveaways:
        status_icon = "✅" if g["is_active"] else "🏁"
        buttons.append([InlineKeyboardButton(
            text=f"{status_icon} Розыгрыш #{g['id']} ({g['channel_id']})",
            callback_data=f"view_giveaway:{g['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_giveaway:"))
async def view_giveaway(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[1])
    g = await get_giveaway_by_id(giveaway_id)

    if not g or g["owner_id"] != callback.from_user.id:
        await callback.answer("Розыгрыш не найден.", show_alert=True)
        return

    count = await get_participants_count(giveaway_id)
    # Winner info
    winner_line = ""
    if not g["is_active"] and g.get("winner_id"):
        winner = await get_user(g["winner_id"])
        if winner:
            wname = (winner.get("first_name") or "").strip()
            wusername = f"@{winner['username']}" if winner.get("username") else str(winner["user_id"])
            winner_line = f"\n🏆 Победитель: <a href=\"tg://user?id={winner['user_id']}\">{wname or wusername}</a> ({wusername})"
        else:
            winner_line = f"\n🏆 Победитель: id={g['winner_id']}"
    elif not g["is_active"]:
        winner_line = "\n🏆 Победитель: не определён (нет участников)"

    status = "✅ Активен" if g["is_active"] else "🏁 Завершён"
    text = (
        f"🎁 <b>Розыгрыш #{g['id']}</b> — {status}\n\n"
        f"📢 Канал: {g['channel_id']}\n"
        f"📝 Описание: {g.get('description', '—')}\n"
        f"🔘 Кнопка: {g.get('button_name', '—')}\n"
        f"👥 Участников: {count}\n"
        f"⏰ Окончание: {g.get('end_value', 'не указано')}\n"
        f"🔗 Реф. ссылка: <code>?start={g['ref_link']}</code>\n"
        f"📅 Создан: {g['created_at'][:16]}"
        + winner_line
    )

    await callback.message.edit_text(
        text,
        reply_markup=giveaway_actions_keyboard(giveaway_id, is_active=bool(g["is_active"])),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("end_giveaway:"))
async def confirm_end_giveaway(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[1])
    from utils.keyboards import confirm_keyboard
    await callback.message.edit_text(
        f"❓ Вы уверены, что хотите завершить розыгрыш #{giveaway_id}?",
        reply_markup=confirm_keyboard(f"confirm_end:{giveaway_id}", "back_main")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_end:"))
async def do_end_giveaway(callback: CallbackQuery, bot: Bot):
    giveaway_id = int(callback.data.split(":")[1])
    g = await get_giveaway_by_id(giveaway_id)
    if not g or g["owner_id"] != callback.from_user.id:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    if not g["is_active"]:
        await callback.answer("Розыгрыш уже завершён.", show_alert=True)
        return

    count = await get_participants_count(giveaway_id)

    if count == 0:
        # No participants — end without winner
        await end_giveaway(giveaway_id, callback.from_user.id, winner_id=None)
        await callback.message.edit_text(
            f"✅ Розыгрыш #{giveaway_id} завершён.\n\n"
            f"😔 Участников не было — победитель не определён.",
            reply_markup=back_keyboard("back_main")
        )
        await callback.answer()
        return

    # Pick random winner
    winner = await get_random_winner(giveaway_id)
    winner_id = winner["user_id"] if winner else None

    # Save to DB
    await end_giveaway(giveaway_id, callback.from_user.id, winner_id=winner_id)

    # Build winner display string
    if winner:
        winner_name = winner.get("first_name", "") or ""
        if winner.get("last_name"):
            winner_name += f" {winner['last_name']}"
        winner_username = f"@{winner['username']}" if winner.get("username") else f"tg://user?id={winner_id}"
        winner_mention = f'<a href="tg://user?id={winner_id}">{winner_name.strip() or winner_username}</a>'
    else:
        winner_mention = "—"

    # Post result to the giveaway channel
    channel_id = g["channel_id"]
    result_text = (
        f"🏆 <b>Розыгрыш завершён!</b>\n\n"
        f"🎉 Победитель: {winner_mention}\n\n"
        f"👥 Всего участников: {count}\n"
        f"📅 Дата завершения: {__import__('datetime').datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC"
    )

    channel_posted = False
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=result_text,
            parse_mode="HTML"
        )
        channel_posted = True
    except Exception as e:
        logger.error(f"Failed to post winner to channel {channel_id}: {e}")

    # Notify the giveaway owner
    posted_note = "✅ Результат опубликован в канале." if channel_posted else "⚠️ Не удалось опубликовать результат в канале (проверьте права бота)."
    await callback.message.edit_text(
        f"🏆 <b>Розыгрыш #{giveaway_id} завершён!</b>\n\n"
        f"🎉 Победитель: {winner_mention}\n"
        f"👥 Всего участников: {count}\n\n"
        f"{posted_note}",
        reply_markup=back_keyboard("back_main"),
        parse_mode="HTML"
    )
    await callback.answer()


# ---- Create Giveaway ----

@router.callback_query(F.data == "create_giveaway")
async def start_create_giveaway(callback: CallbackQuery, state: FSMContext):
    channels = await get_user_channels(callback.from_user.id)

    if not channels:
        # User hasn't added a channel yet
        await callback.message.edit_text(
            "⚠️ Сначала добавьте свой канал!\n\n"
            "Чтобы создать розыгрыш, нужно сначала добавить канал, "
            "в котором будет проводиться розыгрыш.",
            reply_markup=back_keyboard("back_main")
        )
        await callback.answer()
        return

    await state.update_data(channels=channels, required_channels=[])
    await state.set_state(GiveawayStates.waiting_description)
    await callback.message.edit_text(
        "📝 <b>Создание розыгрыша</b>\n\n"
        "Шаг 1/5: Добавьте описание розыгрыша.\n"
        "Вы можете отправить текст, картинку, гиф или видео.\n\n"
        "Если хотите только текст — просто напишите его.",
        reply_markup=back_keyboard("back_main"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(GiveawayStates.waiting_description)
async def get_description(message: Message, state: FSMContext):
    data = {}
    if message.text:
        data["description"] = message.text
        data["media_type"] = None
        data["media_file_id"] = None
    elif message.photo:
        data["description"] = message.caption or ""
        data["media_type"] = "photo"
        data["media_file_id"] = message.photo[-1].file_id
    elif message.animation:
        data["description"] = message.caption or ""
        data["media_type"] = "animation"
        data["media_file_id"] = message.animation.file_id
    elif message.video:
        data["description"] = message.caption or ""
        data["media_type"] = "video"
        data["media_file_id"] = message.video.file_id
    else:
        await message.answer("❌ Неподдерживаемый тип контента. Отправьте текст, фото, гиф или видео.")
        return

    await state.update_data(**data)

    # Step 2: Select channel
    channels = (await state.get_data())["channels"]
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[InlineKeyboardButton(
        text=f"📢 {ch['channel_name']}",
        callback_data=f"select_channel:{ch['channel_id']}"
    )] for ch in channels]
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="back_main")])

    await state.set_state(GiveawayStates.waiting_channel_select)
    await message.answer(
        "📢 <b>Шаг 2/5:</b> Выберите канал, в который будет опубликован розыгрыш:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(GiveawayStates.waiting_channel_select, F.data.startswith("select_channel:"))
async def select_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = callback.data.split(":")[1]
    await state.update_data(selected_channel_id=channel_id)
    await state.set_state(GiveawayStates.waiting_button_name)
    await callback.message.edit_text(
        "🔘 <b>Шаг 3/5:</b> Введите название кнопки для участия в розыгрыше.\n\n"
        "Например: «Участвовать» или «Принять участие»",
        reply_markup=back_keyboard("back_main"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(GiveawayStates.waiting_button_name)
async def get_button_name(message: Message, state: FSMContext):
    await state.update_data(button_name=message.text)

    # Step 4: Select required channels
    channels = (await state.get_data())["channels"]
    await state.set_state(GiveawayStates.waiting_required_channels)
    await message.answer(
        "📋 <b>Шаг 4/5:</b> Выберите каналы, на которые нужно быть подписанным для участия.\n\n"
        "Выберите из ваших каналов или нажмите «Готово» если условие не нужно:",
        reply_markup=required_channels_keyboard(channels),
        parse_mode="HTML"
    )


@router.callback_query(GiveawayStates.waiting_required_channels, F.data.startswith("req_channel:"))
async def select_required_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = callback.data.split(":")[1]
    data = await state.get_data()
    required = data.get("required_channels", [])

    if channel_id == "none":
        await state.update_data(required_channels=[])
    else:
        if channel_id not in required:
            required.append(channel_id)
        await state.update_data(required_channels=required)

    # Move to end type selection
    await state.set_state(GiveawayStates.waiting_end_type)
    req = (await state.get_data()).get("required_channels", [])
    req_text = f"Выбрано каналов: {len(req)}" if req else "Без обязательных каналов"

    await callback.message.edit_text(
        f"⏱ <b>Шаг 5/5:</b> Выберите способ завершения набора участников.\n\n{req_text}",
        reply_markup=end_type_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(GiveawayStates.waiting_end_type, F.data.startswith("end_type:"))
async def select_end_type(callback: CallbackQuery, state: FSMContext):
    end_type = callback.data.split(":")[1]
    await state.update_data(end_type=end_type)
    await state.set_state(GiveawayStates.waiting_end_value)

    if end_type == "time":
        await callback.message.edit_text(
            "📅 Введите дату и время окончания розыгрыша.\n\n"
            "Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "Например: <code>31.12.2025 23:59</code>",
            reply_markup=back_keyboard("back_main"),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            "👥 Введите максимальное количество участников:",
            reply_markup=back_keyboard("back_main"),
            parse_mode="HTML"
        )
    await callback.answer()


@router.message(GiveawayStates.waiting_end_value)
async def get_end_value(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    end_type = data.get("end_type")

    if end_type == "time":
        try:
            dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
            end_value = dt.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
            return
    else:
        if not message.text.strip().isdigit():
            await message.answer("❌ Введите число участников.")
            return
        end_value = message.text.strip()

    # Generate unique ref token
    ref_token = secrets.token_urlsafe(12)

    # Prepare giveaway data
    required_channels = data.get("required_channels", [])
    giveaway_data = {
        "owner_id": message.from_user.id,
        "channel_id": data["selected_channel_id"],
        "description": data.get("description"),
        "media_type": data.get("media_type"),
        "media_file_id": data.get("media_file_id"),
        "button_name": data.get("button_name", "Участвовать"),
        "required_channels": json.dumps(required_channels) if required_channels else None,
        "end_type": end_type,
        "end_value": end_value,
        "ref_link": ref_token,
    }

    giveaway_id = await create_giveaway(giveaway_data)

    # Get bot info to build ref link
    bot_info = await bot.get_me()
    ref_url = f"https://t.me/{bot_info.username}?start={ref_token}"

    # Notify user
    await state.clear()
    await message.answer(
        f"✅ <b>Розыгрыш будет опубликован в выбранном канале!</b>\n\n"
        f"🎁 ID розыгрыша: #{giveaway_id}\n"
        f"📢 Канал: {data['selected_channel_id']}\n"
        f"⏰ Окончание: {end_value}\n"
        f"👥 Обязательных каналов: {len(required_channels)}\n\n"
        f"🔗 Реф. ссылка для публикации:\n<code>{ref_url}</code>\n\n"
        f"Опубликуйте пост в вашем канале с кнопкой «{data.get('button_name', 'Участвовать')}», "
        f"добавив эту ссылку как реф. ссылку для перехода пользователя.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )

    # Publish to channel
    channel_id = data["selected_channel_id"]
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    post_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=data.get("button_name", "Участвовать"),
            url=ref_url
        )]
    ])

    try:
        caption = data.get("description", "🎁 Розыгрыш!")
        if data.get("media_type") == "photo":
            await bot.send_photo(
                chat_id=channel_id,
                photo=data["media_file_id"],
                caption=caption,
                reply_markup=post_keyboard
            )
        elif data.get("media_type") == "animation":
            await bot.send_animation(
                chat_id=channel_id,
                animation=data["media_file_id"],
                caption=caption,
                reply_markup=post_keyboard
            )
        elif data.get("media_type") == "video":
            await bot.send_video(
                chat_id=channel_id,
                video=data["media_file_id"],
                caption=caption,
                reply_markup=post_keyboard
            )
        else:
            await bot.send_message(
                chat_id=channel_id,
                text=caption,
                reply_markup=post_keyboard
            )
        await log_event("giveaway_published", message.from_user.id,
                        f"giveaway_id={giveaway_id} channel={channel_id}")
    except Exception as e:
        logger.error(f"Failed to publish giveaway to channel: {e}")
        await message.answer(
            f"⚠️ Не удалось опубликовать пост в канал автоматически.\n"
            f"Убедитесь, что бот является администратором канала.\n"
            f"Ошибка: {e}"
        )
