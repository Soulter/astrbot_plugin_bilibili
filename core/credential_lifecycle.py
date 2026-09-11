from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol


class CredentialRefreshStatus(str, Enum):
    """登录态维护的脱敏结果。"""

    NOT_MANAGED = "not_managed"
    NOT_REQUIRED = "not_required"
    REFRESHED = "refreshed"
    RELOGIN_REQUIRED = "relogin_required"
    FAILED = "failed"


@dataclass(frozen=True)
class CredentialRefreshResult:
    """凭据维护结果，不包含任何敏感凭据。"""

    status: CredentialRefreshStatus
    reason: str = ""


class CredentialClient(Protocol):
    """凭据维护所需的 BiliClient 最小接口。"""

    credential: Any

    def _apply_proxy(self) -> None: ...

    def get_credential_dict(self) -> Optional[Dict[str, Any]]: ...

    def set_credential(self, credential_dict: Dict[str, Any]) -> None: ...


CredentialSaver = Callable[[Dict[str, Any]], Awaitable[None]]
ClientSupplier = Callable[[], CredentialClient]
ManagedCredentialChecker = Callable[[], bool]


class CredentialLifecycle:
    """集中管理已保存扫码凭据的检查、刷新与持久化。"""

    def __init__(
        self,
        client_supplier: ClientSupplier,
        credential_saver: CredentialSaver,
        has_managed_credential: ManagedCredentialChecker,
    ) -> None:
        self._client_supplier = client_supplier
        self._credential_saver = credential_saver
        self._has_managed_credential = has_managed_credential
        self._refresh_lock = asyncio.Lock()

    async def refresh_if_required(self) -> CredentialRefreshResult:
        """按服务端指示至多刷新一次，并在成功后持久化新凭据。"""
        async with self._refresh_lock:
            if not self._has_managed_credential():
                return CredentialRefreshResult(CredentialRefreshStatus.NOT_MANAGED)

            client = self._client_supplier()
            credential = client.credential
            if credential is None:
                return CredentialRefreshResult(
                    CredentialRefreshStatus.RELOGIN_REQUIRED,
                    "credential_missing",
                )

            if not self._is_refreshable(credential):
                return CredentialRefreshResult(
                    CredentialRefreshStatus.RELOGIN_REQUIRED,
                    "refresh_fields_missing",
                )

            try:
                client._apply_proxy()
                refresh_required = await credential.check_refresh()
            except Exception as exc:
                return CredentialRefreshResult(
                    CredentialRefreshStatus.FAILED,
                    f"check_{type(exc).__name__}",
                )

            if not refresh_required:
                return CredentialRefreshResult(CredentialRefreshStatus.NOT_REQUIRED)

            old_credential = client.get_credential_dict()
            if not old_credential:
                return CredentialRefreshResult(
                    CredentialRefreshStatus.RELOGIN_REQUIRED,
                    "credential_serialization_failed",
                )

            try:
                await credential.refresh()
                refreshed_credential = client.get_credential_dict()
                if not refreshed_credential or not self._is_refreshable_dict(
                    refreshed_credential
                ):
                    raise ValueError("refreshed_credential_incomplete")
                await self._credential_saver(refreshed_credential)
            except Exception as exc:
                # 刷新会原地修改 Credential；持久化失败时恢复旧凭据，避免内存与磁盘不一致。
                try:
                    client.set_credential(old_credential)
                except Exception:
                    pass
                return CredentialRefreshResult(
                    CredentialRefreshStatus.FAILED,
                    f"refresh_{type(exc).__name__}",
                )

            return CredentialRefreshResult(CredentialRefreshStatus.REFRESHED)

    @staticmethod
    def _is_refreshable(credential: Any) -> bool:
        return all(
            str(getattr(credential, field, "") or "")
            for field in ("sessdata", "bili_jct", "dedeuserid", "ac_time_value")
        )

    @staticmethod
    def _is_refreshable_dict(credential: Dict[str, Any]) -> bool:
        return all(
            str(credential.get(field) or "")
            for field in ("sessdata", "bili_jct", "dedeuserid", "ac_time_value")
        )
