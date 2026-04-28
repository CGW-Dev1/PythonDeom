from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DATA_DIR = BASE_DIR / "data"


class Config:
    SECRET_KEY = "replace-this-secret-key-in-production"
    DATABASE = str(INSTANCE_DIR / "housing.db")
    JSON_AS_ASCII = False
    SCHEDULER_ENABLED = True
    DEFAULT_REFRESH_CRON = {"hour": 2, "minute": 30}
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
