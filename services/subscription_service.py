from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from astrbot.api import logger

from ..bili_client import BiliClient
from ..core.data_manager import DataManager
from ..core.models import DynamicParseResult, SubscriptionRecord

ParseDynamicsFn = Callable[[dict, SubscriptionRecord], List[DynamicParseResult]]


@dataclass
class SubscriptionApplyResult:
    record: SubscriptionRecord
    updated: bool
    initialized: bool


class SubscriptionService:
    def __init__(
        self,
        data_manager: DataManager,
        bili_client: BiliClient,
        parse_dynamics: ParseDynamicsFn,
    ) -> None:
        self.data_manager = data_manager
        self.bili_client = bili_client
        self.parse_dynamics = parse_dynamics

    @staticmethod
    def _create_record(
        uid: int,
        filter_types: List[str],
        filter_regex: List[str],
        live_atall: bool,
        at_all: bool = False,
        at_sub_users: Optional[List[str]] = None,
    ) -> SubscriptionRecord:
        return SubscriptionRecord(
            uid=uid,
            filter_types=list(filter_types),
            filter_regex=list(filter_regex),
            live_atall=live_atall,
            at_all=at_all,
            at_sub_users=list(set(at_sub_users)) if at_sub_users else [],
        )

    async def _init_last_dynamic(
        self, sub_user: str, uid: int, record: SubscriptionRecord
    ) -> bool:
        dyn = await self.bili_client.get_latest_dynamics(uid)
        if not dyn:
            return False
        result_list = self.parse_dynamics(dyn, record)
        for result in reversed(result_list):
            if result.dyn_id:
                await self.data_manager.update_last_dynamic_id(
                    sub_user, uid, result.dyn_id
                )
        return True

    async def add_or_update(
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
    ) -> SubscriptionApplyResult:
        updated = await self.data_manager.update_subscription(
            sub_user,
            uid,
            filter_types,
            filter_regex,
            live_atall,
            at_all=at_all,
            add_sub_users=add_sub_users,
            rm_sub_users=rm_sub_users,
            inherit_filters=inherit_filters,
        )
        if updated:
            record = self.data_manager.get_subscription(sub_user, uid)
            if not record:
                raise RuntimeError("subscription missing after update")
            return SubscriptionApplyResult(
                record=record, updated=True, initialized=False
            )

        record = self._create_record(
            uid,
            filter_types,
            filter_regex,
            live_atall,
            at_all=bool(at_all),
            at_sub_users=add_sub_users,
        )
        await self.data_manager.add_subscription(sub_user, record)
        initialized = False
        try:
            initialized = await self._init_last_dynamic(sub_user, uid, record)
        except Exception as exc:
            logger.error(f"初始化订阅失败 UID={uid}: {exc}")
        return SubscriptionApplyResult(
            record=record, updated=False, initialized=initialized
        )
