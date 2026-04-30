import hashlib
import json
import re


class RentDataCleaner:
    """Normalize rental records collected from different platforms."""

    PRICE_MIN = 200
    PRICE_MAX = 100000
    AREA_MIN = 5
    AREA_MAX = 500
    UNIT_PRICE_MAX = 1200

    CHINESE_NUMBERS = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    def clean_records(self, records):
        cleaned = []
        seen = set()

        for record in records:
            item = self.clean_record(record)
            if not item:
                continue

            dedup_key = (
                item["district"],
                item["community"],
                item["house_type"],
                round(item["area"], 1),
                round(item["rent_price"], 0),
            )
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            cleaned.append(item)

        return cleaned

    def clean_record(self, record):
        district = self.normalize_text(record.get("district"))
        community = self.normalize_text(record.get("community"))
        house_type = self.normalize_house_type(record.get("house_type"))
        rent_price = self.parse_price(record.get("rent_price"))
        area = self.parse_area(record.get("area"))

        if not district or not community or not house_type:
            return None
        if rent_price is None or area is None:
            return None
        if not self.is_reasonable(rent_price, area):
            return None

        orientation = self.normalize_orientation(record.get("orientation"))
        floor = self.normalize_text(record.get("floor"))
        tags = self.normalize_tags(record.get("tags"))
        publish_time = self.normalize_text(record.get("publish_time"))
        unit_price = round(rent_price / area, 2)

        cleaned = {
            "source": self.normalize_text(record.get("source")) or "unknown",
            "source_id": self.normalize_text(record.get("source_id")),
            "detail_url": self.normalize_text(record.get("detail_url")),
            "district": district,
            "community": community,
            "rent_price": float(rent_price),
            "area": float(area),
            "house_type": house_type,
            "orientation": orientation,
            "floor": floor,
            "tags": tags,
            "publish_time": publish_time,
            "unit_price": unit_price,
        }
        cleaned["raw_hash"] = self.make_hash(cleaned)
        return cleaned

    @classmethod
    def normalize_text(cls, value):
        if value is None:
            return ""
        text = str(value)
        text = text.replace("\xa0", " ").replace("\u3000", " ")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"[^\w\u4e00-\u9fff/.\-·（）()：: ]", "", text)
        return text

    @classmethod
    def parse_price(cls, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).replace(",", "").strip()
        if not text or "面议" in text:
            return None

        wan_match = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
        if wan_match:
            return round(float(wan_match.group(1)) * 10000, 2)

        yuan_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb)?\s*/?\s*(?:月|每月)?", text, re.I)
        if yuan_match:
            return round(float(yuan_match.group(1)), 2)
        return None

    @classmethod
    def parse_area(cls, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).replace(",", "")
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²|平|平方米)?", text, re.I)
        if match:
            return float(match.group(1))
        return None

    @classmethod
    def normalize_house_type(cls, value):
        text = cls.normalize_text(value)
        if not text:
            return ""
        if "开间" in text:
            return "开间"

        text = text.replace("房", "室").replace("卧", "室")
        match = re.search(
            r"([一二两三四五六七八九十\d]+)\s*室\s*([一二两三四五六七八九十\d]*)\s*厅?",
            text,
        )
        if match:
            rooms = cls.to_digit(match.group(1))
            halls = cls.to_digit(match.group(2)) if match.group(2) else 0
            return f"{rooms}室{halls}厅"

        short_match = re.search(r"([一二两三四五六七八九十\d]+)\s*室", text)
        if short_match:
            rooms = cls.to_digit(short_match.group(1))
            return f"{rooms}室0厅"
        return text[:30]

    @classmethod
    def to_digit(cls, value):
        if not value:
            return 0
        if str(value).isdigit():
            return int(value)
        if value == "十":
            return 10
        if "十" in value:
            left, _, right = value.partition("十")
            return cls.CHINESE_NUMBERS.get(left, 1) * 10 + cls.CHINESE_NUMBERS.get(right, 0)
        return cls.CHINESE_NUMBERS.get(value, 0)

    @classmethod
    def normalize_orientation(cls, value):
        text = cls.normalize_text(value)
        if not text:
            return ""
        direction_words = ["东南", "西南", "东北", "西北", "南北", "东西", "南", "北", "东", "西"]
        found = []
        for word in direction_words:
            if word in text and word not in found:
                found.append(word)
        if found:
            return "/".join(found[:2])
        return text[:30]

    @classmethod
    def normalize_tags(cls, value):
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            tags = [cls.normalize_text(item) for item in value]
        else:
            tags = re.split(r"[,，、|/ ]+", str(value))
            tags = [cls.normalize_text(item) for item in tags]
        return "、".join([tag for tag in tags if tag])

    @classmethod
    def is_reasonable(cls, rent_price, area):
        if rent_price < cls.PRICE_MIN or rent_price > cls.PRICE_MAX:
            return False
        if area < cls.AREA_MIN or area > cls.AREA_MAX:
            return False
        if rent_price / area > cls.UNIT_PRICE_MAX:
            return False
        return True

    @classmethod
    def make_hash(cls, item):
        key = {
            "district": item.get("district"),
            "community": item.get("community"),
            "house_type": item.get("house_type"),
            "area": round(float(item.get("area") or 0), 1),
            "rent_price": round(float(item.get("rent_price") or 0), 0),
        }
        payload = json.dumps(key, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
