def body(response):
    assert response.is_json
    return response.get_json()

def test_order_lifecycle_reduces_and_restores_stock(app, admin, customer):
    product = customer.get("/products").get_json()["data"][0]
    assert customer.post("/cart/items", json={"product_id": product["product_id"], "quantity": 2}).status_code == 200
    created = customer.post("/orders", json={"items": [{"product_id": product["product_id"], "quantity": 2}]}, headers={"Idempotency-Key": "order-001"})
    assert created.status_code == 200
    order = body(created)["data"]
    assert customer.get("/products").get_json()["data"][0]["stock"] == 3
    assert customer.post(f"/orders/{order['order_id']}/pay").status_code == 200
    assert customer.post(f"/orders/{order['order_id']}/pay").get_json()["data"]["status"] == "paid"
    assert customer.post(f"/orders/{order['order_id']}/cancel").status_code == 409

def test_idempotency_returns_same_order_and_does_not_double_decrement(customer):
    product = customer.get("/products").get_json()["data"][0]
    payload = {"items": [{"product_id": product["product_id"], "quantity": 1}]}
    first = customer.post("/orders", json=payload, headers={"Idempotency-Key": "same-key"})
    second = customer.post("/orders", json=payload, headers={"Idempotency-Key": "same-key"})
    assert first.status_code == second.status_code == 200
    assert body(first)["data"]["order_id"] == body(second)["data"]["order_id"]
    assert customer.get("/products").get_json()["data"][0]["stock"] == 4

def test_invalid_inputs_and_stock_boundaries(customer):
    product = customer.get("/products").get_json()["data"][0]
    assert customer.post("/cart/items", json={"product_id": product["product_id"], "quantity": 0}).status_code == 400
    assert customer.post("/orders", json={"items": [{"product_id": product["product_id"], "quantity": 99}]}, headers={"Idempotency-Key": "too-many"}).status_code == 409
    assert customer.post("/orders", json={"items": []}, headers={"Idempotency-Key": "empty"}).status_code == 400

def test_cancel_restores_stock_and_audit_is_created(app, admin, customer):
    product = customer.get("/products").get_json()["data"][0]
    created = customer.post("/orders", json={"items": [{"product_id": product["product_id"], "quantity": 3}]}, headers={"Idempotency-Key": "cancel-key"})
    order_id = body(created)["data"]["order_id"]
    assert customer.post(f"/orders/{order_id}/cancel").status_code == 200
    assert customer.get("/products").get_json()["data"][0]["stock"] == 5
    with app.app_context():
        actions = [row["action"] for row in __import__("database").get_db().execute("SELECT action FROM audit_log").fetchall()]
    assert "ORDER_CREATED" in actions and "ORDER_CANCELLED" in actions

def test_permissions_are_consistent(app, admin):
    anonymous = app.test_client()
    assert anonymous.get("/products").status_code == 401
    assert admin.post("/cart/items", json={"product_id": 1, "quantity": 1}).status_code == 403
    assert admin.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers={"Idempotency-Key": "admin-key"}).status_code == 403

def test_admin_can_create_customer_and_duplicate_is_rejected(app, admin):
    created = admin.post("/users", json={"username": "newbuyer", "password": "Buyer@123"})
    assert created.status_code == 200
    assert body(created)["data"]["role"] == "customer"
    duplicate = admin.post("/users", json={"username": "newbuyer", "password": "Buyer@123"})
    assert duplicate.status_code == 409
    short_password = admin.post("/users", json={"username": "abc", "password": "123"})
    assert short_password.status_code == 400

def test_product_rejects_blank_sku_or_name(admin):
    blank_sku = admin.post("/products", json={"sku": "   ", "name": "有效名称", "price": 1, "stock": 1})
    blank_name = admin.post("/products", json={"sku": "SKU-BLANK", "name": "  ", "price": 1, "stock": 1})
    assert blank_sku.status_code == 400
    assert blank_name.status_code == 400
