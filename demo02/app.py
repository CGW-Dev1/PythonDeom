import html
import ipaddress
import json
import logging
import os
import re
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import RLock
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, FeatureNotFound
from flask import Flask, jsonify, render_template, request, session


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-price-compare-secret")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

DATA_LOCK = RLock()
CHINA_TZ = timezone(timedelta(hours=8))

DEFAULT_CATEGORIES = [
    {"id": "electronics", "name": "电子产品"},
    {"id": "home", "name": "家居用品"},
    {"id": "beauty", "name": "美妆护肤"},
    {"id": "food", "name": "食品酒水"},
]

PLATFORM_RULES = [
    ("淘宝", ("taobao.com",)),
    ("天猫", ("tmall.com",)),
    ("京东", ("jd.com", "360buy.com")),
    ("拼多多", ("pinduoduo.com", "yangkeduo.com")),
    ("唯品会", ("vip.com",)),
    ("苏宁易购", ("suning.com",)),
    ("当当", ("dangdang.com",)),
    ("亚马逊中国", ("amazon.cn",)),
]

categories = [dict(item) for item in DEFAULT_CATEGORIES]
crawler_config = {
    "timeout_seconds": 3,
    "max_batch_size": 20,
    "min_price": 0.01,
    "max_price": 999999,
    "enabled_platforms": {
        "淘宝": True,
        "天猫": True,
        "京东": True,
        "拼多多": True,
        "唯品会": True,
        "苏宁易购": True,
        "当当": True,
        "亚马逊中国": True,
        "其他平台": True,
    },
}

session_store = {}
metrics = {
    "success": 0,
    "failure": 0,
    "total_latency_ms": 0,
    "logs": [],
}


def now_text():
    return datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def api_success(payload=None, status=200):
    data = {"ok": True}
    if payload:
        data.update(payload)
    return jsonify(data), status


def api_error(message, status=400, details=None):
    payload = {"ok": False, "message": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status


def get_session_id():
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["sid"] = sid
    return sid


def get_session_data():
    sid = get_session_id()
    with DATA_LOCK:
        if sid not in session_store:
            session_store[sid] = {"items": {}}
        return session_store[sid]


def get_category(category_id):
    with DATA_LOCK:
        return next((item for item in categories if item["id"] == category_id), None)


def sorted_items_for(category_id):
    data = get_session_data()
    items = data["items"].get(category_id, [])
    return sorted(items, key=lambda item: item["price"])


def serialize_categories():
    data = get_session_data()
    with DATA_LOCK:
        return [
            {
                "id": category["id"],
                "name": category["name"],
                "count": len(data["items"].get(category["id"], [])),
            }
            for category in categories
        ]


def record_event(success, message, url=None, category_id=None, latency_ms=0):
    with DATA_LOCK:
        if success:
            metrics["success"] += 1
        else:
            metrics["failure"] += 1
        metrics["total_latency_ms"] += int(latency_ms or 0)
        metrics["logs"].insert(
            0,
            {
                "time": now_text(),
                "level": "成功" if success else "失败",
                "message": message,
                "url": url or "",
                "category_id": category_id or "",
                "latency_ms": int(latency_ms or 0),
            },
        )
        del metrics["logs"][80:]

    if success:
        logger.info("%s url=%s category=%s latency=%sms", message, url, category_id, latency_ms)
    else:
        logger.warning("%s url=%s category=%s latency=%sms", message, url, category_id, latency_ms)


def normalize_url(raw_url):
    url = (raw_url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url
    return url


def split_urls(raw):
    if isinstance(raw, list):
        values = raw
    else:
        values = re.split(r"[\s,，]+", raw or "")

    urls = []
    seen = set()
    for value in values:
        url = normalize_url(str(value))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def host_is_blocked(hostname):
    host = (hostname or "").strip().lower().rstrip(".")
    if not host or host == "localhost":
        return True

    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return True
    return False


def validate_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "仅支持 http 或 https 商品网址"
    if not parsed.netloc or not parsed.hostname:
        return False, "网址格式不正确"
    if host_is_blocked(parsed.hostname):
        return False, "出于安全考虑，不允许采集本机或内网地址"
    return True, ""


def detect_platform(url):
    host = (urlparse(url).hostname or "").lower().strip(".")
    for platform, domains in PLATFORM_RULES:
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return platform, platform
    display = host[4:] if host.startswith("www.") else host
    return "其他平台", display or "其他平台"


def soup_from_html(page_html):
    try:
        return BeautifulSoup(page_html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(page_html, "html.parser")


def parse_price_value(value):
    if value is None:
        return None
    text = html.unescape(str(value)).replace(",", "").strip()
    match = re.search(r"([0-9]{1,7}(?:\.[0-9]{1,2})?)", text)
    if not match:
        return None

    try:
        price = Decimal(match.group(1)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None

    min_price = Decimal(str(crawler_config["min_price"]))
    max_price = Decimal(str(crawler_config["max_price"]))
    if price < min_price or price > max_price:
        return None
    return price


def read_json_prices(value, add_candidate, priority=1):
    if isinstance(value, dict):
        for key in ("price", "lowPrice", "salePrice", "finalPrice"):
            if key in value:
                add_candidate(value.get(key), f"JSON-LD {key}", priority)

        offers = value.get("offers")
        if offers:
            read_json_prices(offers, add_candidate, priority)

        price_spec = value.get("priceSpecification")
        if price_spec:
            read_json_prices(price_spec, add_candidate, priority)

        for nested in value.values():
            if isinstance(nested, (dict, list)):
                read_json_prices(nested, add_candidate, priority + 1)
    elif isinstance(value, list):
        for item in value:
            read_json_prices(item, add_candidate, priority)


def extract_price(page_html):
    candidates = []

    def add_candidate(value, source, priority):
        price = parse_price_value(value)
        if price is not None:
            candidates.append({"price": price, "source": source, "priority": priority})

    soup = soup_from_html(page_html)

    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value.lower()):
        text = script.string or script.get_text(strip=True)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        read_json_prices(payload, add_candidate, priority=1)

    meta_rules = [
        ("property", "product:price:amount"),
        ("property", "og:price:amount"),
        ("property", "og:price"),
        ("name", "twitter:data1"),
        ("name", "price"),
        ("itemprop", "price"),
    ]
    for attr, name in meta_rules:
        for node in soup.find_all(attrs={attr: name}):
            add_candidate(node.get("content") or node.get("value") or node.get_text(" ", strip=True), name, 2)

    for node in soup.select("[data-price], [data-sale-price], [data-now-price], [itemprop='price']"):
        for attr in ("data-price", "data-sale-price", "data-now-price", "content"):
            add_candidate(node.get(attr), attr, 2)
        add_candidate(node.get_text(" ", strip=True), "价格节点", 2)

    keyword_patterns = [
        r"(?:到手价|券后价|促销价|活动价|秒杀价|现价)\s*[:：=]?\s*[¥￥]?\s*([0-9]{1,7}(?:\.[0-9]{1,2})?)",
        r"(?:salePrice|finalPrice|promotionPrice|pPrice|jdPrice|price)\s*[\"']?\s*[:=]\s*[\"']?[¥￥]?\s*([0-9]{1,7}(?:\.[0-9]{1,2})?)",
        r"[¥￥]\s*([0-9]{1,7}(?:\.[0-9]{1,2})?)",
    ]
    for index, pattern in enumerate(keyword_patterns, start=3):
        for match in re.finditer(pattern, page_html, flags=re.IGNORECASE):
            add_candidate(match.group(1), "页面价格文本", index)

    if not candidates:
        return None

    best_priority = min(item["priority"] for item in candidates)
    best_candidates = [item for item in candidates if item["priority"] == best_priority]
    return min(best_candidates, key=lambda item: item["price"])


def extract_title(page_html):
    soup = soup_from_html(page_html)
    title_node = soup.find("title")
    if not title_node:
        return ""
    title = re.sub(r"\s+", " ", title_node.get_text(" ", strip=True)).strip()
    return title[:120]


class PriceCrawler:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        "Cache-Control": "no-cache",
    }

    def fetch(self, url, timeout):
        current_url = url
        for _ in range(4):
            valid, message = validate_public_url(current_url)
            if not valid:
                raise ValueError(message)

            response = requests.get(
                current_url,
                headers=self.headers,
                timeout=timeout,
                allow_redirects=False,
                stream=True,
            )

            if 300 <= response.status_code < 400 and response.headers.get("Location"):
                current_url = urljoin(current_url, response.headers["Location"])
                continue

            chunks = []
            total = 0
            max_bytes = 2 * 1024 * 1024
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            response._content = b"".join(chunks)
            response.url = current_url
            return response

        raise ValueError("重定向次数过多")

    def collect(self, raw_url):
        started = time.perf_counter()
        url = normalize_url(raw_url)
        valid, message = validate_public_url(url)
        if not valid:
            return self.failure(url, message, started)

        platform_key, platform_display = detect_platform(url)
        if not crawler_config["enabled_platforms"].get(platform_key, True):
            return self.failure(url, f"{platform_display} 当前未启用采集", started)

        try:
            response = self.fetch(url, timeout=crawler_config["timeout_seconds"])
            if response.status_code >= 400:
                return self.failure(url, f"页面请求失败，状态码 {response.status_code}", started)

            page_html = response.text
            price_info = extract_price(page_html)
            if not price_info:
                return self.failure(url, "未能从页面中解析到有效价格", started)

            price = price_info["price"]
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "ok": True,
                "url": response.url or url,
                "input_url": raw_url,
                "platform": platform_display,
                "price": float(price),
                "price_display": f"{price:.2f}",
                "price_source": price_info["source"],
                "title": extract_title(page_html),
                "collected_at": now_text(),
                "latency_ms": latency_ms,
            }
        except requests.Timeout:
            return self.failure(url, "采集超时，请稍后重试", started)
        except requests.RequestException as exc:
            return self.failure(url, f"网络请求异常：{exc.__class__.__name__}", started)
        except ValueError as exc:
            return self.failure(url, str(exc), started)
        except Exception as exc:
            logger.exception("采集发生未知异常")
            return self.failure(url, f"采集失败：{exc.__class__.__name__}", started)

    @staticmethod
    def failure(url, message, started):
        return {
            "ok": False,
            "url": url,
            "message": message,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


crawler = PriceCrawler()


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return api_success({"status": "running", "time": now_text()})


@app.get("/api/categories")
def list_categories():
    return api_success({"categories": serialize_categories()})


@app.post("/api/categories")
def create_category():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return api_error("分类名称不能为空")
    if len(name) > 30:
        return api_error("分类名称不能超过 30 个字符")

    with DATA_LOCK:
        if any(item["name"] == name for item in categories):
            return api_error("分类名称已存在")
        category = {"id": "cat_" + uuid.uuid4().hex[:10], "name": name}
        categories.append(category)

    return api_success({"category": category, "categories": serialize_categories()}, status=201)


@app.put("/api/categories/<category_id>")
def update_category(category_id):
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return api_error("分类名称不能为空")
    if len(name) > 30:
        return api_error("分类名称不能超过 30 个字符")

    with DATA_LOCK:
        category = next((item for item in categories if item["id"] == category_id), None)
        if not category:
            return api_error("分类不存在", status=404)
        if any(item["id"] != category_id and item["name"] == name for item in categories):
            return api_error("分类名称已存在")
        category["name"] = name

    return api_success({"category": category, "categories": serialize_categories()})


@app.delete("/api/categories/<category_id>")
def delete_category(category_id):
    with DATA_LOCK:
        index_to_delete = next((index for index, item in enumerate(categories) if item["id"] == category_id), None)
        if index_to_delete is None:
            return api_error("分类不存在", status=404)
        category = categories.pop(index_to_delete)
        for data in session_store.values():
            data["items"].pop(category_id, None)

    return api_success({"deleted": category, "categories": serialize_categories()})


@app.get("/api/categories/<category_id>/items")
def list_items(category_id):
    if not get_category(category_id):
        return api_error("分类不存在", status=404)
    return api_success({"items": sorted_items_for(category_id)})


@app.post("/api/categories/<category_id>/collect")
def collect_prices(category_id):
    category = get_category(category_id)
    if not category:
        return api_error("分类不存在", status=404)

    payload = request.get_json(silent=True) or {}
    urls = split_urls(payload.get("urls") or payload.get("url") or "")
    if not urls:
        return api_error("请至少输入一个商品网址")

    max_batch_size = int(crawler_config["max_batch_size"])
    if len(urls) > max_batch_size:
        return api_error(f"单次最多支持 {max_batch_size} 个网址")

    added = []
    failures = []
    data = get_session_data()

    for url in urls:
        result = crawler.collect(url)
        if result["ok"]:
            item = {
                "id": uuid.uuid4().hex,
                "url": result["url"],
                "platform": result["platform"],
                "price": result["price"],
                "price_display": result["price_display"],
                "price_source": result["price_source"],
                "title": result["title"],
                "collected_at": result["collected_at"],
                "latency_ms": result["latency_ms"],
                "last_error": "",
            }
            with DATA_LOCK:
                data["items"].setdefault(category_id, []).append(item)
            added.append(item)
            record_event(True, f"{category['name']} 采集完成", url=result["url"], category_id=category_id, latency_ms=result["latency_ms"])
        else:
            failures.append(result)
            record_event(False, result["message"], url=result["url"], category_id=category_id, latency_ms=result["latency_ms"])

    return api_success(
        {
            "added": added,
            "failures": failures,
            "items": sorted_items_for(category_id),
            "categories": serialize_categories(),
        }
    )


@app.post("/api/categories/<category_id>/refresh")
def refresh_prices(category_id):
    category = get_category(category_id)
    if not category:
        return api_error("分类不存在", status=404)

    data = get_session_data()
    items = list(data["items"].get(category_id, []))
    if not items:
        return api_success({"updated": [], "failures": [], "items": []})

    updated = []
    failures = []

    for item in items:
        result = crawler.collect(item["url"])
        if result["ok"]:
            with DATA_LOCK:
                item.update(
                    {
                        "url": result["url"],
                        "platform": result["platform"],
                        "price": result["price"],
                        "price_display": result["price_display"],
                        "price_source": result["price_source"],
                        "title": result["title"],
                        "collected_at": result["collected_at"],
                        "latency_ms": result["latency_ms"],
                        "last_error": "",
                    }
                )
            updated.append(item)
            record_event(True, f"{category['name']} 刷新完成", url=result["url"], category_id=category_id, latency_ms=result["latency_ms"])
        else:
            with DATA_LOCK:
                item["last_error"] = result["message"]
                item["last_checked_at"] = now_text()
            failures.append(result)
            record_event(False, result["message"], url=result["url"], category_id=category_id, latency_ms=result["latency_ms"])

    return api_success({"updated": updated, "failures": failures, "items": sorted_items_for(category_id)})


@app.delete("/api/categories/<category_id>/items")
def clear_items(category_id):
    if not get_category(category_id):
        return api_error("分类不存在", status=404)
    data = get_session_data()
    with DATA_LOCK:
        cleared = len(data["items"].get(category_id, []))
        data["items"][category_id] = []
    return api_success({"cleared": cleared, "items": [], "categories": serialize_categories()})


@app.get("/api/config")
def get_config():
    with DATA_LOCK:
        return api_success({"config": crawler_config})


@app.put("/api/config")
def update_config():
    payload = request.get_json(silent=True) or {}
    with DATA_LOCK:
        if "timeout_seconds" in payload:
            timeout = int(payload["timeout_seconds"])
            if timeout < 1 or timeout > 15:
                return api_error("采集超时时间需在 1 到 15 秒之间")
            crawler_config["timeout_seconds"] = timeout

        if "max_batch_size" in payload:
            max_batch_size = int(payload["max_batch_size"])
            if max_batch_size < 1 or max_batch_size > 50:
                return api_error("批量网址数量需在 1 到 50 之间")
            crawler_config["max_batch_size"] = max_batch_size

        if "enabled_platforms" in payload and isinstance(payload["enabled_platforms"], dict):
            for platform, enabled in payload["enabled_platforms"].items():
                if platform in crawler_config["enabled_platforms"]:
                    crawler_config["enabled_platforms"][platform] = bool(enabled)

    return api_success({"config": crawler_config})


@app.get("/api/metrics")
def get_metrics():
    with DATA_LOCK:
        total = metrics["success"] + metrics["failure"]
        avg_latency = round(metrics["total_latency_ms"] / total, 2) if total else 0
        success_rate = round(metrics["success"] / total * 100, 2) if total else 0
        payload = {
            "success": metrics["success"],
            "failure": metrics["failure"],
            "total": total,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "logs": list(metrics["logs"]),
        }
    return api_success({"metrics": payload})


@app.errorhandler(404)
def not_found(_):
    return api_error("接口不存在", status=404)


@app.errorhandler(500)
def internal_error(error):
    logger.exception("服务器内部错误：%s", error)
    return api_error("服务器内部错误", status=500)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=True)
