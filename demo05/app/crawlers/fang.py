from .base import BaseSeleniumRentCrawler


class FangTianXiaCrawler(BaseSeleniumRentCrawler):
    platform_name = "房天下"
    city_urls = {
        "bj": "https://zu.fang.com/house/i3{page}/",
        "sh": "https://zu.sh.fang.com/house/i3{page}/",
        "gz": "https://zu.gz.fang.com/house/i3{page}/",
        "sz": "https://zu.sz.fang.com/house/i3{page}/",
    }

    def build_url(self, page):
        template = self.city_urls.get(self.city, self.city_urls["bj"])
        return template.format(page=page)

    def parse_current_page(self, page_url):
        cards = self.driver.find_elements(
            "css selector",
            ".houseList dl, .list rel, .content__list--item, dl, li",
        )
        records = []
        for index, card in enumerate(cards):
            text = card.text.strip()
            if not text or ("㎡" not in text and "平" not in text):
                continue
            record = self.parse_card_text(text)
            community = self.text_from_first(card, [".title", "h2", "h3", "a"])
            district = self.text_from_first(card, [".gray6", ".address", ".area"])
            detail_url = self.attr_from_first(card, ["a"], "href")

            record.update(
                {
                    "source": self.platform_name,
                    "source_id": f"fang-{self.city}-{index}-{abs(hash(detail_url or text))}",
                    "detail_url": detail_url,
                    "community": community or self.guess_line(text, 0),
                    "district": self.guess_district(district or text),
                    "tags": self.text_from_first(card, [".note", ".tag", ".tags"]),
                    "publish_time": self.text_from_first(card, [".time", ".release-time"]),
                }
            )
            records.append(record)
        return records

    @staticmethod
    def guess_line(text, line_index):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if line_index < len(lines):
            return lines[line_index][:60]
        return ""

    @staticmethod
    def guess_district(text):
        for token in ["朝阳", "海淀", "西城", "东城", "丰台", "通州", "昌平", "大兴", "石景山"]:
            if token in text:
                return token + "区" if not token.endswith("区") else token
        pieces = [piece for piece in text.replace("-", " ").split() if piece]
        return pieces[0][:30] if pieces else ""
