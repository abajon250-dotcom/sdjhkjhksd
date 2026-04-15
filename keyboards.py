from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🛍️ Маркет", "📢 VK Рассылка")
    kb.row("💰 Баланс", "💸 Вывод средств")
    kb.row("ℹ️ Помощь")
    if is_admin:
        kb.row("👑 Админ панель")
    return kb

def admin_inline():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    kb.add(InlineKeyboardButton("📢 Глобальная рассылка", callback_data="admin_broadcast"))
    kb.add(InlineKeyboardButton("🪞 Зеркало", callback_data="admin_mirror"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    return kb

def market_inline():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Добавить товар", callback_data="add_product"))
    kb.add(InlineKeyboardButton("📋 Мои товары", callback_data="my_products"))
    kb.add(InlineKeyboardButton("📦 Мои заказы", callback_data="my_orders"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb