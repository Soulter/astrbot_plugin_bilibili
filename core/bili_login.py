from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import qrcode
from curl_cffi import requests


QR_GENERATE_URL = (
    "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
)
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_LOGIN_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Referer": "https://www.bilibili.com/",
}
_REQUIRED_CREDENTIAL_KEYS = ("sessdata", "bili_jct", "dedeuserid")
_CROSS_DOMAIN_HOSTS = {"passport.biligame.com", "passport.bilibili.com"}


class BiliLoginError(Exception):
    """Bilibili 扫码登录失败。"""


@dataclass(frozen=True)
class QrCodeInfo:
    url: str
    qrcode_key: str
    image_path: str


@dataclass(frozen=True)
class LoginPollResult:
    login_state_code: int
    message: str
    credential: dict[str, Any] | None = None

    @property
    def is_done(self) -> bool:
        return self.login_state_code == 0 and self.credential is not None

    @property
    def is_timeout(self) -> bool:
        return self.login_state_code == 86038


def is_cross_domain_login_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in _CROSS_DOMAIN_HOSTS
        and parsed.path.endswith("/crossDomain")
        and bool(parse_qs(parsed.query).get("ticket"))
    )


def extract_credential_from_url(url: str) -> dict[str, Any]:
    query = parse_qs(urlparse(url).query)
    return build_credential(
        {
            "SESSDATA": _first_query_value(query, "SESSDATA"),
            "bili_jct": _first_query_value(query, "bili_jct"),
            "buvid3": _first_query_value(query, "buvid3"),
            "buvid4": _first_query_value(query, "buvid4"),
            "DedeUserID": _first_query_value(query, "DedeUserID"),
        }
    )


def extract_credential_from_cookies(
    set_cookie_headers: Iterable[str], refresh_token: str = ""
) -> dict[str, Any]:
    cookies = parse_set_cookie_headers(set_cookie_headers)
    return build_credential(cookies, refresh_token)


def parse_set_cookie_headers(set_cookie_headers: Iterable[str]) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for header in set_cookie_headers:
        parsed = SimpleCookie()
        parsed.load(header)
        cookies.update({key: morsel.value for key, morsel in parsed.items()})
    return cookies


def build_credential(cookies: dict[str, str], refresh_token: str = "") -> dict[str, Any]:
    return {
        "sessdata": cookies.get("SESSDATA", ""),
        "bili_jct": cookies.get("bili_jct", ""),
        "buvid3": cookies.get("buvid3"),
        "buvid4": cookies.get("buvid4"),
        "dedeuserid": cookies.get("DedeUserID", ""),
        "ac_time_value": refresh_token,
    }


def credential_has_required_cookies(credential: dict[str, Any] | None) -> bool:
    if not credential:
        return False
    return all(str(credential.get(key) or "") for key in _REQUIRED_CREDENTIAL_KEYS)


def _first_query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values:
        return ""
    return values[0]


def _create_qrcode_image(url: str) -> str:
    path = os.path.join(tempfile.gettempdir(), "qrcode.png")
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#fb7299", back_color="white")
    image.save(path)
    return path


def _get_set_cookie_headers(response: requests.Response) -> list[str]:
    return response.headers.get_list("Set-Cookie")


class BiliQrLoginClient:
    def __init__(self, proxy: str | None = None, timeout_secs: int = 10) -> None:
        self.proxy = (proxy or "").strip() or None
        self.timeout_secs = timeout_secs
        self.qrcode_key = ""

    async def generate_qrcode(self) -> QrCodeInfo:
        async with self._create_session() as session:
            response = await session.get(QR_GENERATE_URL)
            payload = response.json()

        if payload.get("code") != 0:
            raise BiliLoginError(payload.get("message") or "生成二维码失败")

        data = payload.get("data") or {}
        url = str(data.get("url") or "")
        qrcode_key = str(data.get("qrcode_key") or "")
        if not url or not qrcode_key:
            raise BiliLoginError("生成二维码失败：响应缺少 url 或 qrcode_key。")

        self.qrcode_key = qrcode_key
        return QrCodeInfo(
            url=url,
            qrcode_key=qrcode_key,
            image_path=_create_qrcode_image(url),
        )

    async def poll(self) -> LoginPollResult:
        if not self.qrcode_key:
            raise BiliLoginError("尚未生成二维码。")

        async with self._create_session() as session:
            response = await session.get(
                QR_POLL_URL,
                params={"qrcode_key": self.qrcode_key},
            )
            payload = response.json()

            if payload.get("code") != 0:
                raise BiliLoginError(payload.get("message") or "轮询登录状态失败")

            data = payload.get("data") or {}
            poll_code = int(data.get("code", -1))
            message = str(data.get("message") or "")
            if poll_code != 0:
                return LoginPollResult(login_state_code=poll_code, message=message)

            credential = await self._extract_success_credential(session, data)
            if not credential_has_required_cookies(credential):
                raise BiliLoginError(
                    "扫码已确认，但未能获取完整凭据（缺少 SESSDATA/bili_jct/DedeUserID）。"
                )
            return LoginPollResult(
                login_state_code=0, message=message, credential=credential
            )

    def _create_session(self) -> requests.AsyncSession:
        return requests.AsyncSession(
            headers=_LOGIN_HEADERS,
            proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None,
            impersonate="chrome",
            timeout=self.timeout_secs,
        )

    async def _extract_success_credential(
        self, session: requests.AsyncSession, data: dict[str, Any]
    ) -> dict[str, Any]:
        login_url = str(data.get("url") or "")
        refresh_token = str(data.get("refresh_token") or "")

        if is_cross_domain_login_url(login_url):
            return await self._credential_from_cross_domain_url(
                session, login_url, refresh_token
            )

        credential = extract_credential_from_url(login_url)
        credential["ac_time_value"] = refresh_token
        return credential

    async def _credential_from_cross_domain_url(
        self,
        session: requests.AsyncSession,
        url: str,
        refresh_token: str,
    ) -> dict[str, Any]:
        response = await session.get(url, allow_redirects=True)
        cookie_headers = _get_set_cookie_headers(response)
        cookies = parse_set_cookie_headers(cookie_headers)
        cookies.update(session.cookies.get_dict())
        return build_credential(cookies, refresh_token)
