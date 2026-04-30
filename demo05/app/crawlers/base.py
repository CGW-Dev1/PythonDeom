import random
import re
import time
from abc import ABC, abstractmethod


class BaseSeleniumRentCrawler(ABC):
    platform_name = "base"
    city_urls = {}

    def __init__(
        self,
        city="bj",
        headless=True,
        min_delay=1.5,
        max_delay=4.0,
        page_load_timeout=25,
    ):
        self.city = city
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.page_load_timeout = page_load_timeout
        self.driver = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.stop()

    def start(self):
        if self.driver is not None:
            return

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1366,900")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.page_load_timeout)

    def stop(self):
        if self.driver is not None:
            self.driver.quit()
            self.driver = None

    def collect(self, max_pages=3):
        self.start()
        records = []
        for page in range(1, max_pages + 1):
            url = self.build_url(page)
            self.driver.get(url)
            self.wait_for_ready()
            self.scroll_page()
            records.extend(self.parse_current_page(page_url=url))
            self.polite_sleep()
        return records

    def wait_for_ready(self):
        from selenium.webdriver.support.ui import WebDriverWait

        WebDriverWait(self.driver, self.page_load_timeout).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )

    def scroll_page(self):
        for ratio in (0.35, 0.7, 1.0):
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight * arguments[0]);",
                ratio,
            )
            time.sleep(random.uniform(0.4, 0.9))

    def polite_sleep(self):
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    @abstractmethod
    def build_url(self, page):
        raise NotImplementedError

    @abstractmethod
    def parse_current_page(self, page_url):
        raise NotImplementedError

    def parse_card_text(self, text):
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text:
            return {}

        price = self.find_first(
            [
                r"(\d+(?:\.\d+)?\s*万)\s*(?:元)?/?月",
                r"(\d+(?:\.\d+)?)\s*元\s*/?\s*月",
                r"月租\s*(\d+(?:\.\d+)?)",
            ],
            text,
        )
        area = self.find_first([r"(\d+(?:\.\d+)?)\s*(?:㎡|m²|m2|平米|平)"], text)
        house_type = self.find_first(
            [
                r"([一二两三四五六七八九十\d]+\s*室\s*[一二两三四五六七八九十\d]*\s*厅?)",
                r"(开间)",
            ],
            text,
        )
        orientation = self.find_first(
            [r"(南北|东西|东南|西南|东北|西北|朝南|朝北|朝东|朝西|南|北|东|西)"],
            text,
        )
        floor = self.find_first(
            [r"((?:低|中|高)楼层\s*/?\s*\d+层)", r"(\d+/\d+层)", r"(\d+层)"],
            text,
        )

        return {
            "rent_price": price,
            "area": area,
            "house_type": house_type,
            "orientation": orientation,
            "floor": floor,
        }

    @staticmethod
    def find_first(patterns, text):
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def text_from_first(element, selectors):
        for selector in selectors:
            try:
                found = element.find_element("css selector", selector)
                value = found.text.strip()
                if value:
                    return value
            except Exception:
                continue
        return ""

    @staticmethod
    def attr_from_first(element, selectors, attr):
        for selector in selectors:
            try:
                found = element.find_element("css selector", selector)
                value = found.get_attribute(attr)
                if value:
                    return value
            except Exception:
                continue
        return ""
