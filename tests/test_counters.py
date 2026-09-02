import unittest
import xml.etree.ElementTree as ElementTree

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

    def parse_svg(self, content: bytes) -> ElementTree.Element:
        root = ElementTree.fromstring(content)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        return root

    def test_frontend_and_api_documentation_routes(self) -> None:
        homepage = self.client.get("/")
        self.assertEqual(homepage.status_code, 200)
        self.assertIn("text/html", homepage.headers["content-type"])
        self.assertIn("A counter at an", homepage.text)
        self.assertIn('href="/docs"', homepage.text)
        self.assertEqual(homepage.headers["x-content-type-options"], "nosniff")

        stylesheet = self.client.get("/styles.css")
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn("text/css", stylesheet.headers["content-type"])
        self.assertEqual(
            stylesheet.headers["cache-control"],
            "public, max-age=3600, stale-while-revalidate=86400",
        )

        docs = self.client.get("/docs")
        self.assertEqual(docs.status_code, 200)
        self.assertIn("text/html", docs.headers["content-type"])
        self.assertIn("The manual is taking shape", docs.text)
        self.assertIn('href="/docs-swagger"', docs.text)

        swagger = self.client.get("/docs-swagger")
        self.assertEqual(swagger.status_code, 200)
        self.assertIn("Swagger UI", swagger.text)

        schema = self.client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("/hit/{namespace}/{key}", schema.json()["paths"])

        missing = self.client.get(
            "/not-a-real-page",
            headers={"Accept": "text/html"},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertIn("This count came", missing.text)

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

    def test_get_shield_returns_current_value_as_svg(self) -> None:
        self.create_counter(initializer=50)

        response = self.client.get("/get/test/counter/shield")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/svg+xml")
        self.assertNotIn("cache-control", response.headers)
        root = self.parse_svg(response.content)
        text_values = [element.text for element in root.iter() if element.tag.endswith("text")]
        self.assertEqual(text_values[-1], "50")
        self.assertEqual(root.attrib["aria-label"], "counter: 50")

    def test_hit_shield_increments_once_and_disables_caching(self) -> None:
        self.create_counter(initializer=6)

        response = self.client.get("/hit/test/counter/shield")

        self.assertEqual(response.status_code, 200)
        self.parse_svg(response.content)
        self.assertEqual(
            response.headers["cache-control"],
            "max-age=0, no-cache, no-store, must-revalidate",
        )
        self.assertIn(">7</text>", response.text)
        self.assertEqual(self.client.get("/get/test/counter").json(), {"value": 7})

    def test_get_shield_returns_not_found_for_missing_counter(self) -> None:
        response = self.client.get("/get/test/missing/shield")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Key not found"})

    def test_shield_supports_all_abacus_styles(self) -> None:
        self.create_counter(initializer=3)
        styles = (
            "flat",
            "flat-square",
            "plastic",
            "flat-simple",
            "flat-square-simple",
            "plastic-simple",
        )

        for style in styles:
            with self.subTest(style=style):
                response = self.client.get(
                    "/get/test/counter/shield", params={"style": style}
                )
                self.assertEqual(response.status_code, 200)
                root = self.parse_svg(response.content)
                self.assertEqual(root.attrib["aria-label"], "3" if style.endswith("-simple") else "counter: 3")

    def test_shield_supports_abacus_customization_options(self) -> None:
        self.create_counter(initializer=12)

        response = self.client.get(
            "/get/test/counter/shield",
            params={
                "bgcolor": "e05d44",
                "textcolor": "ffff00",
                "text": "visits & clicks",
                "style": "plastic",
                "fontsize": "12",
                "font": "arial",
            },
        )

        self.assertEqual(response.status_code, 200)
        root = self.parse_svg(response.content)
        self.assertEqual(root.attrib["aria-label"], "visits & clicks: 12")
        self.assertIn('fill="#e05d44"', response.text)
        self.assertIn('fill="#ffff00"', response.text)
        self.assertIn('font-family="Arial,Helvetica,sans-serif"', response.text)
        self.assertIn('font-size="12"', response.text)
        self.assertIn("visits &amp; clicks", response.text)

    def test_simple_shield_omits_label(self) -> None:
        self.create_counter(initializer=8)
        response = self.client.get(
            "/get/test/counter/shield",
            params={"style": "flat-simple", "text": "do not render"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("do not render", response.text)
        self.assertEqual(self.parse_svg(response.content).attrib["aria-label"], "8")

    def test_shield_rejects_invalid_hex_colors(self) -> None:
        self.create_counter()

        background = self.client.get(
            "/get/test/counter/shield", params={"bgcolor": "purple"}
        )
        foreground = self.client.get(
            "/get/test/counter/shield", params={"textcolor": "12"}
        )

        self.assertEqual(background.status_code, 400)
        self.assertIn("not a valid hex color", background.json()["detail"])
        self.assertEqual(foreground.status_code, 400)

    def test_invalid_shield_style_font_and_size_use_abacus_fallbacks(self) -> None:
        self.create_counter(initializer=2)
        response = self.client.get(
            "/get/test/counter/shield",
            params={"style": "unknown", "font": "unknown", "fontsize": "tiny"},
        )

        self.assertEqual(response.status_code, 200)
        self.parse_svg(response.content)
        self.assertIn('font-family="Verdana,DejaVu Sans,sans-serif"', response.text)
        self.assertIn('font-size="11"', response.text)
        self.assertIn('id="smooth"', response.text)


if __name__ == "__main__":
    unittest.main()
