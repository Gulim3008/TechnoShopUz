import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_conn():
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            photo TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price TEXT NOT NULL,
            description TEXT,
            photo TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            product_id INTEGER,
            product_name TEXT,
            price TEXT,
            qty TEXT,
            customer_name TEXT,
            phone TEXT,
            user_id BIGINT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ---------- CATEGORIES ----------

def add_category(name, photo=None):
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute("INSERT INTO categories (name, photo) VALUES (%s, %s) RETURNING id", (name, photo))
    cid = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return cid


def get_categories():
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM categories ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_category(cid):
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM categories WHERE id = %s", (cid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_category(cid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE category_id = %s", (cid,))
    c.execute("DELETE FROM categories WHERE id = %s", (cid,))
    conn.commit()
    conn.close()


# ---------- PRODUCTS ----------

def add_product(category_id, name, price, description, photo=None):
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute(
        "INSERT INTO products (category_id, name, price, description, photo) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (category_id, name, price, description, photo),
    )
    pid = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return pid


def get_products_by_category(cid):
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM products WHERE category_id = %s ORDER BY id", (cid,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product(pid):
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM products WHERE id = %s", (pid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_product(pid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = %s", (pid,))
    conn.commit()
    conn.close()


# ---------- ORDERS ----------

def add_order(product_id, product_name, price, qty, customer_name, phone, user_id):
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute(
        """INSERT INTO orders (product_id, product_name, price, qty, customer_name, phone, user_id, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending') RETURNING id""",
        (product_id, product_name, price, qty, customer_name, phone, user_id),
    )
    oid = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return oid


def get_order(oid):
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM orders WHERE id = %s", (oid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_orders():
    conn = get_conn()
    c = _dict_cursor(conn)
    c.execute("SELECT * FROM orders ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_order_status(oid, status):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE orders SET status = %s WHERE id = %s", (status, oid))
    conn.commit()
    conn.close()
