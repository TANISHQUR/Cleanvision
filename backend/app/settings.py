"""Backend settings, read from environment variables or backend/.env."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Settings:
    def __init__(self) -> None:
        self.mongo_url = _env("MONGO_URL", "mongodb://localhost:27017")
        self.mongo_db = _env("MONGO_DB", "cleanvision")
        self.use_mock_db = _env("USE_MOCK_DB", "0") == "1"

        self.storage_dir = Path(_env("STORAGE_DIR", str(PROJECT_ROOT / "storage"))).resolve()
        self.max_upload_mb = int(_env("MAX_UPLOAD_MB", "500"))

        self.admin_username = _env("ADMIN_USERNAME", "admin")
        self.admin_password = _env("ADMIN_PASSWORD", "cleanvision")
        self.secret_key = _env("SECRET_KEY", "dev-secret-change-me")
        self.token_ttl_hours = int(_env("TOKEN_TTL_HOURS", "12"))
        self.detector_token = _env("DETECTOR_TOKEN", "change-me-detector-token")

        self.cors_origins = [o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

        # How the backend launches the detector for uploaded videos
        self.python_exe = _env("DETECTOR_PYTHON", sys.executable)
        self.detector_config = _env("DETECTOR_CONFIG", str(PROJECT_ROOT / "config.yaml"))
        self.public_api_url = _env("PUBLIC_API_URL", "http://127.0.0.1:8000")

        # Demo fine amounts in INR, per waste type
        self.fine_default = int(_env("FINE_DEFAULT", "500"))
        self.fine_amounts: dict[str, int] = json.loads(
            _env("FINE_AMOUNTS", '{"bottle": 500, "can": 500, "wrapper": 300, "paper": 200, "cup": 300}')
        )
        self.challan_due_days = int(_env("CHALLAN_DUE_DAYS", "30"))

    @property
    def evidence_dir(self) -> Path:
        return self.storage_dir / "evidence"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    def fine_for(self, waste_type: str) -> int:
        return int(self.fine_amounts.get(waste_type, self.fine_default))


settings = Settings()
