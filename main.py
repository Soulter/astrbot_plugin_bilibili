from util.plugin_dev.api.v1.bot import Context, AstrMessageEvent, CommandResult
from util.plugin_dev.api.v1.config import *
from util.plugin_dev.api.v1.types import *
from aiocqhttp.event import Event
from bilibili_api import user, Credential, settings, video
from .dynamics import parse_last_dynamic
import asyncio
import logging
import re

DEFAULT_CFG = {
    "bili_sub_list": {} # sub_user -> [{"uid": "uid", "last": "last_dynamic_id"}]
}
DATA_PATH = "data/astrbot_plugin_bilibili.json"
BV_PATTERN = r"(?:\?.*)?(?:https?:\/\/)?(?:www\.)?bilibili\.com\/video\/(BV[\w\d]+)\/?(?:\?.*)?"
settings.timeout = 15

logger = logging.getLogger("astrbot")

class Main:
    def __init__(self, context: Context) -> None:
        # 仅支持 aiocqhttp
        NAMESPACE = "astrbot_plugin_bilibili"        
        self.context = context
        self.context.register_commands(NAMESPACE, BV_PATTERN, "解析 bilibili 视频BV号", 1, self.get_video_info, use_regex=True, ignore_prefix=True)

        self.context.register_commands(NAMESPACE, "订阅动态", "添加 bilibili 动态监控", 2, self.dynamic_sub)
        self.context.register_commands(NAMESPACE, "订阅列表", "查看 bilibili 动态监控列表", 1, self.dynamic_sub)
        self.context.register_commands(NAMESPACE, "订阅删除", "删除 bilibili 动态监控", 2, self.dynamic_sub)
        
        put_config(NAMESPACE, "sessdata", "sessdata", "", "bilibili sessdata")
        self.cfg = load_config(NAMESPACE)
        self.credential = None
        if not self.cfg["sessdata"]:
            logger.error("请设置 bilibili sessdata")
        else:
            self.credential = Credential(self.cfg["sessdata"])
        self.context = context
        
        if not os.path.exists(DATA_PATH):
            with open(DATA_PATH, "w", encoding="utf-8-sig") as f:
                f.write(json.dumps(DEFAULT_CFG, ensure_ascii=False, indent=4))
        with open(DATA_PATH, "r", encoding="utf-8-sig") as f:
            self.data = json.load(f)
        
        # thread = threading.Thread(target=self.dynamic_listener).start()
        self.context.register_task(self.dynamic_listener(), "bilibili动态监听")
        
    def check_platform(self, message: AstrMessageEvent):
        if message.platform.platform_name in ['aiocqhttp', 'nakuru']:
            return True
        else:
            logger.warn(f"不支持的平台 {message.platform.platform_name}")
            return False
        
    async def get_video_info(self, message: AstrMessageEvent, context: Context):
        if not self.check_platform(message): return
        BV_PATTERN = r"(?:\?.*)?(?:https?:\/\/)?(?:www\.)?bilibili\.com\/video\/(BV[\w\d]+)\/?(?:\?.*)?"
        match_ = re.search(BV_PATTERN, message.message_str, re.IGNORECASE)
        if not match_:
            return
        bvid = 'BV' + match_.group(1)[2:]
        v = video.Video(bvid=bvid)
        info = await v.get_info()
        online = await v.get_online()
        ret = f"""Billibili 视频信息：
标题: {info['title']}
UP主: {info['owner']['name']}
播放量: {info['stat']['view']}
点赞: {info['stat']['like']}
投币: {info['stat']['coin']}
总共 {online['total']} 人正在观看"""
        ls = [Plain(ret), Image.fromURL(info['pic'])]
        
        return CommandResult(message_chain=ls, use_t2i=False)
    
    async def save_cfg(self):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.data, ensure_ascii=False, indent=2))
    
    async def dynamic_sub(self, message: AstrMessageEvent, context: Context):
        if not self.check_platform(message): return
        if not isinstance(message.message_obj.raw_message, Event): return # 非 aiocqhttp
        
        l = message.message_str.split(" ")
        sub_user = message.unified_msg_origin
        if l[0] == "订阅动态" and l[1].isdigit():
            if sub_user:
                if sub_user in self.data["bili_sub_list"]:
                    self.data["bili_sub_list"][sub_user].append({
                        "uid": int(l[1]),
                        "last": ""
                    })
                else:
                    self.data["bili_sub_list"][sub_user] = [{
                        "uid": int(l[1]),
                        "last": ""
                    }]
                await self.save_cfg()
                return CommandResult().message("添加成功")
            else:
                return
        elif l[0] == "订阅列表":
            ret = """订阅列表：\n"""
            if sub_user in self.data["bili_sub_list"]:
                for idx, uid_sub_data in enumerate(self.data["bili_sub_list"][sub_user]):
                    ret += f"{idx+1}. {uid_sub_data['uid']}\n"
                return CommandResult().message(ret)
            else:
                return CommandResult().message("无订阅")
        elif l[0] == "订阅删除":
            if sub_user in self.data["bili_sub_list"]:
                uid = int(l[1])
                for idx, uid_sub_data in enumerate(self.data["bili_sub_list"][sub_user]):
                    if uid_sub_data['uid'] == uid:
                        del self.data["bili_sub_list"][sub_user][idx]
                        await self.save_cfg()
                        return CommandResult().message("删除成功")
            else:
                return CommandResult().message("不存在")
        else:
            return CommandResult().message("参数错误")
        
    async def dynamic_listener(self):
        while True:
            await asyncio.sleep(20*10)
            if self.credential is None:
                logger.warn("bilibili sessdata 未设置，无法获取动态")
                continue
            for sub_usr in self.data["bili_sub_list"]:
                for idx, uid_sub_data in enumerate(self.data["bili_sub_list"][sub_usr]):
                    try:
                        usr = user.User(uid_sub_data['uid'], credential=self.credential)
                        dyn = await usr.get_dynamics_new()
                        # dyn = asyncio.run_coroutine_threadsafe(usr.get_dynamics_new(), asyncio.get_event_loop()).result()
                        if dyn:
                            ret, dyn_id = await parse_last_dynamic(dyn, uid_sub_data)
                            # ret = asyncio.run_coroutine_threadsafe(parse_last_dynamic(dyn, uid_sub_data), asyncio.get_event_loop()).result()
                            if not ret:
                                continue
                            await self.context.send_message(sub_usr, ret)
                            # asyncio.run_coroutine_threadsafe(self.context.send_message(sub_usr, ret), asyncio.get_event_loop())
                            self.data["bili_sub_list"][sub_usr][idx]["last"] = dyn_id
                    except Exception as e:
                        raise e
            
