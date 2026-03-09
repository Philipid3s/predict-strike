"""
Source specs:
- README.md
- docker-compose.dev.yml
- docker-compose.yml
"""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class RuntimeModesAcceptanceTests(unittest.TestCase):
    def test_readme_documents_local_and_docker_run_modes(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        expected_markers = [
            "## Run Modes",
            "Option A: local development",
            "Option B: development Docker compose",
            "docker compose -f docker-compose.dev.yml up --build",
            "docker compose up --build -d",
            "docker compose down",
            "CORS_ALLOWED_ORIGINS",
            "FRONTEND_VITE_API_URL",
        ]

        for marker in expected_markers:
            self.assertIn(marker, readme, msg=f"README run-mode marker missing: {marker}")

    def test_service_dockerfiles_run_real_frontend_and_backend_commands(self) -> None:
        frontend_dev = (REPO_ROOT / "frontend" / "Dockerfile.dev").read_text(
            encoding="utf-8"
        )
        frontend_prod = (REPO_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        backend_dev = (REPO_ROOT / "backend" / "Dockerfile.dev").read_text(encoding="utf-8")
        backend_prod = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn('"npm", "run", "dev"', frontend_dev)
        self.assertIn("--host\", \"0.0.0.0\"", frontend_dev)
        self.assertIn("RUN npm run build", frontend_prod)
        self.assertIn("nginx", frontend_prod)
        self.assertIn("uvicorn", backend_dev)
        self.assertIn("--reload", backend_dev)
        self.assertIn("uvicorn", backend_prod)

        forbidden_markers = [
            "placeholder",
            "sleep infinity",
        ]

        for source_name, source in [
            ("frontend/Dockerfile.dev", frontend_dev),
            ("frontend/Dockerfile", frontend_prod),
            ("backend/Dockerfile.dev", backend_dev),
            ("backend/Dockerfile", backend_prod),
        ]:
            for marker in forbidden_markers:
                self.assertNotIn(
                    marker,
                    source,
                    msg=f"{source_name} still contains placeholder marker: {marker}",
                )

    def test_compose_files_reference_real_runtime_wiring(self) -> None:
        dev_compose = (REPO_ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
        prod_compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        dev_markers = [
            "dockerfile: Dockerfile.dev",
            "./frontend:/workspace",
            "./backend:/workspace",
            "/workspace/node_modules",
            "./frontend/.env.local",
            "./backend/.env",
        ]
        prod_markers = [
            "dockerfile: Dockerfile",
            "VITE_API_URL: ${FRONTEND_VITE_API_URL:-http://localhost:8000}",
            "\"80:80\"",
            "\"8000:8000\"",
        ]

        for marker in dev_markers:
            self.assertIn(marker, dev_compose, msg=f"Dev compose marker missing: {marker}")

        for marker in prod_markers:
            self.assertIn(
                marker, prod_compose, msg=f"Production compose marker missing: {marker}"
            )

    def test_backend_allows_documented_frontend_origins_via_cors(self) -> None:
        main_source = (REPO_ROOT / "backend" / "src" / "main.py").read_text(
            encoding="utf-8"
        )
        settings_source = (REPO_ROOT / "backend" / "src" / "config" / "settings.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CORSMiddleware", main_source)
        self.assertIn("allow_origins=list(settings.cors_allowed_origins)", main_source)
        self.assertIn("CORS_ALLOWED_ORIGINS", settings_source)
        self.assertIn("http://localhost:5173", settings_source)
        self.assertIn("http://localhost", settings_source)


if __name__ == "__main__":
    unittest.main()
