from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests

from config import Config


class HonguoClient:
    BASE_URL = "https://orz.icic.icu/api/hguo/api.php"
    PREVIEW_URL = "https://orz.icic.icu/api/hguo/hgm.php"
    UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    TIMEOUT = 15

    def __init__(self, config: Config) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.UA})

    def _request_url(self, url: str, params: Dict[str, Any]) -> Tuple[bool, Any, str]:
        try:
            response = self._session.get(url, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            return False, None, f"网络错误: {exc}"

        try:
            payload = response.json()
        except ValueError:
            return False, None, "响应解析失败"

        code = payload.get("code")
        msg = str(payload.get("msg") or "")
        data = payload.get("data")

        ok = False
        if isinstance(code, int):
            ok = code == 200
        elif isinstance(code, str):
            ok = code == "200"
        elif isinstance(code, bool):
            ok = code

        if ok:
            return True, data, msg or "请求成功"
        return False, data, msg or "请求失败"

    def _request(self, params: Dict[str, Any]) -> Tuple[bool, Any, str]:
        return self._request_url(self.BASE_URL, params)

    def _level_to_numeric(self, level: str) -> str:
        normalized = (level or "").strip().upper()
        if normalized in {"1080P+", "1080P"}:
            return "3"
        if normalized == "720P":
            return "2"
        return "1"

    def search(self, name: str, page: int = 1) -> Tuple[bool, List[Dict[str, Any]], str]:
        ok, data, msg = self._request({"action": "search", "name": name, "page": page})
        if not ok or not isinstance(data, list):
            return False, [], msg or "搜索失败"
        return True, data, msg or "搜索成功"

    def today_new(self) -> Tuple[bool, List[Dict[str, Any]], str]:
        ok, data, msg = self._request({"action": "today_new"})
        if not ok or not isinstance(data, list):
            return False, [], msg or "获取失败"
        return True, data, msg or "获取成功"

    def get_episodes(self, book_id: str) -> Tuple[bool, List[Dict[str, Any]], str]:
        if self.config.is_key_set:
            params = {
                "action": "get_list",
                "key": self.config.key,
                "machine_id": self.config.machine_id,
                "book_id": book_id,
            }
            ok, data, msg = self._request(params)
        else:
            ok, data, msg = self._request_url(self.PREVIEW_URL, {"book_id": book_id})
        if not ok or not isinstance(data, list):
            return False, [], msg or "获取失败"
        return True, data, msg or "获取成功"

    def get_video_url(self, video_id: str, level: str = "1080P+") -> Tuple[bool, Dict[str, Any], str]:
        if self.config.is_key_set:
            video_level = level or self.config.level or "1080P+"
            params = {
                "action": "get_detail",
                "key": self.config.key,
                "machine_id": self.config.machine_id,
                "video_id": video_id,
                "level": video_level,
            }
            ok, data, msg = self._request(params)
        else:
            preferred_level = level or self.config.level or "1080P+"
            params = {
                "video_id": video_id,
                "level": self._level_to_numeric(preferred_level),
            }
            ok, data, msg = self._request_url(self.PREVIEW_URL, params)
        if not ok or not isinstance(data, dict):
            return False, {}, msg or "获取失败"
        if not self.config.is_key_set:
            url = str(data.get("url") or "")
            if not url:
                return False, {}, msg or "播放链接缺失"
        return True, data, msg or "获取成功"

    def check_version(self) -> Tuple[bool, Dict[str, Any], str]:
        ok, data, msg = self._request({"action": "version"})
        if not ok or not isinstance(data, dict):
            return False, {}, msg or "获取失败"
        return True, data, msg or "获取成功"

    def get_buy_url(self) -> Tuple[bool, str, str]:
        ok, data, msg = self._request({"action": "get_buy_url"})
        if not ok or not isinstance(data, dict):
            return False, "", msg or "获取失败"
        buy_url = str(data.get("buy_url") or "")
        if not buy_url:
            return False, "", msg or "链接缺失"
        return True, buy_url, msg or "获取成功"
