import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + str(BASE_DIR / "rent_analysis.db").replace("\\", "/"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CHART_OUTPUT_DIR = os.getenv(
        "CHART_OUTPUT_DIR",
        str(BASE_DIR / "app" / "static" / "generated"),
    )
    CHART_URL_PREFIX = "/static/generated"
    LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))

    CRAWLER_HEADLESS = os.getenv("CRAWLER_HEADLESS", "1") != "0"
    CRAWLER_MIN_DELAY = float(os.getenv("CRAWLER_MIN_DELAY", "1.5"))
    CRAWLER_MAX_DELAY = float(os.getenv("CRAWLER_MAX_DELAY", "4.0"))
    CRAWLER_PAGE_LOAD_TIMEOUT = int(os.getenv("CRAWLER_PAGE_LOAD_TIMEOUT", "25"))

    PAGE_SIZE = int(os.getenv("PAGE_SIZE", "12"))
