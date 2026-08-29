import unittest

from fastapi.testclient import TestClient

import core.database as db
from core.constants import BASE_TTL_SECONDS
from main import app
from tests.fake_valkey import FakeValkey


class CounterApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valkey = FakeValkey()
        db.client = self.valkey
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        db.client = None

    def create_counter(
        self, namespace: str = "test", key: str = "counter", initializer: int = 0
    ) -> dict:
        response = self.client.post(
            f"/create/{namespace}/{key}", params={"initializer": initializer}
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_create_get_hit_and_info(self) -> None:
        created = self.create_counter(initializer=10)

        self.assertEqual(created["value"], 10)
        self.assertTrue(created["admin_key"])
        self.assertEqual(self.client.get("/get/test/counter").json(), {"value": 10})

        hit = self.client.get("/hit/test/counter")
        self.assertEqual(hit.status_code, 200)
        self.assertEqual(hit.json(), {"value": 11})

        info = self.client.get("/info/test/counter")
        self.assertEqual(info.status_code, 200)
        self.assertEqual(
            info.json(),
            {
                "value": 11,
                "full_key": "K:test:counter",
                "is_genuine": False,
                "expires_in": BASE_TTL_SECONDS,
                "exists": True,
            },
        )

    def test_hit_auto_creates_genuine_counter(self) -> None:
        response = self.client.get("/hit/public/visits")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"value": 1})

        info = self.client.get("/info/public/visits").json()
        self.assertTrue(info["is_genuine"])
        self.assertEqual(info["expires_in"], BASE_TTL_SECONDS)

        update = self.client.post("/update/public/visits", params={"value": 2})
        self.assertEqual(update.status_code, 400)

    def test_managed_counter_admin_lifecycle(self) -> None:
        token = self.create_counter(initializer=4)["admin_key"]

        unauthorized = self.client.post(
            "/update/test/counter", params={"value": 3}
        )
        self.assertEqual(unauthorized.status_code, 401)

        updated = self.client.post(
            "/update/test/counter", params={"value": 3, "token": token}
        )
        self.assertEqual(updated.json(), {"value": 7})

        changed = self.client.post(
            "/set/test/counter",
            params={"value": 25},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(changed.json(), {"value": 25})

        reset = self.client.post("/reset/test/counter", params={"token": token})
        self.assertEqual(reset.json(), {"value": 0})

        deleted = self.client.post("/delete/test/counter", params={"token": token})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/get/test/counter").status_code, 404)

    def test_create_rejects_duplicate_counter(self) -> None:
        self.create_counter()
        duplicate = self.client.post("/create/test/counter")
        self.assertEqual(duplicate.status_code, 409)

    def test_invalid_namespace_and_key_are_rejected(self) -> None:
        too_short = self.client.get("/hit/ab/valid-key")
        invalid_character = self.client.get("/hit/valid/key%20with%20spaces")

        self.assertEqual(too_short.status_code, 400)
        self.assertEqual(invalid_character.status_code, 400)

    def test_random_create_returns_addressable_counter(self) -> None:
        response = self.client.post("/create")
        self.assertEqual(response.status_code, 201)
        body = response.json()

        fetched = self.client.get(f"/get/{body['namespace']}/{body['key']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), {"value": 0})


if __name__ == "__main__":
    unittest.main()
