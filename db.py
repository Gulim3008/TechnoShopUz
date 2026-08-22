import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "shop.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            photo TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price TEXT NOT NULL,
            description TEXT,
            photo TEXT,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            product_name TEXT,
            price TEXT,
            qty TEXT,
            customer_name TEXT,
            phone TEXT,
            user_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# ---------- CATEGORIES ----------

def add_category(name, photo=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO categories (name, photo) VALUES (?, ?)", (name, photo))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid


def get_categories():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_category(cid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_category(cid):
    conn = get_conn()
    conn.execute("DELETE FROM products WHERE category_id = ?", (cid,))
    conn.execute("DELETE FROM categories WHERE id = ?", (cid,))
    conn.commit()
    conn.close()


# ---------- PRODUCTS ----------

def add_product(category_id, name, price, description, photo=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO products (category_id, name, price, description, photo) VALUES (?, ?, ?, ?, ?)",
        (category_id, name, price, description, photo),
    )
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid


def get_products_by_category(cid):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM products WHERE category_id = ? ORDER BY id", (cid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_product(pid):
    conn = get_conn()
    conn.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()


# ---------- ORDERS ----------

def add_order(product_id, product_name, price, qty, customer_name, phone, user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO orders (product_id, product_name, price, qty, customer_name, phone, user_id, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (product_id, product_name, price, qty, customer_name, phone, user_id),
    )
    conn.commit()
    oid = c.lastrowid
    conn.close()
    return oid


def get_order(oid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_orders():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_order_status(oid, status):
    conn = get_conn()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, oid))
    conn.commit()
    conn.close()
