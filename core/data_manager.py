import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from astrbot.api import logger
from astrbot.api.star import StarTools

from .constant import DATA_PATH, DEFAULT_CFG, RECENT_DYNAMIC_CACHE
from .models import SubscriptionRecord


class DataManager:
    """
    负责管理插件的订阅数据，包括加载、保存和修改。
    """

    def __init__(self, recent_dynamic_cache: int = RECENT_DYNAMIC_CACHE):
        self.recent_dynamic_cache = recent_dynamic_cache
        standard_data_path = os.path.join(
            StarTools.get_data_dir(plugin_name="astrbot_plugin_bilibili"),
            "astrbot_plugin_bilibili.json",
        )
        if os.path.exists(DATA_PATH) and not os.path.exists(standard_data_path):
            # 复制旧数据文件到标准路径
            os.makedirs(os.path.dirname(standard_data_path), exist_ok=True)
            with open(DATA_PATH, "r", encoding="utf-8-sig") as src:
                with open(standard_data_path, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            logger.info(f"已将旧数据文件迁移到标准路径: {standard_data_path}")
        self.path = standard_data_path
        self.data = self._load_data()
        self._normalize_subscriptions()
        self._normalize_runtime_fields()

    def _load_data(self) -> Dict[str, Any]:
        """
        从 JSON 文件加载数据。如果文件不存在，则创建并使用默认配置。
        """
        if not os.path.exists(self.path):
            logger.info(f"数据文件不存在，将创建于: {self.path}")
            # 确保目录存在
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8-sig") as f:
                json.dump(DEFAULT_CFG, f, ensure_ascii=False, indent=4)
            return DEFAULT_CFG

        with open(self.path, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def _normalize_subscriptions(self) -> None:
        normalized: Dict[str, List[SubscriptionRecord]] = {}
        raw_subs = self.data.get("bili_sub_list", {})
        if not isinstance(raw_subs, dict):
            self.data["bili_sub_list"] = {}
            return

        for sub_user, sub_list in raw_subs.items():
            if not isinstance(sub_list, list):
                continue
            records: List[SubscriptionRecord] = []
            for raw_sub in sub_list:
                if not isinstance(raw_sub, dict):
                    continue
                try:
                    records.append(SubscriptionRecord.from_dict(raw_sub))
                except ValueError:
                    logger.warning(f"跳过无效订阅记录: {raw_sub}")
                    continue
            if records:
                normalized[sub_user] = records
        self.data["bili_sub_list"] = normalized

    def _serialize_data(self) -> Dict[str, Any]:
        payload = dict(self.data)
        payload["bili_sub_list"] = {
            sub_user: [record.to_dict() for record in records]
            for sub_user, records in self.get_all_subscriptions().items()
        }
        return payload

    def _normalize_runtime_fields(self) -> None:
        parsed_ts = int(self.data.get("last_success_sub_notify_ts", 0))
        self.data["last_success_sub_notify_ts"] = max(parsed_ts, 0)

    @staticmethod
    def _write_text(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    async def save(self):
        payload = json.dumps(self._serialize_data(), ensure_ascii=False, indent=2)
        await asyncio.to_thread(self._write_text, self.path, payload)

    def get_all_subscriptions(self) -> Dict[str, List[SubscriptionRecord]]:
        """
        获取所有的订阅列表。
        """
        subs = self.data.setdefault("bili_sub_list", {})
        if not isinstance(subs, dict):
            self.data["bili_sub_list"] = {}
            return self.data["bili_sub_list"]
        return subs

    def get_subscriptions_by_user(
        self, sub_user: str
    ) -> Optional[List[SubscriptionRecord]]:
        """
        根据 sub_user 获取其订阅的UP主列表。
        sub_user: 订阅用户的唯一标识, 形如 "aipcqhttp:GroupMessage:123456"
        """
        return self.get_all_subscriptions().get(sub_user)

    def get_subscription(self, sub_user: str, uid: int) -> Optional[SubscriptionRecord]:
        """
        获取特定用户对特定UP主的订阅信息。
        """
        user_subs = self.get_subscriptions_by_user(sub_user)
        if user_subs:
            for sub in user_subs:
                if sub.uid == uid:
                    return sub
        return None

    async def add_subscription(self, sub_user: str, sub_data: SubscriptionRecord):
        """
        为用户添加一条新的订阅。
        """
        all_subs = self.get_all_subscriptions()
        if sub_user not in all_subs:
            all_subs[sub_user] = []
        existing = self.get_subscription(sub_user, sub_data.uid)
        if existing:
            existing.last = sub_data.last
            existing.is_live = sub_data.is_live
            existing.filter_types = list(sub_data.filter_types)
            existing.filter_regex = list(sub_data.filter_regex)
            existing.recent_ids = list(sub_data.recent_ids)
            existing.live_atall = sub_data.live_atall
            existing.last_live_start_ts = sub_data.last_live_start_ts
            existing.at_all = sub_data.at_all
            existing.at_sub_users = list(sub_data.at_sub_users)
        else:
            all_subs[sub_user].append(sub_data)
        await self.save()

    async def update_subscription(
        self,
        sub_user: str,
        uid: int,
        filter_types: List[str],
        filter_regex: List[str],
        live_atall: bool,
        at_all: Optional[bool] = None,
        add_sub_users: Optional[List[str]] = None,
        rm_sub_users: Optional[List[str]] = None,
        inherit_filters: bool = False,
    ):
        """
        更新一个已存在的订阅的过滤条件及 @ 提醒设置。
        """
        sub = self.get_subscription(sub_user, uid)
        if sub:
            sub.update_filters(
                filter_types,
                filter_regex,
                live_atall,
                at_all=at_all,
                add_sub_users=add_sub_users,
                rm_sub_users=rm_sub_users,
                inherit_filters=inherit_filters,
            )
            await self.save()
            return True
        return False

    def get_credential(self) -> Optional[Dict[str, Any]]:
        """
        获取保存的凭据。
        """
        return self.data.get("credential")

    def get_last_success_sub_notify_ts(self) -> int:
        parsed_ts = int(self.data.get("last_success_sub_notify_ts", 0))
        return max(parsed_ts, 0)

    async def set_last_success_sub_notify_ts(self, ts: int) -> None:
        next_ts = max(int(ts), 0)
        if self.get_last_success_sub_notify_ts() == next_ts:
            return
        self.data["last_success_sub_notify_ts"] = next_ts
        await self.save()

    async def set_credential(self, credential_data: Dict[str, Any] | None):
        """
        保存凭据。
        """
        if credential_data is None:
            raise ValueError("credential_data 不能为空")
        self.data["credential"] = credential_data
        await self.save()

    async def clear_credential(self):
        """
        清除保存的凭据。
        """
        if "credential" in self.data:
            del self.data["credential"]
            await self.save()

    async def update_last_dynamic_id(self, sub_user: str, uid: int, dyn_id: str):
        """
        更新订阅的最新动态ID。
        """
        sub = self.get_subscription(sub_user, uid)
        if sub:
            sub.record_dynamic(dyn_id, self.recent_dynamic_cache)
            await self.save()

    async def update_live_status(self, sub_user: str, uid: int, is_live: bool):
        """
        更新特定订阅的直播状态。
        """
        sub = self.get_subscription(sub_user, uid)
        if sub:
            sub.is_live = is_live
            await self.save()

    async def remove_subscription(self, sub_user: str, uid: int) -> bool:
        """
        移除一条订阅。
        """
        user_subs = self.get_subscriptions_by_user(sub_user)
        if not user_subs:
            return False

        sub_to_remove = None
        for sub in user_subs:
            if sub.uid == uid:
                sub_to_remove = sub
                break

        if sub_to_remove:
            user_subs.remove(sub_to_remove)
            # 如果该用户已无任何订阅，可以选择移除该用户键
            if not user_subs:
                del self.data["bili_sub_list"][sub_user]
            await self.save()
            return True

        return False

    async def remove_all_for_user(self, sid: str):
        """
        移除一个用户的所有订阅（用于管理员指令）。
        """
        candidate = []
        for sub_user in self.get_all_subscriptions():
            third = sub_user.split(":")[2]
            if third == str(sid) or sid == sub_user:
                candidate.append(sub_user)

        if not candidate:
            msg = "未找到订阅"
            return msg

        if len(candidate) == 1:
            self.data["bili_sub_list"].pop(candidate[0])
            await self.save()
            msg = f"删除 {sid} 订阅成功"
            return msg

        msg = "找到多个订阅者: " + ", ".join(candidate)
        return msg
