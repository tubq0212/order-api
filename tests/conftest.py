import pytest
from app import create_app

@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "shop.db"), "SECRET_KEY": "test-secret"})

@pytest.fixture
def admin(app):
    client = app.test_client()
    assert client.post("/auth/setup", json={"username": "admin", "password": "Admin@123"}).status_code == 200
    assert client.post("/auth/login", json={"username": "admin", "password": "Admin@123"}).status_code == 200
    return client

@pytest.fixture
def customer(app, admin):
    product = admin.post("/products", json={"sku": "SKU-001", "name": "测试商品", "price": 10, "stock": 5})
    assert product.status_code == 200
    user = app.test_client()
    created = admin.post("/users", json={"username": "buyer", "password": "Buyer@123"})
    assert created.status_code == 200
    assert user.post("/auth/login", json={"username": "buyer", "password": "Buyer@123"}).status_code == 200
    return user
