from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


def test_concurrent_orders_do_not_oversell(app, customer):
    product = customer.get("/products").get_json()["data"][0]
    clients = [app.test_client() for _ in range(10)]
    for client in clients:
        login = client.post("/auth/login", json={"username": "buyer", "password": "Buyer@123"})
        assert login.status_code == 200

    barrier = Barrier(len(clients))

    def place_order(index):
        barrier.wait(timeout=10)
        response = clients[index].post(
            "/orders",
            json={"items": [{"product_id": product["product_id"], "quantity": 1}]},
            headers={"Idempotency-Key": f"concurrent-{index}"},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        statuses = list(pool.map(place_order, range(len(clients))))

    assert statuses.count(200) == 5
    assert statuses.count(409) == 5
    assert customer.get("/products").get_json()["data"][0]["stock"] == 0
