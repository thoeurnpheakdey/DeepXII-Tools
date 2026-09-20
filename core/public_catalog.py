"""Read the public Hongguo catalogue without private APIs.

The HTML selectors are adapted from the MIT-licensed project
https://github.com/lingbol088-spec/short-drama-downloader.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://hongguoduanju.com"
CATEGORY_QUERIES = {
    "modern": "background=cate_757",
    "urban": "background=cate_1",
    "historical": "background=cate_758",
    "rural": "background=cate_11",
    "workplace": "background=cate_127",
    "fantasy": "topic=cate_1020",
    "romance": "topic=cate_1021",
    "ceo": "setting=cate_936",
    "rebirth": "setting=cate_36",
    "time travel": "setting=cate_37",
    "system": "setting=cate_19",
    "comedy": "topic=cate_303",
}
ALL_CATALOG_QUERIES = ("sort_type=2", "sort_type=1", *CATEGORY_QUERIES.values())
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_catalog(html: str) -> List[Dict[str, str]]:
    """Extract public series cards from a Hongguo catalogue page."""
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, str]] = []
    seen = set()
    for anchor in soup.select('a[href*="/detail?series_id="]'):
        href = str(anchor.get("href") or "")
        detail_url = urljoin(BASE_URL, href)
        series_id = (parse_qs(urlparse(detail_url).query).get("series_id") or [""])[0]
        if not series_id or series_id in seen:
            continue
        seen.add(series_id)

        texts = [_clean(value) for value in anchor.stripped_strings if _clean(value)]
        episode_text = next((value for value in texts if re.search(r"全?\d+集", value)), "")
        title_node = anchor.select_one('[class*="title"]')
        title = _clean(title_node.get_text(" ")) if title_node else ""
        if not title:
            candidates = [value for value in texts if value != episode_text]
            title = candidates[0] if candidates else series_id
        image = anchor.select_one("img")
        cover_url = ""
        if image is not None:
            for attribute in ("src", "data-src", "data-original", "data-lazy-src"):
                candidate = _clean(image.get(attribute))
                if candidate and not candidate.startswith("data:"):
                    cover_url = urljoin(BASE_URL, candidate)
                    break
            if not cover_url:
                srcset = _clean(image.get("srcset"))
                if srcset:
                    cover_url = urljoin(BASE_URL, srcset.split(",")[0].strip().split(" ")[0])
        results.append(
            {
                "title": title,
                "book_id": series_id,
                "episode_total": episode_text,
                "cover_url": cover_url,
                "type": "红果短剧",
                "source_url": detail_url,
            }
        )
    return results


def search_catalog(keyword: str, category: str = "all", timeout: int = 20) -> List[Dict[str, str]]:
    """Fetch public pages and filter series locally by title."""
    all_items: List[Dict[str, str]] = []
    seen = set()
    errors: List[Exception] = []
    normalized_category = category.strip().lower() or "all"
    if normalized_category == "all":
        urls = [f"{BASE_URL}/category?{query}" for query in ALL_CATALOG_QUERIES]
        urls.append(BASE_URL)
    else:
        query = CATEGORY_QUERIES.get(normalized_category, "sort_type=1")
        urls = [f"{BASE_URL}/category?{query}"]

    def fetch(url: str) -> List[Dict[str, str]]:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        return parse_catalog(response.text)

    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="catalog") as executor:
        futures = [executor.submit(fetch, url) for url in urls]
        for future in as_completed(futures):
            try:
                items = future.result()
            except requests.RequestException as exc:
                errors.append(exc)
                continue
            for item in items:
                if item["book_id"] not in seen:
                    seen.add(item["book_id"])
                    all_items.append(item)
    if not all_items and errors:
        raise RuntimeError(f"无法读取红果公开目录: {errors[-1]}") from errors[-1]
    needle = keyword.strip().casefold()
    if not needle:
        return all_items
    return [item for item in all_items if needle in item["title"].casefold()]
