from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import aiohttp
from astrbot.api import logger
from bilibili_api import Credential, hot, request_settings, search, user, video
from bilibili_api.utils.network import Api


class BiliClient:
    """
    负责所有与 Bilibili API 的交互。
    """

    def __init__(
        self,
        sessdata: Optional[str] = None,
        credential_dict: Optional[Dict[str, Any]] = None,
        proxy: Optional[str] = None,
    ) -> None:
        """
        初始化 Bilibili API 客户端。
        """
        self.proxy = (proxy or "").strip()
        self._apply_proxy()
        self.credential = None
        if credential_dict:
            self.credential = self._build_credential(credential_dict)
        elif sessdata:
            self.credential = self._build_credential({"sessdata": sessdata})
        else:
            logger.warning("未提供 SESSDATA 或 凭据，部分需要登录的API可能无法使用。")

    def _apply_proxy(self) -> None:
        """
        根据当前配置应用全局请求代理。
        """
        try:
            request_settings.set_proxy(self.proxy)
        except Exception as e:
            logger.warning(f"设置 Bilibili 请求代理失败: {e}")

    def _build_credential(self, credential_data: Dict[str, Any]) -> Credential:
        """
        构建 Credential，优先尝试携带 proxy 参数，失败时自动回退。
        """
        payload = dict(credential_data)
        if self.proxy:
            payload.setdefault("proxy", self.proxy)
        try:
            return Credential(**payload)
        except TypeError:
            payload.pop("proxy", None)
            return Credential(**payload)

    def set_credential(self, credential_dict: Dict[str, Any]) -> None:
        """
        设置凭据。
        """
        self.credential = self._build_credential(credential_dict)

    def get_credential_dict(self) -> Optional[Dict[str, Any]]:
        """
        获取当前凭据的字典形式。
        """
        if not self.credential:
            return None
        return {
            "sessdata": self.credential.sessdata,
            "bili_jct": self.credential.bili_jct,
            "buvid3": self.credential.buvid3,
            "buvid4": self.credential.buvid4,
            "dedeuserid": self.credential.dedeuserid,
            "ac_time_value": self.credential.ac_time_value,
        }

    async def logout(self) -> bool:
        """
        调用 Bilibili 退出登录接口 (login/exit/v2)，在服务端注销 SESSDATA。
        仅清除本地保存的凭据无法使服务端的登录态失效，需调用此接口才能彻底登出。

        Returns:
            bool: 服务端注销是否成功。
        """
        if not self.credential:
            return False
        self._apply_proxy()
        try:
            self.credential.raise_for_no_bili_jct()
            resp = await Api(
                url="https://api.bilibili.com/login/exit/v2",
                method="POST",
                no_csrf=True,
                data={"biliCSRF": self.credential.bili_jct},
                credential=self.credential,
                ignore_code=True,
            ).result
            # 成功时 data 为 {"redirectUrl": ...}；账号未登录 (code -101) 时 data 为 None
            return isinstance(resp, dict) and "redirectUrl" in resp
        except Exception as e:
            logger.error(f"调用退出登录接口失败: {e}")
            return False

    async def check_credential(self) -> bool:
        """
        检查凭据是否有效。
        DEPRECATED: 该方法已废弃。
        """
        if not self.credential:
            return False
        return await self.credential.check_valid()

    async def refresh_credential(self) -> bool:
        """
        刷新凭据。
        DEPRECATED: 该方法已废弃。
        """
        if not self.credential:
            return False
        try:
            if await self.credential.check_refresh():
                await self.credential.refresh()
                return True
        except Exception as e:
            logger.error(f"刷新凭据失败: {e}")
        return False

    def start_refresh(
        self,
        on_refreshed: Optional[
            Callable[[Dict[str, Any] | None], Awaitable[None]]
        ] = None,
    ):
        """
        定时刷新凭据的循环。
        DEPRECATED: 该方法已废弃。
        :param on_refreshed: 兼容保留。过去用于刷新成功后的异步回调。
        """
        logger.warning(
            "start_refresh() 已废弃：为避免触发上游异常，已禁用定时刷新凭据任务。"
        )
        return

    def get_user(self, uid: int) -> user.User:
        """
        根据UID获取一个 User 对象。
        """
        return user.User(uid=uid, credential=self.credential)

    @staticmethod
    def _resolve_video_order(
        order: str,
    ) -> search.OrderVideo:
        mapping = {
            "totalrank": search.OrderVideo.TOTALRANK,
            "click": search.OrderVideo.CLICK,
            "pubdate": search.OrderVideo.PUBDATE,
            "dm": search.OrderVideo.DM,
            "stow": search.OrderVideo.STOW,
            "scores": search.OrderVideo.SCORES,
        }
        return mapping.get(order.lower(), search.OrderVideo.TOTALRANK)

    async def get_video_info(self, bvid: str) -> Optional[Dict[str, Any]]:
        """
        获取视频的详细信息和在线观看人数。
        """
        try:
            v = video.Video(bvid=bvid)
            info = await v.get_info()
            online = await v.get_online()
            return {"info": info, "online": online}
        except Exception as e:
            logger.error(f"获取视频信息失败 (BVID: {bvid}): {e}")
            return None

    async def get_hot_videos(
        self, pn: int = 1, ps: int = 20
    ) -> Optional[Dict[str, Any]]:
        """
        获取全站热门视频列表。
        """
        try:
            self._apply_proxy()
            return await hot.get_hot_videos(pn=pn, ps=ps)
        except Exception as e:
            logger.error(f"获取热门视频失败 (pn={pn}, ps={ps}): {e}")
            return None

    async def search_videos(
        self,
        keyword: str,
        *,
        order: str = "totalrank",
        page: int = 1,
        page_size: int = 20,
        video_zone_type: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        按关键词搜索视频，并按指定排序返回结果。
        """
        try:
            self._apply_proxy()
            order_type = self._resolve_video_order(order)
            return await search.search_by_type(
                keyword=keyword,
                search_type=search.SearchObjectType.VIDEO,
                order_type=order_type,
                page=page,
                page_size=page_size,
                video_zone_type=video_zone_type,
            )
        except Exception as e:
            logger.error(f"搜索视频失败 (keyword={keyword}, order={order}): {e}")
            return None

    async def get_latest_dynamics(self, uid: int) -> Optional[Dict[str, Any]]:
        """
        获取用户的最新动态。
        """
        try:
            self._apply_proxy()
            u: user.User = self.get_user(uid)
            return await u.get_dynamics_new()
        except Exception as e:
            logger.error(f"获取用户动态失败 (UID: {uid}): {e}")
            return None

    async def get_live_info(self, uid: int) -> Optional[Dict[str, Any]]:
        """
        获取用户的直播间信息。
        DEPRECATED: 该方法已弃用，据反馈易引起412错误
        """
        try:
            u: user.User = self.get_user(uid)
            # 上游接口同u.get_user_info，即"https://api.bilibili.com/x/space/wbi/acc/info"，412的诱因
            return await u.get_live_info()
        except Exception as e:
            logger.error(f"获取直播间信息失败 (UID: {uid}): {e}")
            return None

    async def get_live_info_by_uids(self, uids: list[int]) -> Optional[Dict[str, Any]]:
        self._apply_proxy()
        API_CONFIG = {
            "url": "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids",
            "method": "GET",
            "verify": False,
            "params": {"uids[]": "list<int>: 主播uid列表"},
            "comment": "通过主播uid列表获取直播间状态信息（是否在直播、房间号等）",
        }
        params: Dict[str, list[int]] = {"uids[]": uids}
        resp = await Api(**API_CONFIG, no_csrf=True).update_params(**params).result
        if not isinstance(resp, dict) or not resp:
            return None
        live_room = next(iter(resp.values()))
        return live_room

    async def get_user_info(self, uid: int) -> Tuple[Dict[str, Any] | None, str]:
        """
        获取用户的基本信息。
        """
        try:
            u: user.User = self.get_user(uid)
            info = await u.get_user_info()
            return info, ""
        except Exception as e:
            if "code" in e.args[0] and e.args[0]["code"] == -404:
                logger.warning(f"无法找到用户 (UID: {uid})")
                return None, "啥都木有 (´;ω;`)"
            else:
                logger.error(f"获取用户信息失败 (UID: {uid}): {e}")
                return None, f"获取 UP 主信息失败: {str(e)}"

    async def b23_to_bv(self, url: str) -> Optional[str]:
        """
        b23短链转换为原始链接
        """
        headers: Dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url=url, headers=headers, allow_redirects=False, timeout=10
                ) as response:
                    if 300 <= response.status < 400:
                        location_url: str | None = response.headers.get("Location")
                        if location_url:
                            base_url: str = location_url.split("?", 1)[0]
                            return base_url
            except Exception as e:
                logger.error(f"解析b23链接失败 (URL: {url}): {e}")
                return url
