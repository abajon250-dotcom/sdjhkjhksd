import asyncio
import logging
import sys
import requests
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import vk_api
from config import BOT_TOKEN, ADMIN_IDS, REQUIRED_CHANNEL_ID, ADMIN_LOG_CHAT_ID, CRYPTOBOT_API_TOKEN
from database import *

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== КАСТОМНЫЕ ЭМОДЗИ (твои ID) ==========
EMOJI_IDS = {
    "catalog": "5278613311858959074",
    "add": "5206401524200145033",
    "balance": "5276398496008663230",
    "withdraw": "5206476089127372379",
    "vk": "5278411813468269386",
    "admin": "5276412364458059956",
    "back": "5206476089127372379",
    "success": "5260399854500191689",
    "error": "5278578973595427038",
    "buy": "5195058841988914267",
    "delete": "5276442772826515132",
    "home": "5278413853577734640",
}

def custom_emoji_button(text: str, callback_data: str, emoji_id: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data, icon_custom_emoji_id=emoji_id)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def ensure_subscribed(message: types.Message) -> bool:
    if await is_subscribed(message.from_user.id):
        return True
    await message.answer(f"❌ Подпишитесь на канал {REQUIRED_CHANNEL_ID}\nПосле подписки нажмите /start")
    return False

async def log_to_admin(text: str):
    if ADMIN_LOG_CHAT_ID:
        try:
            await bot.send_message(ADMIN_LOG_CHAT_ID, text)
        except:
            pass

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ========== ГЛАВНОЕ МЕНЮ ==========
def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="Каталог"), KeyboardButton(text="Добавить товар")],
        [KeyboardButton(text="Баланс"), KeyboardButton(text="Вывод средств")],
        [KeyboardButton(text="Помощь")],
    ]
    if is_admin(user_id):
        kb.append([KeyboardButton(text="Админ панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы.")
        return
    if not await is_subscribed(message.from_user.id):
        await message.answer(f"❌ Подпишитесь на канал {REQUIRED_CHANNEL_ID}\nПосле подписки нажмите /start")
        return
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await log_to_admin(f"➕ Новый пользователь: {message.from_user.id} (@{message.from_user.username})")
    await message.answer("✅ Добро пожаловать!", reply_markup=main_menu(message.from_user.id))

# ========== БАЛАНС И ВЫВОД ==========
@dp.message(lambda m: m.text == "Баланс")
async def show_balance(message: types.Message):
    if not await ensure_subscribed(message):
        return
    balance = get_balance(message.from_user.id)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [custom_emoji_button("Пополнить баланс", "topup_balance", EMOJI_IDS["balance"])],
        [custom_emoji_button("Вывести средства", "withdraw_balance", EMOJI_IDS["withdraw"])],
    ])
    await message.answer(f"💰 Ваш баланс: {balance:.2f} $\n\nПополнение через CryptoBot (USDT).", reply_markup=markup)

class TopUpState(StatesGroup):
    amount = State()

@dp.callback_query(lambda c: c.data == "topup_balance")
async def topup_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите сумму пополнения в USD (минимум 1):")
    await state.set_state(TopUpState.amount)
    await callback.answer()

@dp.message(TopUpState.amount)
async def topup_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < 1:
            raise ValueError
        url = "https://pay.crypt.bot/api/createInvoice"
        headers = {"Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN}
        data = {"asset": "USDT", "amount": str(amount), "description": f"Пополнение {message.from_user.id}"}
        resp = requests.post(url, headers=headers, json=data).json()
        if resp.get("ok"):
            invoice = resp["result"]
            invoice_id = invoice["invoice_id"]
            add_payment(message.from_user.id, amount, invoice_id)
            await message.answer(f"💳 Счёт на {amount} USDT создан.\nОплатите: {invoice['bot_invoice_url']}\n\nПосле оплаты баланс пополнится автоматически.")
            asyncio.create_task(check_payment_status(message.from_user.id, invoice_id, amount))
        else:
            await message.answer("❌ Ошибка создания счёта.")
    except:
        await message.answer("❌ Неверная сумма. Введите число >0.")
    await state.clear()

async def check_payment_status(user_id, invoice_id, amount):
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN}
    params = {"invoice_ids": invoice_id}
    for _ in range(60):
        await asyncio.sleep(10)
        resp = requests.get(url, headers=headers, params=params).json()
        if resp.get("ok") and resp["result"]["items"]:
            invoice = resp["result"]["items"][0]
            if invoice["status"] == "paid":
                confirm_payment(invoice_id)
                await bot.send_message(user_id, f"✅ Баланс пополнен на {amount} USDT!")
                await log_to_admin(f"💰 Пользователь {user_id} пополнил баланс на {amount} USDT")
                break
            elif invoice["status"] == "expired":
                await bot.send_message(user_id, f"❌ Счёт истёк. Попробуйте ещё раз.")
                break

class WithdrawState(StatesGroup):
    amount = State()
    address = State()

@dp.callback_query(lambda c: c.data == "withdraw_balance")
async def withdraw_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите сумму вывода (минимум 1 $):")
    await state.set_state(WithdrawState.amount)
    await callback.answer()

@dp.message(WithdrawState.amount)
async def withdraw_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < 1:
            raise ValueError
        bal = get_balance(message.from_user.id)
        if bal < amount:
            await message.answer("❌ Недостаточно средств.")
            await state.clear()
            return
        await state.update_data(amount=amount)
        await message.answer("Введите адрес кошелька USDT (TRC20):")
        await state.set_state(WithdrawState.address)
    except:
        await message.answer("❌ Неверная сумма.")
        await state.clear()

@dp.message(WithdrawState.address)
async def withdraw_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    data = await state.get_data()
    amount = data["amount"]
    create_withdrawal(message.from_user.id, amount, address)
    await message.answer(f"✅ Заявка на вывод {amount} $ создана. Администратор обработает.")
    await log_to_admin(f"💸 Заявка на вывод от {message.from_user.id}: {amount} $ на адрес {address}")
    await state.clear()

# ========== КАТАЛОГ (ТОЧЬ-В-ТОЧЬ) ==========
user_catalog = {}

@dp.message(lambda m: m.text == "Каталог")
async def catalog(message: types.Message):
    if not await ensure_subscribed(message):
        return
    chat_id = message.chat.id
    user_catalog[chat_id] = {'page': 0, 'sort': 'new', 'min_contacts': 0, 'last_msg_id': None}
    await show_catalog(message)

async def show_catalog(message: types.Message, edit_msg_id: int = None):
    chat_id = message.chat.id
    state = user_catalog.get(chat_id, {'page': 0, 'sort': 'new', 'min_contacts': 0})
    page = state['page']
    sort = state['sort']
    min_contacts = state['min_contacts']
    limit = 6
    offset = page * limit
    products = get_products(limit, offset, sort, min_contacts)
    total = get_total_products(min_contacts)
    if not products:
        text = "📭 В каталоге пока нет товаров."
        if edit_msg_id:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_msg_id)
        else:
            await message.answer(text)
        return

    text = "📋 <b>Каталог аккаунтов</b>\n\n"
    for p in products:
        pid, _, name, price, contacts, _, _ = p
        text += f"🔹 <b>{name}</b>\n💰 {price}$ • Контактов: {contacts}\n\n"
    total_pages = max(1, (total + limit - 1) // limit)
    text += f"📄 Страница {page+1} / {total_pages}"

    filter_btn = [custom_emoji_button("Фильтры поиска", "filters", EMOJI_IDS["catalog"])]
    product_btns = [custom_emoji_button(f"{p[4]} конт. • {p[3]}$", f"view_{p[0]}", EMOJI_IDS["catalog"]) for p in products]
    nav = []
    if page > 0:
        nav.append(custom_emoji_button("◀ Назад", "prev", EMOJI_IDS["back"]))
    if (page+1)*limit < total:
        nav.append(custom_emoji_button("Вперед ▶", "next", EMOJI_IDS["back"]))
    back_btn = [custom_emoji_button("Назад", "back_menu", EMOJI_IDS["back"])]

    inline_kb = filter_btn + [[btn] for btn in product_btns] + [nav] + back_btn
    markup = InlineKeyboardMarkup(inline_keyboard=inline_kb)
    if edit_msg_id:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_msg_id, parse_mode="HTML", reply_markup=markup)
        state['last_msg_id'] = edit_msg_id
    else:
        sent = await message.answer(text, parse_mode="HTML", reply_markup=markup)
        state['last_msg_id'] = sent.message_id
    user_catalog[chat_id] = state

@dp.callback_query(lambda c: c.data == "filters")
async def show_filters(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    state = user_catalog.get(chat_id)
    if not state or not state.get('last_msg_id'):
        await callback.answer("Ошибка, попробуйте снова /start")
        return
    last_msg_id = state['last_msg_id']
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [custom_emoji_button("Сначала новые", "sort_new", EMOJI_IDS["catalog"])],
        [custom_emoji_button("Сначала дешёвые", "sort_price", EMOJI_IDS["catalog"])],
        [custom_emoji_button("Контакты от 40 шт.", "filter_contacts", EMOJI_IDS["catalog"])],
        [custom_emoji_button("Назад", "back_catalog", EMOJI_IDS["back"])],
    ])
    await bot.edit_message_text("Фильтры поиска", chat_id=chat_id, message_id=last_msg_id, reply_markup=markup)
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["sort_new", "sort_price", "filter_contacts", "prev", "next", "back_catalog"])
async def catalog_handlers(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    if chat_id not in user_catalog:
        user_catalog[chat_id] = {'page': 0, 'sort': 'new', 'min_contacts': 0, 'last_msg_id': None}
    if callback.data == "sort_new":
        user_catalog[chat_id]['sort'] = 'new'
        user_catalog[chat_id]['page'] = 0
        await show_catalog(callback.message, edit_msg_id=user_catalog[chat_id]['last_msg_id'])
    elif callback.data == "sort_price":
        user_catalog[chat_id]['sort'] = 'price'
        user_catalog[chat_id]['page'] = 0
        await show_catalog(callback.message, edit_msg_id=user_catalog[chat_id]['last_msg_id'])
    elif callback.data == "filter_contacts":
        await callback.message.answer("Введите минимальное количество контактов (число):")
        await state.set_state("waiting_contacts")
    elif callback.data == "prev":
        user_catalog[chat_id]['page'] -= 1
        await show_catalog(callback.message, edit_msg_id=user_catalog[chat_id]['last_msg_id'])
    elif callback.data == "next":
        user_catalog[chat_id]['page'] += 1
        await show_catalog(callback.message, edit_msg_id=user_catalog[chat_id]['last_msg_id'])
    elif callback.data == "back_catalog":
        await show_catalog(callback.message, edit_msg_id=user_catalog[chat_id]['last_msg_id'])
    await callback.answer()

@dp.message(State("waiting_contacts"))
async def set_contacts_filter(message: types.Message, state: FSMContext):
    try:
        min_contacts = int(message.text)
        if min_contacts < 0:
            raise ValueError
        chat_id = message.chat.id
        if chat_id not in user_catalog:
            user_catalog[chat_id] = {'page': 0, 'sort': 'new', 'min_contacts': 0, 'last_msg_id': None}
        user_catalog[chat_id]['min_contacts'] = min_contacts
        user_catalog[chat_id]['page'] = 0
        await show_catalog(message, edit_msg_id=user_catalog[chat_id]['last_msg_id'])
    except:
        await message.answer("❌ Введите целое неотрицательное число.")
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("view_"))
async def view_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    prod = get_product(product_id)
    if not prod:
        await callback.answer("Товар не найден")
        return
    pid, seller_id, name, price, contacts, desc = prod
    seller = get_user(seller_id)
    seller_name = seller[1] or seller[2] or str(seller_id) if seller else str(seller_id)
    text = (f"📦 <b>{name}</b>\n\n"
            f"💰 Цена: {price} $\n"
            f"📞 Контактов: {contacts}\n"
            f"📝 Описание: {desc}\n"
            f"👤 Продавец: {seller_name}")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [custom_emoji_button("Купить", f"buy_{pid}", EMOJI_IDS["buy"])],
        [custom_emoji_button("Назад", "back_catalog", EMOJI_IDS["back"])]
    ])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    prod = get_product(product_id)
    if not prod:
        await callback.answer("Товар не найден")
        return
    pid, seller_id, name, price, contacts, desc = prod
    buyer_id = callback.from_user.id
    if buyer_id == seller_id:
        await callback.answer("❌ Нельзя купить свой товар")
        return
    balance = get_balance(buyer_id)
    if balance >= price:
        update_balance(buyer_id, -price)
        update_balance(seller_id, price)
        add_purchase(product_id, buyer_id, price)
        delete_product(product_id)
        await callback.message.answer(f"✅ Вы купили {name} за {price}$\nТовар удалён из каталога.")
        await bot.send_message(seller_id, f"💰 Ваш товар {name} куплен за {price}$. Баланс пополнен. Товар удалён.")
        await log_to_admin(f"🛒 Покупка: {buyer_id} купил у {seller_id} товар {name} за {price}$. Товар удалён.")
        await callback.answer("Покупка успешна!", show_alert=True)
    else:
        await callback.message.answer(f"❌ Недостаточно средств\nДоступно: {balance:.2f} $")
        await callback.answer()

# ========== ДОБАВЛЕНИЕ ТОВАРА ==========
class AddProductState(StatesGroup):
    name = State()
    price = State()
    contacts = State()
    desc = State()

@dp.message(lambda m: m.text == "Добавить товар")
async def add_product_start(message: types.Message, state: FSMContext):
    if not await ensure_subscribed(message):
        return
    await message.answer("Введите название товара:")
    await state.set_state(AddProductState.name)

@dp.message(AddProductState.name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите цену в $ (число):")
    await state.set_state(AddProductState.price)

@dp.message(AddProductState.price)
async def add_product_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        await state.update_data(price=price)
        await message.answer("Введите количество контактов (число):")
        await state.set_state(AddProductState.contacts)
    except:
        await message.answer("Цена должна быть положительным числом. Повторите:")

@dp.message(AddProductState.contacts)
async def add_product_contacts(message: types.Message, state: FSMContext):
    try:
        contacts = int(message.text)
        if contacts < 0:
            raise ValueError
        await state.update_data(contacts=contacts)
        await message.answer("Введите описание товара:")
        await state.set_state(AddProductState.desc)
    except:
        await message.answer("Контакты должны быть целым неотрицательным числом. Повторите:")

@dp.message(AddProductState.desc)
async def add_product_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_product(message.from_user.id, data["name"], data["price"], data["contacts"], message.text)
    await message.answer(f"✅ Товар «{data['name']}» добавлен!")
    await log_to_admin(f"🆕 Новый товар от {message.from_user.id}: {data['name']} за {data['price']}$")
    await state.clear()

# ========== VK РАССЫЛКА (полная) ==========
class VKAddAccountState(StatesGroup):
    name = State()
    token = State()
    group_choice = State()

class VKTemplateState(StatesGroup):
    name = State()
    text = State()

class VKBroadcastState(StatesGroup):
    account_id = State()
    text = State()

@dp.message(lambda m: m.text == "VK Рассылка")
async def vk_menu(message: types.Message):
    if not await ensure_subscribed(message):
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить аккаунт VK"), KeyboardButton(text="Мои аккаунты")],
            [KeyboardButton(text="Шаблоны сообщений"), KeyboardButton(text="Запустить рассылку")],
            [KeyboardButton(text="Главное меню")],
        ],
        resize_keyboard=True
    )
    await message.answer("📢 VK Рассылка", reply_markup=kb)

@dp.message(lambda m: m.text == "Добавить аккаунт VK")
async def add_vk_account_start(message: types.Message, state: FSMContext):
    if not await ensure_subscribed(message):
        return
    await message.answer("Введите название аккаунта (например, 'Мой бот'):")
    await state.set_state(VKAddAccountState.name)

@dp.message(VKAddAccountState.name)
async def vk_acc_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите токен доступа VK (сообщества):")
    await state.set_state(VKAddAccountState.token)

@dp.message(VKAddAccountState.token)
async def vk_acc_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    try:
        vk_session = vk_api.VkApi(token=token)
        vk = vk_session.get_api()
        groups = vk.groups.get(extended=1, filter='admin')
        if not groups['items']:
            await message.answer("❌ По этому токену нет доступных групп (вы не администратор).")
            await state.clear()
            return
        await state.update_data(token=token)
        if len(groups['items']) == 1:
            group = groups['items'][0]
            group_id = group['id']
            data = await state.get_data()
            add_vk_account(message.from_user.id, data["name"], token, group_id)
            await message.answer(f"✅ Аккаунт «{data['name']}» добавлен для группы {group['name']} (ID {group_id})")
            await state.clear()
        else:
            markup = InlineKeyboardMarkup()
            for g in groups['items']:
                markup.add(InlineKeyboardButton(text=g['name'], callback_data=f"vk_group_{g['id']}"))
            await message.answer("Найдено несколько групп. Выберите:", reply_markup=markup)
            await state.set_state(VKAddAccountState.group_choice)
    except Exception as e:
        await message.answer(f"❌ Ошибка проверки токена: {e}")
        await state.clear()

@dp.callback_query(VKAddAccountState.group_choice)
async def vk_choose_group(callback: types.CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    add_vk_account(callback.from_user.id, data["name"], data["token"], group_id)
    await callback.message.answer(f"✅ Аккаунт «{data['name']}» добавлен для группы {group_id}")
    await state.clear()
    await callback.answer()

@dp.message(lambda m: m.text == "Мои аккаунты")
async def list_vk_accounts(message: types.Message):
    if not await ensure_subscribed(message):
        return
    accounts = get_vk_accounts(message.from_user.id)
    if not accounts:
        await message.answer("У вас нет добавленных аккаунтов VK.")
        return
    text = "📋 Ваши аккаунты VK:\n"
    for acc in accounts:
        acc_id, name, token, gid = acc
        text += f"🔹 {name} (ID {acc_id}, группа {gid})\n"
    text += "\n🗑 Удалить: /del_vk <id>"
    await message.answer(text)

@dp.message(Command("del_vk"))
async def delete_vk_account_cmd(message: types.Message):
    if not await ensure_subscribed(message):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /del_vk <id_аккаунта>")
        return
    try:
        acc_id = int(args[1])
        delete_vk_account(acc_id, message.from_user.id)
        await message.answer("✅ Аккаунт удалён.")
    except:
        await message.answer("❌ Ошибка.")

@dp.message(lambda m: m.text == "Шаблоны сообщений")
async def templates_menu(message: types.Message):
    if not await ensure_subscribed(message):
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [custom_emoji_button("Создать шаблон", "create_template", EMOJI_IDS["add"])],
        [custom_emoji_button("Мои шаблоны", "my_templates", EMOJI_IDS["catalog"])],
    ])
    await message.answer("📝 Управление шаблонами", reply_markup=markup)

@dp.callback_query(lambda c: c.data == "create_template")
async def create_template_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название шаблона:")
    await state.set_state(VKTemplateState.name)
    await callback.answer()

@dp.message(VKTemplateState.name)
async def tpl_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите текст шаблона (можно с HTML):")
    await state.set_state(VKTemplateState.text)

@dp.message(VKTemplateState.text)
async def tpl_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_vk_template(message.from_user.id, data["name"], message.text)
    await message.answer(f"✅ Шаблон «{data['name']}» сохранён.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "my_templates")
async def my_templates(callback: types.CallbackQuery):
    templates = get_vk_templates(callback.from_user.id)
    if not templates:
        await callback.message.answer("У вас нет шаблонов.")
        return
    text = "📋 Ваши шаблоны:\n"
    for t in templates:
        tid, name, content = t
        text += f"🔹 {name} (ID {tid})\n"
    text += "\n🗑 Удалить: /del_template <id>"
    await callback.message.answer(text)
    await callback.answer()

@dp.message(Command("del_template"))
async def delete_template_cmd(message: types.Message):
    if not await ensure_subscribed(message):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /del_template <id_шаблона>")
        return
    try:
        tid = int(args[1])
        delete_vk_template(tid, message.from_user.id)
        await message.answer("✅ Шаблон удалён.")
    except:
        await message.answer("❌ Ошибка.")

@dp.message(lambda m: m.text == "Запустить рассылку")
async def start_broadcast(message: types.Message, state: FSMContext):
    if not await ensure_subscribed(message):
        return
    accounts = get_vk_accounts(message.from_user.id)
    if not accounts:
        await message.answer("❌ Сначала добавьте аккаунт VK через «Добавить аккаунт VK».")
        return
    markup = InlineKeyboardMarkup()
    for acc in accounts:
        acc_id, name, _, _ = acc
        markup.add(InlineKeyboardButton(text=name, callback_data=f"broadcast_acc_{acc_id}"))
    await message.answer("📢 Выберите аккаунт VK для рассылки:", reply_markup=markup)

@dp.callback_query(lambda c: c.data.startswith("broadcast_acc_"))
async def choose_account(callback: types.CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[2])
    await state.update_data(account_id=acc_id)
    templates = get_vk_templates(callback.from_user.id)
    markup = InlineKeyboardMarkup()
    for t in templates:
        tid, name, _ = t
        markup.add(InlineKeyboardButton(text=f"📄 {name}", callback_data=f"broadcast_tpl_{tid}"))
    markup.add(InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="broadcast_manual"))
    await callback.message.answer("📝 Выберите шаблон или введите текст вручную:", reply_markup=markup)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("broadcast_tpl_"))
async def broadcast_with_template(callback: types.CallbackQuery, state: FSMContext):
    tpl_id = int(callback.data.split("_")[2])
    text = get_vk_template(tpl_id)
    if not text:
        await callback.answer("Шаблон не найден")
        return
    data = await state.get_data()
    acc_id = data.get("account_id")
    if not acc_id:
        await callback.message.answer("❌ Ошибка: выберите аккаунт заново.")
        return
    await do_vk_broadcast(callback.message.chat.id, callback.from_user.id, acc_id, text)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "broadcast_manual")
async def broadcast_manual(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Введите текст сообщения для рассылки (можно с HTML):")
    await state.set_state(VKBroadcastState.text)
    await callback.answer()

@dp.message(VKBroadcastState.text)
async def broadcast_manual_text(message: types.Message, state: FSMContext):
    text = message.text
    data = await state.get_data()
    acc_id = data.get("account_id")
    if not acc_id:
        await message.answer("❌ Ошибка: сессия истекла, начните заново.")
        await state.clear()
        return
    await do_vk_broadcast(message.chat.id, message.from_user.id, acc_id, text)
    await state.clear()

async def do_vk_broadcast(chat_id, user_id, account_id, text):
    acc = get_vk_account(account_id)
    if not acc:
        await bot.send_message(chat_id, "❌ Аккаунт не найден.")
        return
    _, owner_id, name, token, group_id = acc
    if owner_id != user_id:
        await bot.send_message(chat_id, "❌ Это не ваш аккаунт.")
        return
    try:
        vk_session = vk_api.VkApi(token=token)
        vk = vk_session.get_api()
        members = vk.groups.getMembers(group_id=group_id)['items']
        if not members:
            await bot.send_message(chat_id, "📭 В группе нет участников.")
            return
        sent = 0
        msg = await bot.send_message(chat_id, f"🚀 Начинаю рассылку для {len(members)} участников...")
        for uid in members:
            try:
                vk.messages.send(user_id=uid, message=text, random_id=0)
                sent += 1
                await asyncio.sleep(0.1)
            except:
                pass
        await msg.edit_text(f"✅ Рассылка завершена. Отправлено: {sent}")
        await log_to_admin(f"📢 Пользователь {user_id} запустил рассылку через аккаунт {name}, отправлено {sent}")
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка VK: {e}")

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(lambda m: m.text == "Админ панель" and is_admin(m.from_user.id))
async def admin_panel(message: types.Message):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [custom_emoji_button("Статистика", "stats", EMOJI_IDS["admin"])],
        [custom_emoji_button("Пользователи", "users", EMOJI_IDS["admin"])],
        [custom_emoji_button("Выдать баланс", "give", EMOJI_IDS["balance"])],
        [custom_emoji_button("Заявки на вывод", "withdraws", EMOJI_IDS["withdraw"])],
        [custom_emoji_button("Управление товарами", "products", EMOJI_IDS["catalog"])],
        [custom_emoji_button("Заблокировать", "block", EMOJI_IDS["delete"])],
        [custom_emoji_button("Разблокировать", "unblock", EMOJI_IDS["success"])],
        [custom_emoji_button("Рассылка", "broadcast", EMOJI_IDS["vk"])],
        [custom_emoji_button("Зеркало", "mirror", EMOJI_IDS["admin"])],
        [custom_emoji_button("Назад", "back_menu", EMOJI_IDS["back"])],
    ])
    await message.answer("🔧 Админ панель", reply_markup=markup)

@dp.callback_query(lambda c: c.data == "stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    users = get_user_count()
    products = len(get_products(limit=9999))
    await callback.message.answer(f"📊 Статистика:\n👥 Пользователей: {users}\n📦 Товаров: {products}")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "users")
async def admin_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    users = get_all_users()
    if not users:
        await callback.message.answer("Список пользователей пуст.")
    else:
        text = "👥 Список пользователей:\n" + "\n".join(str(uid) for uid in users)
        await callback.message.answer(text)
    await callback.answer()

class AdminGive(StatesGroup):
    data = State()

@dp.callback_query(lambda c: c.data == "give")
async def admin_give_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    await callback.message.answer("Введите ID и сумму через пробел (например 123456 10):")
    await state.set_state(AdminGive.data)
    await callback.answer()

@dp.message(AdminGive.data)
async def admin_give_exec(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        amount = float(parts[1])
        if amount <= 0:
            raise ValueError
        update_balance(user_id, amount)
        await message.answer(f"✅ Пользователю {user_id} начислено {amount} $")
        await bot.send_message(user_id, f"💰 Администратор начислил вам {amount} $")
        await log_to_admin(f"💰 Админ {message.from_user.id} начислил {user_id} {amount} $")
    except:
        await message.answer("❌ Ошибка. Используйте: ID сумма (положительное число)")
    await state.clear()

@dp.callback_query(lambda c: c.data == "withdraws")
async def admin_withdrawals(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    withdrawals = get_pending_withdrawals()
    if not withdrawals:
        await callback.message.answer("📭 Нет заявок на вывод.")
        return
    for w in withdrawals:
        wid, uid, amount, addr = w
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [custom_emoji_button("✅ Выполнено", f"approve_wd_{wid}", EMOJI_IDS["success"])]
        ])
        await callback.message.answer(f"Заявка #{wid}\nОт пользователя {uid}\nСумма: {amount} $\nАдрес: {addr}", reply_markup=markup)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("approve_wd_"))
async def approve_withdrawal_cmd(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    wid = int(callback.data.split("_")[2])
    approve_withdrawal(wid)
    await callback.message.answer(f"✅ Заявка #{wid} помечена как выполненная.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "products")
async def admin_products(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    products = get_products(limit=9999)
    if not products:
        await callback.message.answer("Нет товаров.")
        return
    text = "📦 Список товаров:\n"
    for p in products:
        pid, seller_id, name, price, contacts, desc, _ = p
        text += f"ID {pid}: {name} - {price}$ (конт. {contacts}) от {seller_id}\n"
    text += "\nУдалить: /del_product <id>"
    await callback.message.answer(text)
    await callback.answer()

@dp.message(Command("del_product"))
async def del_product_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /del_product <id_товара>")
        return
    try:
        pid = int(args[1])
        delete_product(pid)
        await message.answer(f"✅ Товар {pid} удалён.")
        await log_to_admin(f"🗑 Админ {message.from_user.id} удалил товар {pid}")
    except:
        await message.answer("❌ Ошибка.")

class AdminBlock(StatesGroup):
    user_id = State()

@dp.callback_query(lambda c: c.data == "block")
async def admin_block_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    await callback.message.answer("Введите ID пользователя для блокировки:")
    await state.set_state(AdminBlock.user_id)
    await callback.answer()

@dp.message(AdminBlock.user_id)
async def admin_block_exec(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        block_user(uid)
        await message.answer(f"✅ Пользователь {uid} заблокирован")
        await bot.send_message(uid, "❌ Вы заблокированы администратором.")
        await log_to_admin(f"🔒 Админ {message.from_user.id} заблокировал {uid}")
    except:
        await message.answer("❌ Ошибка. Введите числовой ID.")
    await state.clear()

class AdminUnblock(StatesGroup):
    user_id = State()

@dp.callback_query(lambda c: c.data == "unblock")
async def admin_unblock_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    await callback.message.answer("Введите ID пользователя для разблокировки:")
    await state.set_state(AdminUnblock.user_id)
    await callback.answer()

@dp.message(AdminUnblock.user_id)
async def admin_unblock_exec(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        unblock_user(uid)
        await message.answer(f"✅ Пользователь {uid} разблокирован")
        await bot.send_message(uid, "✅ Вы разблокированы.")
        await log_to_admin(f"🔓 Админ {message.from_user.id} разблокировал {uid}")
    except:
        await message.answer("❌ Ошибка.")
    await state.clear()

class AdminBroadcast(StatesGroup):
    text = State()

@dp.callback_query(lambda c: c.data == "broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    await callback.message.answer("Введите текст рассылки (можно с HTML):")
    await state.set_state(AdminBroadcast.text)
    await callback.answer()

@dp.message(AdminBroadcast.text)
async def admin_broadcast_exec(message: types.Message, state: FSMContext):
    text = message.html_text
    users = get_all_users()
    sent = 0
    await message.answer(f"Начинаю рассылку для {len(users)} пользователей...")
    for uid in users:
        if is_blocked(uid):
            continue
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Рассылка завершена. Отправлено: {sent}")
    await log_to_admin(f"📢 Админ {message.from_user.id} сделал рассылку, отправлено {sent}")
    await state.clear()

# ========== ЗЕРКАЛО (РАБОЧЕЕ) ==========
mirror_process = None

def start_mirror(token):
    global mirror_process
    if mirror_process and mirror_process.poll() is None:
        return False, "Зеркало уже запущено"
    env = os.environ.copy()
    env["BOT_TOKEN"] = token
    try:
        mirror_process = subprocess.Popen([sys.executable, __file__, "--mirror", token], env=env)
        return True, f"Зеркало запущено (PID {mirror_process.pid})"
    except Exception as e:
        return False, f"Ошибка: {e}"

def stop_mirror():
    global mirror_process
    if mirror_process and mirror_process.poll() is None:
        mirror_process.terminate()
        mirror_process.wait()
        mirror_process = None
        return "Зеркало остановлено"
    return "Зеркало не запущено"

def mirror_status():
    return mirror_process is not None and mirror_process.poll() is None

@dp.callback_query(lambda c: c.data == "mirror")
async def admin_mirror(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    status = "🟢 Запущено" if mirror_status() else "🔴 Остановлено"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [custom_emoji_button("Запустить зеркало", "mirror_start", EMOJI_IDS["success"])],
        [custom_emoji_button("Остановить зеркало", "mirror_stop", EMOJI_IDS["delete"])],
        [custom_emoji_button("Назад", "back_menu", EMOJI_IDS["back"])],
    ])
    await callback.message.answer(f"🪞 Зеркало бота: {status}", reply_markup=markup)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "mirror_start")
async def mirror_start_cmd(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    await callback.message.answer("Введите токен нового бота (от @BotFather):")
    await state.set_state("mirror_token")
    await callback.answer()

@dp.message(State("mirror_token"))
async def mirror_token_set(message: types.Message, state: FSMContext):
    token = message.text.strip()
    success, msg = start_mirror(token)
    await message.answer(f"{'✅' if success else '❌'} {msg}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "mirror_stop")
async def mirror_stop_cmd(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    msg = stop_mirror()
    await callback.message.answer(f"🪞 {msg}")
    await callback.answer()

# ========== ПОМОЩЬ И НАЗАД ==========
@dp.message(lambda m: m.text == "Помощь")
async def help_cmd(message: types.Message):
    if not await ensure_subscribed(message):
        return
    await message.answer("📖 Команды бота:\n/start - главное меню\nКаталог - список товаров\nДобавить товар - выставить свой товар\nБаланс - ваш баланс\nВывод средств - заявка на вывод\nАдмин панель - для администраторов")

@dp.message(lambda m: m.text == "Главное меню")
async def back_to_main(message: types.Message):
    if not await ensure_subscribed(message):
        return
    await message.answer("Главное меню", reply_markup=main_menu(message.from_user.id))

@dp.callback_query(lambda c: c.data == "back_menu")
async def back_menu(callback: types.CallbackQuery):
    await callback.message.answer("Главное меню", reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import subprocess, os
    if len(sys.argv) > 1 and sys.argv[1] == "--mirror":
        token = sys.argv[2]
        bot = Bot(token=token)
        asyncio.run(main())
    else:
        asyncio.run(main())