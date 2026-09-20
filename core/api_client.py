from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

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
        self.base_url = os.environ.get("HONGGUO_API_BASE_URL", self.BASE_URL).strip()
        self.preview_url = os.environ.get("HONGGUO_PREVIEW_URL", self.PREVIEW_URL).strip()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.UA})
        self._public_video_pages: Dict[str, Tuple[str, int]] = {}

    @staticmethod
    def _extract_router_data(html: str) -> Dict[str, Any]:
        marker_index = html.find("_ROUTER_DATA")
        start = html.find("{", marker_index) if marker_index >= 0 else -1
        if start < 0:
            return {}
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(html)):
            char = html[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(html[start:index + 1])
                        return value if isinstance(value, dict) else {}
                    except json.JSONDecodeError:
                        return {}
        return {}

    @staticmethod
    def _find_player_page(router: Dict[str, Any]) -> Dict[str, Any]:
        loader_data = router.get("loaderData")
        if isinstance(loader_data, dict):
            for value in loader_data.values():
                if isinstance(value, dict) and isinstance(value.get("seriesDetail"), dict):
                    return value
        return {}

    def _public_player_page(
        self, series_id: str, video_id: str = "", episode_num: int = 1
    ) -> Tuple[bool, Dict[str, Any], str]:
        suffix = f"/{video_id}" if episode_num > 1 and video_id else ""
        url = f"https://hongguoduanju.com/player/{series_id}{suffix}"
        try:
            response = self._session.get(url, timeout=self.TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            return False, {}, f"Public player request failed: {exc}"
        page = self._find_player_page(self._extract_router_data(response.text))
        if not page:
            return False, {}, "The public player returned no episode data"
        return True, page, "Public episode data loaded"

    def _request_url(self, url: str, params: Dict[str, Any]) -> Tuple[bool, Any, str]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return (
                False,
                None,
                "API 地址无效。请把 HONGGUO_API_BASE_URL 设置为团队提供的完整 "
                "https:// 地址；不要使用 CURRENT_API_URL 示例文字。",
            )
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
        return self._request_url(self.base_url, params)

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
                "key": self.config.effective_key,
                "machine_id": self.config.machine_id,
                "book_id": book_id,
            }
            ok, data, msg = self._request(params)
        else:
            ok, data, msg = self._request_url(self.preview_url, {"book_id": book_id})
        if not ok or not isinstance(data, list) or not data:
            public_ok, page, public_msg = self._public_player_page(book_id)
            if not public_ok:
                return False, [], public_msg or msg or "Unable to load episodes"
            details = page.get("seriesDetail")
            details = details if isinstance(details, dict) else {}
            video_ids = details.get("vid_list")
            video_ids = video_ids if isinstance(video_ids, list) else []
            try:
                accessible = int(details.get("accessible_episode_cnt") or 0)
            except (TypeError, ValueError):
                accessible = 0
            limit = min(accessible, len(video_ids)) if accessible > 0 else len(video_ids)
            public_episodes: List[Dict[str, Any]] = []
            for index, value in enumerate(video_ids[:limit], start=1):
                video_id = str(value or "")
                if not video_id:
                    continue
                self._public_video_pages[video_id] = (book_id, index)
                public_episodes.append({
                    "video_id": video_id,
                    "episode_num": index,
                    "title": f"Episode {index}",
                })
            if not public_episodes:
                return False, [], "This drama has no episodes open for public playback"
            return True, public_episodes, f"{len(public_episodes)} public episodes available"
        return True, data, msg or "获取成功"

    def get_video_url(self, video_id: str, level: str = "1080P+") -> Tuple[bool, Dict[str, Any], str]:
        if self.config.is_key_set:
            video_level = level or self.config.level or "1080P+"
            params = {
                "action": "get_detail",
                "key": self.config.effective_key,
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
            ok, data, msg = self._request_url(self.preview_url, params)
        if not ok or not isinstance(data, dict) or not data:
            public_page = self._public_video_pages.get(video_id)
            if public_page is None:
                return False, {}, msg or "Unable to resolve the episode video"
            series_id, episode_num = public_page
            public_ok, page, public_msg = self._public_player_page(series_id, video_id, episode_num)
            if not public_ok:
                return False, {}, public_msg
            player_info = page.get("video_player_info")
            player_info = player_info if isinstance(player_info, dict) else {}
            public_url = str(player_info.get("main_url") or "")
            if not public_url:
                return False, {}, "This episode is not open for public playback"
            return True, {"url": public_url}, "Public video URL loaded"
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
