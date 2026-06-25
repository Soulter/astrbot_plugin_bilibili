import asyncio
import json
import os
import re
import tempfile
import time
from typing import List, Tuple

from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import *
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.event.filter import (
    EventMessageType,
    PermissionType,
    command,
    event_message_type,
    permission_type,
    regex,
)
from astrbot.api.message_components import Image, Plain
from astrbot.core.star.filter.command import GreedyStr
from bilibili_api import login_v2

from .bili_client import BiliClient
from .core.constant import (
    AT_ALL_OPTION,
    AT_SUB_OPTION,
    BV,
    CARD_TEMPLATES,
    DEFAULT_TEMPLATE,
    LIVE_ATALL_OPTION,
    LOGO_PATH,
    RECENT_DYNAMIC_CACHE,
    RECONNECT_SILENT_PADDING_SECS,
    RECONNECT_SILENT_THRESHOLD_SECS,
    UNAT_SUB_OPTION,
    VALID_FILTER_TYPES,
    VALID_SUB_OPTIONS,
    get_template_names,
)
from .core.data_manager import DataManager
from .core.models import RenderPayload, SubscriptionRecord
from .core.utils import create_qrcode, image_to_base64, is_valid_umo
from .services.dispatcher import SubscriptionNotificationDispatcher
from .services.listener import DynamicListener
from .services.renderer import Renderer
from .services.subscription_service import SubscriptionService
from .tools.bgm_daily import BgmDailyTool
from .tools.bgm_subject import BgmAdvancedSubjectSearchTool, BgmRecommendHotSubjectsTool
from .tools.bili_hot_video import BiliSearchHotVideosTool
from .tools.bili_user_dynamics import BiliUserDynamicsTool


@register("astrbot_plugin_bilibili", "Soulter", "", "", "")
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.cfg = config
        self.context = context

        self.rai = self.cfg.get("rai", True)
        self.enable_parse_miniapp = self.cfg.get("enable_parse_miniapp", True)
        self.enable_parse_BV = self.cfg.get("enable_parse_BV", True)
        self.proxy = (self.cfg.get("proxy", "") or "").strip()
        self.bangumi_token = (self.cfg.get("bangumi_token", "") or "").strip()
        # 读取样式配置
        self.style = self.cfg.get("renderer_template", DEFAULT_TEMPLATE)

        self.data_manager = DataManager(
            recent_dynamic_cache=self.cfg.get(
                "recent_dynamic_cache", RECENT_DYNAMIC_CACHE
            )
        )
        self.renderer = Renderer(self, self.rai, self.style)
        self._last_notify_write_ts = self.data_manager.get_last_success_sub_notify_ts()
        self.notification_dispatcher = SubscriptionNotificationDispatcher(
            context=self.context,
            on_sent=self._on_subscription_notification_sent,
        )

        # 优先使用 DataManager 中的凭据
        saved_credential = self.data_manager.get_credential()
        if saved_credential:
            self.bili_client = BiliClient(
                credential_dict=saved_credential, proxy=self.proxy
            )
        else:
            self.bili_client = BiliClient(
                sessdata=self.cfg.get("sessdata"), proxy=self.proxy
            )

        self.dynamic_listener = DynamicListener(
            context=self.context,
            data_manager=self.data_manager,
            bili_client=self.bili_client,
            renderer=self.renderer,
            dispatcher=self.notification_dispatcher,
            cfg=self.cfg,
        )
        self.subscription_service = SubscriptionService(
            data_manager=self.data_manager,
            bili_client=self.bili_client,
            parse_dynamics=self.dynamic_listener._parse_and_filter_dynamics,
        )
        llm_tools = (
            BgmAdvancedSubjectSearchTool(
                token=self.bangumi_token,
            ),
            BgmRecommendHotSubjectsTool(
                token=self.bangumi_token,
            ),
            BgmDailyTool(
                token=self.bangumi_token,
            ),
            BiliSearchHotVideosTool(
                bili_client=self.bili_client,
            ),
            BiliUserDynamicsTool(
                bili_client=self.bili_client,
                parse_dynamics=self.dynamic_listener._parse_and_filter_dynamics,
            ),
        )
        self.context.add_llm_tools(*llm_tools)
        self._configure_reconnect_silent()

        self._start_tasks()

    def _start_tasks(self):
        """启动或重启后台任务。"""
        if hasattr(self, "dynamic_listener_task") and self.dynamic_listener_task:
            self.dynamic_listener_task.cancel()

        self.dynamic_listener_task = asyncio.create_task(self.dynamic_listener.start())

    def _compute_reconnect_silent_duration(self) -> int:
        uid_count = len(self.dynamic_listener._build_uid_targets())
        interval_secs = max(float(self.cfg.get("interval_secs")), 0.0)
        task_gap_secs = max(float(self.cfg.get("task_gap_secs")), 0.0)
        duration = (
            interval_secs + task_gap_secs * uid_count + RECONNECT_SILENT_PADDING_SECS
        )
        return max(int(duration), 1)

    def _configure_reconnect_silent(self) -> None:
        if not bool(self.cfg.get("reconnect_silent", False)):
            self.notification_dispatcher.set_silent_until_ts(0)
            return

        last_success_ts = self.data_manager.get_last_success_sub_notify_ts()
        if last_success_ts <= 0:
            logger.info("重连静默未触发：缺少历史推送成功时间。")
            return

        now_ts = int(time.time())
        idle_secs = now_ts - last_success_ts
        if idle_secs <= RECONNECT_SILENT_THRESHOLD_SECS:
            logger.info(
                f"重连静默未触发：距上次成功推送仅 {idle_secs} 秒（阈值 {RECONNECT_SILENT_THRESHOLD_SECS} 秒）。"
            )
            return

        silent_duration = self._compute_reconnect_silent_duration()
        silent_until_ts = now_ts + silent_duration
        self.notification_dispatcher.set_silent_until_ts(silent_until_ts)
        logger.warning(
            f"检测到长时间未成功推送订阅通知（{idle_secs} 秒），进入静默模式 {silent_duration} 秒。"
        )

    async def _on_subscription_notification_sent(self, _notification: object) -> None:
        now_ts = int(time.time())
        if now_ts == self._last_notify_write_ts:
            return
        self._last_notify_write_ts = now_ts
        await self.data_manager.set_last_success_sub_notify_ts(now_ts)

    @staticmethod
    def _parse_sub_args(
        input_text: GreedyStr,
    ) -> tuple[List[str], List[str], bool, bool, bool, bool]:
        args = input_text.strip().split(" ") if input_text.strip() else []
        filter_types: List[str] = []
        filter_regex: List[str] = []
        live_atall = False
        at_all = False
        at_sub = False
        unat_sub = False

        for arg in args:
            if arg in VALID_SUB_OPTIONS:
                if arg == LIVE_ATALL_OPTION:
                    live_atall = True
                elif arg == AT_ALL_OPTION:
                    at_all = True
                elif arg == AT_SUB_OPTION:
                    at_sub = True
                elif arg == UNAT_SUB_OPTION:
                    unat_sub = True
                continue
            if arg in VALID_FILTER_TYPES:
                filter_types.append(arg)
            else:
                filter_regex.append(arg)

        return filter_types, filter_regex, live_atall, at_all, at_sub, unat_sub

    @staticmethod
    def _build_filter_desc(
        filter_types: List[str],
        filter_regex: List[str],
        live_atall: bool,
        at_all: bool = False,
        at_sub_users_len: int = 0,
    ) -> str:
        filter_desc = ""
        if filter_types:
            filter_desc += f"<br>过滤类型: {', '.join(filter_types)}"
        if filter_regex:
            filter_desc += f"<br>过滤正则: {filter_regex}"
        if live_atall:
            filter_desc += "<br>直播开播@全体: 开启"
        else:
            filter_desc += "<br>直播开播@全体: 关闭"
        if at_all:
            filter_desc += "<br>@全体成员: 开启"
        else:
            filter_desc += "<br>@全体成员: 关闭"
        filter_desc += f"<br>@特定订阅者人数: {at_sub_users_len}"
        return filter_desc

    @staticmethod
    def _build_subscription_payload(
        uid: int,
        name: str,
        sex: str,
        avatar: str,
        mid: int,
        filter_desc: str,
    ) -> RenderPayload:
        link = f"https://space.bilibili.com/{mid}"
        return RenderPayload(
            uid=str(uid),
            name="AstrBot",
            avatar=image_to_base64(LOGO_PATH),
            text=f"📣 订阅成功！<br>UP 主: {name} | 性别: {sex}{filter_desc}",
            image_urls=[avatar] if avatar else [],
            url=link,
            qrcode=create_qrcode(link),
        )

    async def _send_subscription_result(
        self, event: AstrMessageEvent, payload: RenderPayload, avatar: str
    ) -> MessageEventResult | None:
        text = "\n".join(filter(None, payload.text.split("<br>")))
        if self.rai:
            img_path = await self.renderer.render_dynamic(payload)
            if img_path:
                await event.send(
                    MessageChain().file_image(img_path).message(payload.url)
                )
                return None
            msg = "渲染图片失败了 (´;ω;`)"
            chain = MessageChain().message(msg).message(text)
            if avatar:
                chain = chain.url_image(avatar)
            await event.send(chain)
            return None
        chain = [Plain(text)]
        if avatar:
            chain.append(Image.fromURL(avatar))
        return MessageEventResult(chain=chain, use_t2i_=False)

    async def _apply_subscription(
        self,
        sub_user: str,
        uid_int: int,
        filter_types: List[str],
        filter_regex: List[str],
        live_atall: bool,
        at_all: bool | None = None,
        add_sub_users: List[str] | None = None,
        rm_sub_users: List[str] | None = None,
        inherit_filters: bool = False,
    ) -> Tuple[bool, str]:
        result = await self.subscription_service.add_or_update(
            sub_user,
            uid_int,
            filter_types,
            filter_regex,
            live_atall,
            at_all=at_all,
            add_sub_users=add_sub_users,
            rm_sub_users=rm_sub_users,
            inherit_filters=inherit_filters,
        )
        if result.updated:
            option_desc = "开启" if live_atall else "关闭"
            return True, f"该动态已订阅，已更新过滤条件。直播@全体: {option_desc}"
        return False, ""

    @command("bili_login")
    @permission_type(PermissionType.ADMIN)
    async def bili_login(self, event: AstrMessageEvent):
        """扫码登录 Bilibili。"""
        if event.get_group_id():
            return MessageEventResult().message(
                "仅支持管理员在私聊中使用'/bili_login'指令。"
            )

        login_obj = login_v2.QrCodeLogin()
        await login_obj.generate_qrcode()

        # 获取二维码图片路径
        qr_path = os.path.join(tempfile.gettempdir(), "qrcode.png")

        await event.send(
            MessageChain()
            .message("请使用 Bilibili App 扫描下方二维码登录：")
            .file_image(qr_path)
        )

        # 轮询状态
        try:
            while True:
                state = await login_obj.check_state()
                if state == login_v2.QrCodeLoginEvents.DONE:
                    credential = login_obj.get_credential()
                    # 保存凭据
                    self.bili_client.credential = credential
                    cred_dict = self.bili_client.get_credential_dict()
                    if cred_dict is not None:
                        await self.data_manager.set_credential(cred_dict)
                        self._start_tasks()
                        await event.send(MessageChain().message("✅ 登录成功！"))
                    else:
                        await event.send(
                            MessageChain().message("❌ 登录失败：无法获取凭据。")
                        )
                    break
                elif state == login_v2.QrCodeLoginEvents.TIMEOUT:
                    await event.send(
                        MessageChain().message("❌ 登录超时，请重新执行 /bili_login。")
                    )
                    break

                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"登录过程中发生错误: {e}")
            await event.send(MessageChain().message(f"❌ 登录失败: {str(e)}"))

    @command("bili_logout")
    @permission_type(PermissionType.ADMIN)
    async def bili_logout(self, event: AstrMessageEvent):
        """登出 Bilibili，清除凭据。"""
        self.bili_client.credential = None
        await self.data_manager.clear_credential()
        self.bili_client = BiliClient(
            sessdata=self.cfg.get("sessdata"), proxy=self.proxy
        )
        self.dynamic_listener.bili_client = self.bili_client
        self._start_tasks()
        return MessageEventResult().message("✅ 已登出 Bilibili，凭据已清除。")

    @command("bili_card_style", alias={"卡片样式"})
    @permission_type(PermissionType.ADMIN)
    async def switch_style(self, event: AstrMessageEvent, style: str | None = None):
        """切换动态卡片样式。不带参数可以查看可用的卡片样式列表。"""
        available = get_template_names()

        # 不带参数：显示可用样式列表
        if not style:
            lines = ["📋 可用的卡片样式："]
            for tid in available:
                info = CARD_TEMPLATES[tid]
                current = " ← 当前" if tid == self.style else ""
                lines.append(f"  • {tid}: {info['name']}{current}")
                lines.append(f"    {info['description']}")
            lines.append("\n使用 /卡片样式 <样式名> 切换")
            return MessageEventResult().message("\n".join(lines))

        # 带参数：切换样式
        if style not in available:
            return MessageEventResult().message(
                f"样式 '{style}' 不存在。可用样式：{', '.join(available)}"
            )

        self.style = style
        self.renderer.style = style

        info = CARD_TEMPLATES[style]
        self.cfg["renderer_template"] = style
        self.cfg.save_config()
        return MessageEventResult().message(
            f"✅ 已切换样式为：{info['name']} ({style})"
        )

    @regex(BV)
    async def get_video_info(self, event: AstrMessageEvent):
        if self.enable_parse_BV:
            match_ = re.search(BV, event.message_str, re.IGNORECASE)
            if not match_:
                return
            # 匹配到短链接
            if match_.group(2):
                full_link = match_.group(0)
                converted_url = await self.bili_client.b23_to_bv(full_link)
                if not converted_url:
                    return
                match_bv = re.search(r"(BV[a-zA-Z0-9]+)", converted_url, re.IGNORECASE)
                if match_bv:
                    bvid = match_bv.group(1)
                else:
                    return
            # 匹配到长链接
            elif match_.group(1):
                bvid = match_.group(1)
            # 匹配到纯 BV 号
            elif match_.group(0):
                bvid = match_.group(0)

            video_data = await self.bili_client.get_video_info(bvid=bvid)
            if not video_data:
                return await event.send(
                    MessageChain().message("获取视频信息失败了 (´;ω;`)")
                )
            info = video_data["info"]
            online = video_data["online"]

            payload = RenderPayload(
                name="AstrBot",
                avatar=image_to_base64(LOGO_PATH),
                title=info["title"],
                text=(
                    f"UP 主: {info['owner']['name']}<br>"
                    f"播放量: {info['stat']['view']}<br>"
                    f"点赞: {info['stat']['like']}<br>"
                    f"投币: {info['stat']['coin']}<br>"
                    f"总共 {online['total']} 人正在观看"
                ),
                image_urls=[info["pic"]],
            )

            img_path = await self.renderer.render_dynamic(payload)
            if img_path:
                await event.send(MessageChain().file_image(img_path))
            else:
                msg = "渲染图片失败了 (´;ω;`)"
                text = "\n".join(filter(None, payload.text.split("<br>")))
                await event.send(
                    MessageChain().message(msg).message(text).url_image(info["pic"])
                )

    @command("bili_sub", alias={"订阅动态"})
    async def dynamic_sub(self, event: AstrMessageEvent, uid: str, input: GreedyStr):
        filter_types, filter_regex, live_atall, at_all, at_sub, unat_sub = (
            self._parse_sub_args(input)
        )

        if (at_all or live_atall) and not event.is_admin():
            if event.role not in ("admin", "owner", "founder"):
                return MessageEventResult().message(
                    "权限不足：只有管理员可以设置 @全体成员 相关选项。"
                )

        sub_user = event.unified_msg_origin
        if not uid.isdigit():
            return MessageEventResult().message("UID 格式错误")
        uid_int = int(uid)

        inherit_filters = False
        if not filter_types and not filter_regex and (at_all or at_sub or unat_sub):
            inherit_filters = True

        add_sub_users = [event.get_sender_id()] if at_sub else None
        rm_sub_users = [event.get_sender_id()] if unat_sub else None

        warning = ""
        if (at_all or live_atall) and getattr(event, "get_group_id", lambda: None)():
            permit_atall = await self.dynamic_listener._check_atall_permission(
                sub_user, True
            )
            if not permit_atall:
                warning = "\n⚠️ 注意：机器人目前在本会话无 @全体成员 的权限，此项设置可能不会生效（请给予机器人管理员权限）。"

        updated, update_msg = await self._apply_subscription(
            sub_user,
            uid_int,
            filter_types,
            filter_regex,
            live_atall,
            at_all=at_all if at_all else None,
            add_sub_users=add_sub_users,
            rm_sub_users=rm_sub_users,
            inherit_filters=inherit_filters,
        )
        if updated:
            if warning:
                update_msg += warning
            return MessageEventResult().message(update_msg)

        try:
            usr_info, msg = await self.bili_client.get_user_info(int(uid))
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return MessageEventResult().message("订阅成功，但获取 UP 主信息失败。")
        if not usr_info:
            return MessageEventResult().message(
                f"订阅成功，但获取 UP 主信息失败: {msg}"
            )

        filter_desc = self._build_filter_desc(
            filter_types,
            filter_regex,
            live_atall,
            at_all=at_all,
            at_sub_users_len=len(add_sub_users or []),
        )
        if warning:
            filter_desc += warning.replace("\n", "<br>")

        payload = self._build_subscription_payload(
            uid_int,
            str(usr_info.get("name", "Unknown")),
            str(usr_info.get("sex", "保密")),
            str(usr_info.get("face", "")),
            int(usr_info.get("mid", uid_int)),
            filter_desc,
        )
        return await self._send_subscription_result(
            event, payload, str(usr_info.get("face", ""))
        )

    @command("bili_sub_list", alias={"订阅列表"})
    async def sub_list(self, event: AstrMessageEvent):
        """查看 bilibili 动态监控列表"""
        sub_user = event.unified_msg_origin
        ret = """订阅列表：\n"""
        subs = self.data_manager.get_subscriptions_by_user(sub_user)

        if not subs:
            return MessageEventResult().message("无订阅")
        else:
            for idx, uid_sub_data in enumerate(subs):
                uid = uid_sub_data.uid
                info, _ = await self.bili_client.get_user_info(int(uid))
                if not info:
                    ret += f"{idx + 1}. {uid} - 无法获取 UP 主信息\n"
                else:
                    name = info["name"]
                    ret += f"{idx + 1}. {uid} - {name}\n"
                filters = []
                if uid_sub_data.filter_types:
                    filters.append(f"过滤类型: {', '.join(uid_sub_data.filter_types)}")
                if uid_sub_data.filter_regex:
                    filters.append(f"过滤正则: {uid_sub_data.filter_regex}")
                if uid_sub_data.live_atall:
                    filters.append("直播@全体: 开启")
                else:
                    filters.append("直播@全体: 关闭")
                if uid_sub_data.at_all:
                    filters.append("@全体成员: 开启")
                else:
                    filters.append("@全体成员: 关闭")
                if uid_sub_data.at_sub_users:
                    filters.append(f"@订阅者: [{', '.join(uid_sub_data.at_sub_users)}]")
                if filters:
                    ret += f"   {'｜'.join(filters)}\n"
            return MessageEventResult().message(ret)

    @command("bili_sub_del", alias={"订阅删除"})
    async def sub_del(self, event: AstrMessageEvent, uid: str):
        """删除 bilibili 动态监控"""
        sub_user = event.unified_msg_origin
        if not uid or not uid.isdigit():
            return MessageEventResult().message("参数错误，请提供正确的UID。")

        uid2del = int(uid)

        if await self.data_manager.remove_subscription(sub_user, uid2del):
            return MessageEventResult().message("删除成功")
        else:
            return MessageEventResult().message("未找到指定的订阅")

    @permission_type(PermissionType.ADMIN)
    @command("bili_global_del", alias={"全局删除"})
    async def global_sub_del(self, event: AstrMessageEvent, umo: str = ""):
        """管理员指令。通过 UMO 删除某一个群聊或者私聊的所有订阅。"""
        if not is_valid_umo(umo):
            return MessageEventResult().message(
                "通过 UMO 删除某一个群聊或者私聊的所有订阅。使用 /sid 指令查看当前会话的 UMO 或参考 WebUI-自定义规则。"
            )

        msg = await self.data_manager.remove_all_for_user(umo)
        return MessageEventResult().message(msg)

    @permission_type(PermissionType.ADMIN)
    @command("bili_global_sub", alias={"全局订阅"})
    async def global_sub_add(
        self, event: AstrMessageEvent, umo: str, uid: str, input: GreedyStr
    ):
        """管理员指令。通过 UID 添加某一个用户的所有订阅。"""
        if not is_valid_umo(umo) or not uid.isdigit():
            return MessageEventResult().message(
                "请提供正确的UMO与UID。使用 /sid 指令查看当前会话的 UMO 或参考 WebUI-自定义规则。"
            )
        filter_types, filter_regex, live_atall, at_all, at_sub, unat_sub = (
            self._parse_sub_args(input)
        )
        uid_int = int(uid)

        inherit_filters = False
        if not filter_types and not filter_regex and (at_all or at_sub or unat_sub):
            inherit_filters = True

        warning = ""
        if at_all or live_atall:
            permit_atall = await self.dynamic_listener._check_atall_permission(
                umo, True
            )
            if not permit_atall:
                warning = "\n⚠️ 注意：机器人目前在目标会话无 @全体成员 的权限，此项设置可能不会生效（请检查机器人权限）。"

        updated, update_msg = await self._apply_subscription(
            umo,
            uid_int,
            filter_types,
            filter_regex,
            live_atall,
            at_all=True if at_all else None,
            add_sub_users=None,
            rm_sub_users=None,
            inherit_filters=inherit_filters,
        )
        if updated:
            if warning:
                update_msg += warning
            return MessageEventResult().message(update_msg)
        return MessageEventResult().message(
            f"订阅完成，已为{umo}添加订阅{uid_int}，详情见日志。{warning}"
        )

    @permission_type(PermissionType.ADMIN)
    @command("bili_global_list", alias={"全局列表"})
    async def global_list(self, event: AstrMessageEvent):
        """管理员指令。查看所有订阅者"""
        ret = "订阅会话列表：\n"
        all_subs = self.data_manager.get_all_subscriptions()
        if not all_subs:
            return MessageEventResult().message("没有任何会话订阅过。")

        for sub_user in all_subs:
            ret += f"- {sub_user}\n"
            for sub in all_subs[sub_user]:
                uid = sub.uid
                ret += f"  - {uid}\n"
        return MessageEventResult().message(ret)

    @event_message_type(EventMessageType.ALL)
    async def parse_miniapp(self, event: AstrMessageEvent):
        if self.enable_parse_miniapp:
            for msg_element in event.message_obj.message:
                if (
                    hasattr(msg_element, "type")
                    and msg_element.type == "Json"
                    and hasattr(msg_element, "data")
                ):
                    json_string = msg_element.data

                    try:
                        if isinstance(json_string, dict):
                            parsed_data = json_string
                        else:
                            parsed_data = json.loads(json_string)
                        meta = parsed_data.get("meta", {})
                        detail_1 = meta.get("detail_1", {})
                        title = detail_1.get("title")
                        qqdocurl = detail_1.get("qqdocurl")
                        desc = detail_1.get("desc")

                        if title == "哔哩哔哩" and qqdocurl:
                            if "https://b23.tv" in qqdocurl:
                                qqdocurl = await self.bili_client.b23_to_bv(qqdocurl)
                            ret = f"标题: {desc}\n链接: {qqdocurl}"
                            await event.send(MessageChain().message(ret))
                        news = meta.get("news", {})
                        tag = news.get("tag", "")
                        jumpurl = news.get("jumpUrl", "")
                        title = news.get("title", "")
                        if tag == "哔哩哔哩" and jumpurl:
                            if "https://b23.tv" in jumpurl:
                                jumpurl = await self.bili_client.b23_to_bv(jumpurl)
                            ret = f"标题: {title}\n链接: {jumpurl}"
                            await event.send(MessageChain().message(ret))
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode JSON string: {json_string}")
                    except Exception as e:
                        logger.error(f"An error occurred during JSON processing: {e}")

    @command("bili_sub_test", alias={"订阅测试"})
    async def sub_test(self, event: AstrMessageEvent, uid: str):
        """测试订阅功能。仅测试获取动态与渲染图片功能，不保存订阅信息。"""
        sub_user = event.unified_msg_origin
        try:
            uid_int = int(uid)
        except (TypeError, ValueError):
            return MessageEventResult().message("UID 必须是数字。")

        dyn = await self.bili_client.get_latest_dynamics(uid_int)
        if not dyn:
            return MessageEventResult().message("未获取到动态数据，请稍后重试。")

        sub_data = self.data_manager.get_subscription(sub_user, uid_int)
        if not sub_data:
            sub_data = SubscriptionRecord(uid=uid_int)

        result_list = self.dynamic_listener._parse_and_filter_dynamics(
            dyn,
            sub_data,
        )

        render_data: RenderPayload | None = None
        # dyn_id = None
        for result in result_list or []:
            if result.has_payload():
                render_data = result.payload
                # dyn_id = result.dyn_id
                break

        if not render_data:
            return MessageEventResult().message(
                "没有可用于测试推送的动态（可能没有新动态、都被过滤掉，或动态类型暂不支持）。"
            )

        # 测试命令需要每次基于当前代码重新构造消息，避免命中同 dyn_id 的历史缓存。
        await self.dynamic_listener._handle_new_dynamic(
            sub_user, render_data, None, sub_data=sub_data
        )
        event.stop_event()

    async def terminate(self):
        if (
            hasattr(self, "dynamic_listener_task")
            and self.dynamic_listener_task
            and not self.dynamic_listener_task.done()
        ):
            self.dynamic_listener_task.cancel()
            try:
                await self.dynamic_listener_task
            except asyncio.CancelledError:
                logger.info(
                    "bilibili dynamic_listener task was successfully cancelled during terminate."
                )
            except Exception as e:
                logger.error(
                    f"Error awaiting cancellation of dynamic_listener task: {e}"
                )
