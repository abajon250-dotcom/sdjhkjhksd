import sqlite3
from datetime import datetime, timedelta

DB_NAME = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance REAL DEFAULT 0,
        registered_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        name TEXT,
        price REAL,
        contacts INTEGER,
        description TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        buyer_id INTEGER,
        amount REAL,
        purchased_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        wallet_address TEXT,
        status TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        invoice_id TEXT,
        status TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS vk_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        token TEXT,
        group_id INTEGER,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS vk_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        text TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS blocked (
        user_id INTEGER PRIMARY KEY
    )""")
    conn.commit()
    conn.close()

# ---------- Users ----------
def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, registered_at, balance) VALUES (?,?,?,?,?)",
              (user_id, username, first_name, datetime.now().isoformat(), 0.0))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, balance, registered_at FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def get_balance(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = c.fetchone()
    conn.close()
    return bal[0] if bal else 0.0

def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def set_balance(user_id, new_balance):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = ? WHERE user_id=?", (new_balance, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def get_user_count():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count

# ---------- Products ----------
def add_product(seller_id, name, price, contacts, description):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO products (seller_id, name, price, contacts, description, created_at) VALUES (?,?,?,?,?,?)",
              (seller_id, name, price, contacts, description, datetime.now().isoformat()))
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid

def get_products(limit=10, offset=0, sort_by='new', min_contacts=0):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    order = "ORDER BY created_at DESC" if sort_by == 'new' else "ORDER BY price ASC"
    c.execute(f"""
        SELECT id, seller_id, name, price, contacts, description, created_at 
        FROM products 
        WHERE contacts >= ? 
        {order} 
        LIMIT ? OFFSET ?
    """, (min_contacts, limit, offset))
    prods = c.fetchall()
    conn.close()
    return prods

def get_total_products(min_contacts=0):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM products WHERE contacts >= ?", (min_contacts,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_product(product_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, seller_id, name, price, contacts, description FROM products WHERE id=?", (product_id,))
    prod = c.fetchone()
    conn.close()
    return prod

def get_user_products(seller_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, price, contacts, description FROM products WHERE seller_id=?", (seller_id,))
    prods = c.fetchall()
    conn.close()
    return prods

def delete_product(product_id, seller_id=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if seller_id:
        c.execute("DELETE FROM products WHERE id=? AND seller_id=?", (product_id, seller_id))
    else:
        c.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()

# ---------- Purchases ----------
def add_purchase(product_id, buyer_id, amount):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO purchases (product_id, buyer_id, amount, purchased_at) VALUES (?,?,?,?)",
              (product_id, buyer_id, amount, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_purchases(buyer_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT p.id, pr.name, pr.price, pr.contacts, pr.description, p.purchased_at 
                 FROM purchases p JOIN products pr ON p.product_id = pr.id 
                 WHERE p.buyer_id = ? ORDER BY p.purchased_at DESC""", (buyer_id,))
    purchases = c.fetchall()
    conn.close()
    return purchases

# ---------- Withdrawals ----------
def create_withdrawal(user_id, amount, wallet_address):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO withdrawals (user_id, amount, wallet_address, status, created_at) VALUES (?,?,?,?,?)",
              (user_id, amount, wallet_address, 'pending', datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_pending_withdrawals():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, user_id, amount, wallet_address FROM withdrawals WHERE status='pending'")
    withdrawals = c.fetchall()
    conn.close()
    return withdrawals

def approve_withdrawal(withdrawal_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE withdrawals SET status='completed' WHERE id=?", (withdrawal_id,))
    conn.commit()
    conn.close()

# ---------- Payments ----------
def add_payment(user_id, amount, invoice_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO payments (user_id, amount, invoice_id, status, created_at) VALUES (?,?,?,?,?)",
              (user_id, amount, invoice_id, 'pending', datetime.now().isoformat()))
    conn.commit()
    conn.close()

def confirm_payment(invoice_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE payments SET status='completed' WHERE invoice_id=?", (invoice_id,))
    conn.commit()
    conn.close()
    c.execute("SELECT user_id, amount FROM payments WHERE invoice_id=?", (invoice_id,))
    payment = c.fetchone()
    if payment:
        update_balance(payment[0], payment[1])
    conn.close()

# ---------- VK Accounts ----------
def add_vk_account(user_id, name, token, group_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO vk_accounts (user_id, name, token, group_id, created_at) VALUES (?,?,?,?,?)",
              (user_id, name, token, group_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_vk_accounts(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, token, group_id FROM vk_accounts WHERE user_id=?", (user_id,))
    accounts = c.fetchall()
    conn.close()
    return accounts

def get_vk_account(account_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, user_id, name, token, group_id FROM vk_accounts WHERE id=?", (account_id,))
    acc = c.fetchone()
    conn.close()
    return acc

def delete_vk_account(account_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM vk_accounts WHERE id=? AND user_id=?", (account_id, user_id))
    conn.commit()
    conn.close()

# ---------- VK Templates ----------
def add_vk_template(user_id, name, text):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO vk_templates (user_id, name, text, created_at) VALUES (?,?,?,?)",
              (user_id, name, text, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_vk_templates(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, text FROM vk_templates WHERE user_id=?", (user_id,))
    templates = c.fetchall()
    conn.close()
    return templates

def get_vk_template(template_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT text FROM vk_templates WHERE id=?", (template_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def delete_vk_template(template_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM vk_templates WHERE id=? AND user_id=?", (template_id, user_id))
    conn.commit()
    conn.close()

# ---------- Block ----------
def block_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO blocked (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def unblock_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM blocked WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def is_blocked(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM blocked WHERE user_id=?", (user_id,))
    blocked = c.fetchone() is not None
    conn.close()
    return blocked