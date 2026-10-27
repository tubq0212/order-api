from __future__ import annotations

import json
import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import close_db, get_db, init_db


def response(code, message, data=None, status=None):
    return jsonify({"code": code, "message": message, "data": data}), status or code

def error(status, message):
    return response(status, message, None, status)

def json_body():
    if not request.is_json or not isinstance(request.get_json(), dict):
        return None
    return request.get_json()

def require_roles(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return error(401, "请先登录")
            if user["role"] not in roles:
                return error(403, "无权执行此操作")
            g.current_user = user
            return view(*args, **kwargs)
        return wrapped
    return decorator

def current_user():
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        return None
    row = get_db().execute("SELECT user_id,username,role FROM app_user WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None

def audit(connection, action, target_type, target_id=None, detail=None):
    connection.execute(
        "INSERT INTO audit_log(user_id,action,target_type,target_id,detail) VALUES (?,?,?,?,?)",
        (g.current_user["user_id"] if hasattr(g, "current_user") else None,
         action, target_type, str(target_id) if target_id is not None else None,
         json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)),
    )

def create_app(test_config=None):
    root = Path(__file__).resolve().parent
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_urlsafe(32),
        DATABASE=os.getenv("DATABASE", str(root / "instance" / "shop.db")),
        TESTING=False,
    )
    if test_config:
        app.config.update(test_config)
    app.teardown_appcontext(close_db)
    init_db(app)

    @app.get("/health")
    def health():
        get_db().execute("SELECT 1")
        return response(200, "ok", {"service": "order-api", "database": "sqlite"})

    @app.post("/auth/setup")
    def setup():
        data = json_body()
        if not data or not isinstance(data.get("username"), str) or not isinstance(data.get("password"), str):
            return error(400, "用户名和密码必填")
        if len(data["username"].strip()) < 3 or len(data["password"]) < 8:
            return error(400, "用户名至少 3 位，密码至少 8 位")
        connection = get_db()
        if connection.execute("SELECT 1 FROM app_user LIMIT 1").fetchone():
            return error(409, "系统已初始化")
        connection.execute("INSERT INTO app_user(username,password_hash,role) VALUES (?,?,?)",
                           (data["username"].strip(), generate_password_hash(data["password"]), "admin"))
        connection.commit()
        return response(200, "管理员创建成功")

    @app.post("/auth/login")
    def login():
        data = json_body()
        if not data:
            return error(400, "请求参数错误")
        row = get_db().execute("SELECT * FROM app_user WHERE username=?", (str(data.get("username", "")).strip(),)).fetchone()
        if not row or not check_password_hash(row["password_hash"], str(data.get("password", ""))):
            return error(401, "用户名或密码错误")
        session.clear()
        session["user_id"] = row["user_id"]
        return response(200, "登录成功", {"username": row["username"], "role": row["role"]})

    @app.post("/auth/logout")
    @require_roles("admin", "customer")
    def logout():
        session.clear()
        return response(200, "退出成功")

    @app.post("/users")
    @require_roles("admin")
    def create_customer():
        data = json_body()
        if not data or not isinstance(data.get("username"), str) or not isinstance(data.get("password"), str):
            return error(400, "用户名和密码必填")
        username, password = data["username"].strip(), data["password"]
        if len(username) < 3 or len(password) < 8:
            return error(400, "用户名至少 3 位，密码至少 8 位")
        connection = get_db()
        try:
            cursor = connection.execute(
                "INSERT INTO app_user(username,password_hash,role) VALUES (?,?,?)",
                (username, generate_password_hash(password), "customer"),
            )
            audit(connection, "USER_CREATED", "user", cursor.lastrowid, {"username": username, "role": "customer"})
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            return error(409, "用户名已存在")
        return response(200, "客户账号创建成功", {"user_id": cursor.lastrowid, "username": username, "role": "customer"})

    @app.post("/products")
    @require_roles("admin")
    def create_product():
        data = json_body()
        if not data or not isinstance(data.get("sku"), str) or not isinstance(data.get("name"), str):
            return error(400, "sku 和商品名称必填")
        sku, name = data["sku"].strip(), data["name"].strip()
        if not sku or not name:
            return error(400, "sku 和商品名称不能为空")
        try:
            price, stock = float(data.get("price")), int(data.get("stock"))
            if price < 0 or stock < 0:
                raise ValueError
        except (TypeError, ValueError):
            return error(400, "价格和库存必须为非负数")
        try:
            connection = get_db()
            cursor = connection.execute("INSERT INTO product(sku,name,price,stock) VALUES (?,?,?,?)",
                                         (sku, name, price, stock))
            audit(connection, "PRODUCT_CREATED", "product", cursor.lastrowid, {"sku": sku})
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            return error(409, "SKU 已存在")
        return response(200, "商品创建成功", {"product_id": cursor.lastrowid})

    @app.get("/products")
    @require_roles("admin", "customer")
    def products():
        rows = get_db().execute("SELECT product_id,sku,name,price,stock FROM product WHERE active=1 ORDER BY product_id").fetchall()
        return response(200, "查询成功", [dict(row) for row in rows])

    @app.post("/cart/items")
    @require_roles("customer")
    def add_cart_item():
        data = json_body()
        if not data or not isinstance(data.get("product_id"), int) or not isinstance(data.get("quantity"), int) or data["quantity"] <= 0:
            return error(400, "商品和数量参数错误")
        connection = get_db()
        product = connection.execute("SELECT product_id,stock,active FROM product WHERE product_id=?", (data["product_id"],)).fetchone()
        if not product or not product["active"]:
            return error(404, "商品不存在")
        old = connection.execute("SELECT quantity FROM cart_item WHERE user_id=? AND product_id=?",
                                 (g.current_user["user_id"], data["product_id"])).fetchone()
        quantity = (old["quantity"] if old else 0) + data["quantity"]
        if quantity > product["stock"]:
            return error(409, "购物车数量超过库存")
        connection.execute("INSERT INTO cart_item(user_id,product_id,quantity) VALUES (?,?,?) ON CONFLICT(user_id,product_id) DO UPDATE SET quantity=excluded.quantity",
                           (g.current_user["user_id"], data["product_id"], quantity))
        connection.commit()
        return response(200, "已加入购物车")

    @app.get("/cart")
    @require_roles("customer")
    def cart():
        rows = get_db().execute("SELECT c.product_id,p.name,p.price,c.quantity FROM cart_item c JOIN product p ON p.product_id=c.product_id WHERE c.user_id=?",
                                (g.current_user["user_id"],)).fetchall()
        return response(200, "查询成功", [dict(row) for row in rows])

    @app.post("/orders")
    @require_roles("customer")
    def create_order():
        data = json_body()
        items = data.get("items") if data else None
        idem = request.headers.get("Idempotency-Key", "").strip()
        if not isinstance(items, list) or not items or not idem or len(idem) > 80:
            return error(400, "items 和 Idempotency-Key 必填")
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute("SELECT order_id,order_no,status,total_amount FROM customer_order WHERE user_id=? AND idempotency_key=?",
                                     (g.current_user["user_id"], idem)).fetchone()
            if old:
                connection.rollback()
                return response(200, "重复请求，返回原订单", dict(old))
            total, validated = 0.0, []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("product_id"), int) or not isinstance(item.get("quantity"), int) or item["quantity"] <= 0:
                    connection.rollback()
                    return error(400, "订单商品参数错误")
                product = connection.execute("SELECT * FROM product WHERE product_id=? AND active=1", (item["product_id"],)).fetchone()
                if not product:
                    connection.rollback()
                    return error(404, "商品不存在")
                if product["stock"] < item["quantity"]:
                    connection.rollback()
                    return error(409, "库存不足")
                total += product["price"] * item["quantity"]
                validated.append((product, item["quantity"]))
            order_no = "ORD" + secrets.token_hex(8).upper()
            cursor = connection.execute("INSERT INTO customer_order(order_no,user_id,status,total_amount,idempotency_key) VALUES (?,?,?,?,?)",
                                         (order_no, g.current_user["user_id"], "pending_payment", round(total, 2), idem))
            order_id = cursor.lastrowid
            for product, quantity in validated:
                connection.execute("UPDATE product SET stock=stock-? WHERE product_id=?", (quantity, product["product_id"]))
                connection.execute("INSERT INTO order_item(order_id,product_id,product_name,unit_price,quantity) VALUES (?,?,?,?,?)",
                                   (order_id, product["product_id"], product["name"], product["price"], quantity))
            connection.execute("DELETE FROM cart_item WHERE user_id=?", (g.current_user["user_id"],))
            audit(connection, "ORDER_CREATED", "order", order_id, {"total": round(total, 2)})
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            return error(409, "订单幂等键冲突")
        except Exception:
            connection.rollback()
            return error(503, "订单服务暂不可用")
        return response(200, "订单创建成功", {"order_id": order_id, "order_no": order_no, "status": "pending_payment", "total_amount": round(total, 2)})

    @app.post("/orders/<int:order_id>/pay")
    @require_roles("customer")
    def pay_order(order_id):
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute("SELECT * FROM customer_order WHERE order_id=? AND user_id=?", (order_id, g.current_user["user_id"])).fetchone()
            if not order:
                connection.rollback()
                return error(404, "订单不存在")
            if order["status"] == "paid":
                connection.rollback()
                return response(200, "订单已支付", {"order_id": order_id, "status": "paid"})
            if order["status"] != "pending_payment":
                connection.rollback()
                return error(409, "当前订单状态不可支付")
            payment_no = "PAY" + secrets.token_hex(8).upper()
            connection.execute("INSERT INTO payment(order_id,payment_no,amount) VALUES (?,?,?)", (order_id, payment_no, order["total_amount"]))
            connection.execute("UPDATE customer_order SET status='paid' WHERE order_id=?", (order_id,))
            audit(connection, "ORDER_PAID", "order", order_id, {"payment_no": payment_no})
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            return response(200, "订单已支付", {"order_id": order_id, "status": "paid"})
        return response(200, "支付成功", {"order_id": order_id, "status": "paid", "payment_no": payment_no})

    @app.post("/orders/<int:order_id>/cancel")
    @require_roles("customer")
    def cancel_order(order_id):
        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute("SELECT * FROM customer_order WHERE order_id=? AND user_id=?", (order_id, g.current_user["user_id"])).fetchone()
            if not order:
                connection.rollback()
                return error(404, "订单不存在")
            if order["status"] == "cancelled":
                connection.rollback()
                return response(200, "订单已取消", {"order_id": order_id, "status": "cancelled"})
            if order["status"] != "pending_payment":
                connection.rollback()
                return error(409, "已支付订单不能直接取消")
            items = connection.execute("SELECT product_id,quantity FROM order_item WHERE order_id=?", (order_id,)).fetchall()
            for item in items:
                connection.execute("UPDATE product SET stock=stock+? WHERE product_id=?", (item["quantity"], item["product_id"]))
            connection.execute("UPDATE customer_order SET status='cancelled' WHERE order_id=?", (order_id,))
            audit(connection, "ORDER_CANCELLED", "order", order_id)
            connection.commit()
        except Exception:
            connection.rollback()
            return error(503, "订单服务暂不可用")
        return response(200, "订单已取消", {"order_id": order_id, "status": "cancelled"})

    @app.get("/orders")
    @require_roles("admin", "customer")
    def orders():
        if g.current_user["role"] == "admin":
            rows = get_db().execute("SELECT order_id,order_no,user_id,status,total_amount,created_at FROM customer_order ORDER BY order_id DESC").fetchall()
        else:
            rows = get_db().execute("SELECT order_id,order_no,user_id,status,total_amount,created_at FROM customer_order WHERE user_id=? ORDER BY order_id DESC", (g.current_user["user_id"],)).fetchall()
        return response(200, "查询成功", [dict(row) for row in rows])

    return app

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5002, debug=False)
