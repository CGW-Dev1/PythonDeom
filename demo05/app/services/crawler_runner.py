import logging
from pathlib import Path

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.crawlers.fang import FangTianXiaCrawler
from app.crawlers.platform_58 import Tongcheng58Crawler
from app.database import db
from app.models import Listing
from app.services.data_cleaner import RentDataCleaner
from app.services.sample_data import SAMPLE_LISTINGS


CRAWLER_REGISTRY = {
    "58": Tongcheng58Crawler,
    "fang": FangTianXiaCrawler,
}


def get_logger():
    log_dir = Path(current_app.config["LOG_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("rent_crawler")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(log_dir / "crawler.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def import_sample_data(clear=False):
    if clear:
        Listing.query.delete()
        db.session.commit()
    return save_records(SAMPLE_LISTINGS, source_name="sample")


def crawl_to_database(platforms, city="bj", max_pages=3):
    logger = get_logger()
    result = {
        "inserted": 0,
        "skipped": 0,
        "errors": [],
        "raw_count": 0,
    }

    for platform in platforms:
        crawler_class = CRAWLER_REGISTRY.get(platform)
        if crawler_class is None:
            result["errors"].append(f"未知平台：{platform}")
            continue

        try:
            with crawler_class(
                city=city,
                headless=current_app.config["CRAWLER_HEADLESS"],
                min_delay=current_app.config["CRAWLER_MIN_DELAY"],
                max_delay=current_app.config["CRAWLER_MAX_DELAY"],
                page_load_timeout=current_app.config["CRAWLER_PAGE_LOAD_TIMEOUT"],
            ) as crawler:
                raw_records = crawler.collect(max_pages=max_pages)
            logger.info("platform=%s city=%s raw_count=%s", platform, city, len(raw_records))
            saved = save_records(raw_records, source_name=crawler_class.platform_name)
            result["raw_count"] += len(raw_records)
            result["inserted"] += saved["inserted"]
            result["skipped"] += saved["skipped"]
        except Exception as exc:
            logger.exception("crawler failed: platform=%s city=%s", platform, city)
            result["errors"].append(f"{platform} 采集失败：{exc}")

    return result


def save_records(records, source_name="unknown"):
    cleaner = RentDataCleaner()
    cleaned_records = cleaner.clean_records(records)
    inserted = 0
    skipped = 0

    for item in cleaned_records:
        item["source"] = item.get("source") or source_name
        if Listing.query.filter_by(raw_hash=item["raw_hash"]).first():
            skipped += 1
            continue

        listing = Listing(**item)
        db.session.add(listing)
        try:
            db.session.commit()
            inserted += 1
        except IntegrityError:
            db.session.rollback()
            skipped += 1

    return {
        "inserted": inserted,
        "skipped": skipped + max(0, len(records) - len(cleaned_records)),
        "cleaned": len(cleaned_records),
    }
