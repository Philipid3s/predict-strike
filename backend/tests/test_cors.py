from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.main import app  # noqa: E402


class CorsTests(unittest.TestCase):
    def test_localhost_frontend_origin_is_allowed(self) -> None:
        client = TestClient(app)

        response = client.options(
            "/api/v1/signals/latest",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )


if __name__ == "__main__":
    unittest.main()
