from __future__ import annotations

import sqlite3
from pathlib import Path
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_user (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','customer')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS product (
  product_id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  price REAL NOT NULL CHECK (price >= 0),
  stock INTEGER NOT NULL CHECK (stock >= 0),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cart_item (
  user_id INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES product(product_id),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  PRIMARY KEY (user_id, product_id)
);
CREATE TABLE IF NOT EXISTS customer_order (
  order_id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_no TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES app_user(user_id),
  status TEXT NOT NULL CHECK (status IN ('pending_payment','paid','cancelled')),
  total_amount REAL NOT NULL CHECK (total_amount >= 0),
  idempotency_key TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS order_item (
  order_id INTEGER NOT NULL REFERENCES customer_order(order_id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES product(product_id),
  product_name TEXT NOT NULL,
  unit_price REAL NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  PRIMARY KEY(order_id, product_id)
);
CREATE TABLE IF NOT EXISTS payment (
  payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL UNIQUE REFERENCES customer_order(order_id),
  payment_no TEXT NOT NULL UNIQUE,
  amount REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES app_user(user_id),
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  detail TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def get_db():
    if "db" not in g:
        path = Path(current_app.config["DATABASE"])
        path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(_error=None):
    connection = g.pop("db", None)
    if connection:
        connection.close()

def init_db(app):
    with app.app_context():
        get_db().executescript(SCHEMA)
        get_db().commit()
