from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..core.constant import VALID_FILTER_TYPES
from ..core.data_manager import DataManager
from ..core.models import SubscriptionRecord
from ..core.utils import is_valid_umo, parse_bilibili_uid
from .subscription_service import SubscriptionApplyResult, SubscriptionService

MAX_FILTER_REGEX_COUNT = 20
MAX_FILTER_REGEX_LENGTH = 200
MAX_AT_SUB_USERS = 100


@dataclass(frozen=True)
class PageSubscriptionInput:
    umo: str
    uid: int
    filter_types: list[str]
    filter_regex: list[str]
    live_atall: bool
    at_all: bool
    at_sub_users: list[str]


class SubscriptionPageService:
    """为订阅管理 Page 提供与界面无关的查询和写入能力。"""

    def __init__(
        self,
        data_manager: DataManager,
        subscription_service: SubscriptionService,
    ) -> None:
        self.data_manager = data_manager
        self.subscription_service = subscription_service

    @staticmethod
    def serialize_record(record: SubscriptionRecord) -> dict[str, Any]:
        """将订阅记录转换为可安全返回给 Page 的数据。"""
        return {
            "uid": str(record.uid),
            "last": record.last,
            "is_live": record.is_live,
            "filter_types": list(record.filter_types),
            "filter_regex": list(record.filter_regex),
            "live_atall": record.live_atall,
            "last_live_start_ts": record.last_live_start_ts,
            "at_all": record.at_all,
            "at_sub_users": list(record.at_sub_users),
        }

    def list_subscriptions(self, keyword: str = "") -> dict[str, Any]:
        """返回全部会话及订阅；keyword 仅用于服务端过滤，避免泄露无关数据。"""
        needle = keyword.strip().lower()
        sessions = []
        total = 0
        live_count = 0

        for umo, records in self.data_manager.get_all_subscriptions().items():
            entries = [self.serialize_record(record) for record in records]
            if needle:
                entries = [
                    entry
                    for entry in entries
                    if needle in umo.lower() or needle in str(entry["uid"])
                ]
            if not entries:
                continue
            total += len(entries)
            live_count += sum(1 for entry in entries if entry["is_live"])
            sessions.append(
                {
                    "umo": umo,
                    "subscriptions": entries,
                    "count": len(entries),
                }
            )

        sessions.sort(key=lambda item: item["umo"])
        return {
            "sessions": sessions,
            "summary": {
                "session_count": len(sessions),
                "subscription_count": total,
                "live_count": live_count,
            },
        }

    @staticmethod
    def parse_input(payload: Any) -> PageSubscriptionInput:
        """严格验证 Page 写入载荷，避免未受信任输入进入订阅数据。"""
        if not isinstance(payload, dict):
            raise TypeError("请求体必须是 JSON 对象。")

        umo = str(payload.get("umo", "")).strip()
        if len(umo) > 300 or not is_valid_umo(umo):
            raise ValueError("UMO 格式无效。")

        uid = parse_bilibili_uid(payload.get("uid"))

        raw_types = payload.get("filter_types", [])
        if not isinstance(raw_types, list) or not all(
            isinstance(item, str) for item in raw_types
        ):
            raise ValueError("过滤类型必须是字符串数组。")
        filter_types = list(dict.fromkeys(item.strip() for item in raw_types if item.strip()))
        invalid_types = set(filter_types) - VALID_FILTER_TYPES
        if invalid_types:
            raise ValueError(f"不支持的过滤类型: {', '.join(sorted(invalid_types))}。")

        raw_regex = payload.get("filter_regex", [])
        if not isinstance(raw_regex, list) or not all(
            isinstance(item, str) for item in raw_regex
        ):
            raise ValueError("正则过滤器必须是字符串数组。")
        filter_regex = list(
            dict.fromkeys(item.strip() for item in raw_regex if item.strip())
        )
        if len(filter_regex) > MAX_FILTER_REGEX_COUNT:
            raise ValueError(f"正则过滤器最多 {MAX_FILTER_REGEX_COUNT} 条。")
        if any(len(item) > MAX_FILTER_REGEX_LENGTH for item in filter_regex):
            raise ValueError(f"单条正则过滤器最长 {MAX_FILTER_REGEX_LENGTH} 个字符。")
        for regex_pattern in filter_regex:
            try:
                re.compile(regex_pattern)
            except re.error as exc:
                raise ValueError(f"无效的正则表达式：{regex_pattern}。") from exc

        for key in ("live_atall", "at_all"):
            if not isinstance(payload.get(key, False), bool):
                raise TypeError(f"{key} 必须是布尔值。")

        raw_users = payload.get("at_sub_users", [])
        if not isinstance(raw_users, list):
            raise TypeError("特定提醒用户必须是数组。")
        at_sub_users = list(
            dict.fromkeys(str(item).strip() for item in raw_users if str(item).strip())
        )
        if len(at_sub_users) > MAX_AT_SUB_USERS:
            raise ValueError(f"特定提醒用户最多 {MAX_AT_SUB_USERS} 人。")
        if any(len(item) > 100 for item in at_sub_users):
            raise ValueError("特定提醒用户 ID 过长。")

        return PageSubscriptionInput(
            umo=umo,
            uid=uid,
            filter_types=filter_types,
            filter_regex=filter_regex,
            live_atall=bool(payload.get("live_atall", False)),
            at_all=bool(payload.get("at_all", False)),
            at_sub_users=at_sub_users,
        )

    async def save(self, payload: Any) -> tuple[SubscriptionApplyResult, bool]:
        """创建或完整更新一条订阅，返回结果和是否为更新。"""
        data = self.parse_input(payload)
        previous = self.data_manager.get_subscription(data.umo, data.uid)
        old_users = set(previous.at_sub_users) if previous else set()
        new_users = set(data.at_sub_users)
        result = await self.subscription_service.add_or_update(
            data.umo,
            data.uid,
            data.filter_types,
            data.filter_regex,
            data.live_atall,
            at_all=data.at_all,
            add_sub_users=sorted(new_users - old_users),
            rm_sub_users=sorted(old_users - new_users),
        )
        return result, previous is not None

    async def delete_subscription(self, umo: Any, uid: Any) -> bool:
        valid_umo, valid_uid = self._parse_identifier(umo, uid)
        return await self.subscription_service.remove(valid_umo, valid_uid)

    async def delete_session(self, umo: Any) -> bool:
        valid_umo = str(umo or "").strip()
        if len(valid_umo) > 300 or not is_valid_umo(valid_umo):
            raise ValueError("UMO 格式无效。")
        return await self.subscription_service.remove_all_for_session(valid_umo)

    @staticmethod
    def _parse_identifier(umo: Any, uid: Any) -> tuple[str, int]:
        valid_umo = str(umo or "").strip()
        if len(valid_umo) > 300 or not is_valid_umo(valid_umo):
            raise ValueError("UMO 格式无效。")
        return valid_umo, parse_bilibili_uid(uid)
