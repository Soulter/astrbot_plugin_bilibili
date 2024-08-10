from util.plugin_dev.api.v1.bot import Context, AstrMessageEvent, CommandResult
from util.plugin_dev.api.v1.types import *

async def parse_last_dynamic(dyn: dict, data: dict):
    uid, last = data["uid"], data["last"]
    items = dyn["items"]
    
    for item in items:
        if 'modules' not in item:
            continue
        # 过滤置顶
        if 'module_tag' in item['modules'] and \
            'text' in item['modules']['module_tag'] and \
            item['modules']['module_tag']['text'] == '置顶':
            continue
        
        if item['id_str'] == last:
            # 无新动态
            return None, None
        
        dyn_id = item['id_str']
        
        # 用户名称
        name = item['modules']['module_author']['name']
        
        # 投稿视频
        if item['type'] == 'DYNAMIC_TYPE_AV':
            archive = item['modules']['module_dynamic']['major']['archive']
            title = archive['title']
            bv = archive['bvid']
            cover_url = archive['cover']
            return CommandResult(
                message_chain=[Plain(f"你订阅的UP {name} 投稿了新视频：\n{title}\n{bv}"),
                               Image.fromURL(cover_url)],
            ).use_t2i(False), dyn_id
            
        # 图文
        elif item['type'] == 'DYNAMIC_TYPE_DRAW' or item['type'] == 'DYNAMIC_TYPE_WORD':
            ls = [Plain(f"你订阅的UP {name} 发布了新图文动态：\n")]
            opus = item['modules']['module_dynamic']['major']['opus']
            summary = opus['summary']['text']
            ls.append(Plain(summary))
            if 'pics' in opus:
                for pic in opus['pics']:
                    ls.append(Image.fromURL(pic['url']))
                    
            return CommandResult(message_chain=ls).use_t2i(False), dyn_id
        