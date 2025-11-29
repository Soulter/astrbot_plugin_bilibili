"""
UI 开发模式 - 模拟数据模块
提供各种动态类型和元数据组合的模拟数据，用于 UI 开发和测试
"""

import base64
import io
from typing import Dict, Any, List, Optional
import qrcode

# ==================== 基础工具函数 ====================

def create_qrcode_sync(url: str) -> str:
    """同步生成二维码 Base64"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="#fb7299", back_color="white")
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    base64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{base64_str}"


def create_base_render_data() -> Dict[str, Any]:
    """创建基础渲染数据结构"""
    return {
        "name": "",
        "avatar": "",
        "pendant": "",
        "text": "",
        "image_urls": [],
        "qrcode": "",
        "url": "",
        "title": "",
        "type": "",
        "forward": None,
    }


# ==================== 示例图片 URL (使用 picsum.photos 占位图) ====================

SAMPLE_AVATARS = [
    "https://picsum.photos/seed/avatar1/200/200",
    "https://picsum.photos/seed/avatar2/200/200",
    "https://picsum.photos/seed/avatar3/200/200",
    "https://picsum.photos/seed/avatar4/200/200",
]

SAMPLE_PENDANTS = [
    "https://i0.hdslb.com/bfs/garb/item/4f8f3f1f8a6d7e8b9c0d1e2f3a4b5c6d.png",  # B站挂件示例
    "",  # 无挂件
]

SAMPLE_COVERS = [
    "https://picsum.photos/seed/cover1/672/378",
    "https://picsum.photos/seed/cover2/672/378",
    "https://picsum.photos/seed/cover3/672/378",
]

SAMPLE_IMAGES = [
    "https://picsum.photos/seed/img1/800/600",
    "https://picsum.photos/seed/img2/600/800",
    "https://picsum.photos/seed/img3/800/800",
    "https://picsum.photos/seed/img4/1200/800",
    "https://picsum.photos/seed/img5/800/1200",
    "https://picsum.photos/seed/img6/600/600",
    "https://picsum.photos/seed/img7/900/600",
    "https://picsum.photos/seed/img8/600/900",
    "https://picsum.photos/seed/img9/700/700",
]

SAMPLE_EMOJIS = [
    ("https://i0.hdslb.com/bfs/emote/3087d273a78ccaff4bb1e9972e2ba2a7583c9f11.png", "[doge]"),
    ("https://i0.hdslb.com/bfs/emote/bf03720868a26f230fc0dd4c5a8bda9d4b1a8c0b.png", "[笑哭]"),
    ("https://i0.hdslb.com/bfs/emote/6ea59c827c414b4a2955fe79e0f6fd3dcd515e24.png", "[妙啊]"),
]


# ==================== 模拟用户数据 ====================

MOCK_USERS = [
    {
        "name": "某科学的超电磁炮",
        "avatar": "https://picsum.photos/seed/user1/200/200",
        "pendant": "",
    },
    {
        "name": "哔哩哔哩番剧",
        "avatar": "https://picsum.photos/seed/user2/200/200",
        "pendant": "",
    },
    {
        "name": "老番茄",
        "avatar": "https://picsum.photos/seed/user3/200/200",
        "pendant": "",
    },
    {
        "name": "影视飓风",
        "avatar": "https://picsum.photos/seed/user4/200/200",
        "pendant": "",
    },
    {
        "name": "超长用户名测试_这是一个非常非常长的用户名用于测试UI显示效果",
        "avatar": "https://picsum.photos/seed/user5/200/200",
        "pendant": "",
    },
]


# ==================== 动态类型模拟数据生成器 ====================

class MockDataGenerator:
    """模拟数据生成器"""
    
    @staticmethod
    def video_dynamic(
        user_index: int = 0,
        title: str = "【4K】这可能是你看过最震撼的视频",
        content: str = "新视频来啦！这次给大家带来超级震撼的内容，记得三连支持~",
        with_qrcode: bool = True,
        cover_index: int = 0,
    ) -> Dict[str, Any]:
        """
        视频动态 (DYNAMIC_TYPE_AV)
        """
        user = MOCK_USERS[user_index % len(MOCK_USERS)]
        data = create_base_render_data()
        data.update({
            "name": user["name"],
            "avatar": user["avatar"],
            "pendant": user["pendant"],
            "type": "DYNAMIC_TYPE_AV",
            "title": title,
            "text": f"投稿了新视频<br>{content}",
            "image_urls": [SAMPLE_COVERS[cover_index % len(SAMPLE_COVERS)]],
        })
        if with_qrcode:
            url = "https://www.bilibili.com/video/BV1xx411c7mD"
            data["qrcode"] = create_qrcode_sync(url)
            data["url"] = url
        return data

    @staticmethod
    def draw_dynamic(
        user_index: int = 0,
        title: str = "",
        content: str = "今天天气真好，分享一些照片给大家~",
        image_count: int = 3,
        with_qrcode: bool = True,
        with_topic: bool = False,
        with_emoji: bool = False,
    ) -> Dict[str, Any]:
        """
        图文动态 (DYNAMIC_TYPE_DRAW)
        支持 1-9 张图片
        """
        user = MOCK_USERS[user_index % len(MOCK_USERS)]
        data = create_base_render_data()
        
        text = content
        if with_topic:
            text = "<a href='https://search.bilibili.com/all?keyword=日常'># 日常分享</a><br>" + text
        if with_emoji:
            emoji_url, emoji_text = SAMPLE_EMOJIS[0]
            text = text + f" <img src='{emoji_url}'>"
        
        data.update({
            "name": user["name"],
            "avatar": user["avatar"],
            "pendant": user["pendant"],
            "type": "DYNAMIC_TYPE_DRAW",
            "title": title,
            "text": text,
            "image_urls": SAMPLE_IMAGES[:min(image_count, 9)],
        })
        if with_qrcode:
            url = "https://t.bilibili.com/123456789"
            data["qrcode"] = create_qrcode_sync(url)
            data["url"] = url
        return data

    @staticmethod
    def word_dynamic(
        user_index: int = 0,
        content: str = "今天也是元气满满的一天！大家早上好~",
        with_qrcode: bool = True,
        with_topic: bool = False,
        with_emoji: bool = True,
    ) -> Dict[str, Any]:
        """
        纯文字动态 (DYNAMIC_TYPE_WORD)
        """
        user = MOCK_USERS[user_index % len(MOCK_USERS)]
        data = create_base_render_data()
        
        text = content
        if with_topic:
            text = "<a href='https://search.bilibili.com/all?keyword=日常'># 每日打卡</a><br>" + text
        if with_emoji:
            emoji_url, emoji_text = SAMPLE_EMOJIS[1]
            text = text + f" <img src='{emoji_url}'>"
        
        data.update({
            "name": user["name"],
            "avatar": user["avatar"],
            "pendant": user["pendant"],
            "type": "DYNAMIC_TYPE_WORD",
            "title": "",
            "text": text,
            "image_urls": [],
        })
        if with_qrcode:
            url = "https://t.bilibili.com/987654321"
            data["qrcode"] = create_qrcode_sync(url)
            data["url"] = url
        return data

    @staticmethod
    def article_dynamic(
        user_index: int = 0,
        title: str = "深度解析：为什么这部番剧能成为神作",
        content: str = "本文将从剧情、作画、音乐等多个维度分析这部作品的成功之处...",
        with_qrcode: bool = True,
        cover_index: int = 1,
    ) -> Dict[str, Any]:
        """
        专栏文章动态 (DYNAMIC_TYPE_ARTICLE)
        """
        user = MOCK_USERS[user_index % len(MOCK_USERS)]
        data = create_base_render_data()
        data.update({
            "name": user["name"],
            "avatar": user["avatar"],
            "pendant": user["pendant"],
            "type": "DYNAMIC_TYPE_ARTICLE",
            "title": title,
            "text": content,
            "image_urls": [SAMPLE_COVERS[cover_index % len(SAMPLE_COVERS)]],
        })
        if with_qrcode:
            url = "https://www.bilibili.com/read/cv12345678"
            data["qrcode"] = create_qrcode_sync(url)
            data["url"] = url
        return data

    @staticmethod
    def forward_dynamic(
        user_index: int = 0,
        forward_user_index: int = 1,
        comment: str = "转发动态",
        forward_type: str = "video",  # video, draw, word
        with_qrcode: bool = True,
    ) -> Dict[str, Any]:
        """
        转发动态 (DYNAMIC_TYPE_FORWARD)
        """
        user = MOCK_USERS[user_index % len(MOCK_USERS)]
        forward_user = MOCK_USERS[forward_user_index % len(MOCK_USERS)]
        data = create_base_render_data()
        
        # 构建被转发的内容
        forward_data = {
            "name": forward_user["name"],
            "avatar": forward_user["avatar"],
            "pendant": forward_user["pendant"],
        }
        
        if forward_type == "video":
            forward_data.update({
                "title": "【必看】年度最佳视频合集",
                "text": "这个视频太棒了，强烈推荐！",
                "image_urls": [SAMPLE_COVERS[0]],
            })
        elif forward_type == "draw":
            forward_data.update({
                "title": "",
                "text": "分享一些好看的图片~",
                "image_urls": SAMPLE_IMAGES[:3],
            })
        else:  # word
            forward_data.update({
                "title": "",
                "text": "今天心情很好！",
                "image_urls": [],
            })
        
        data.update({
            "name": user["name"],
            "avatar": user["avatar"],
            "pendant": user["pendant"],
            "type": "DYNAMIC_TYPE_FORWARD",
            "text": comment,
            "forward": forward_data,
        })
        if with_qrcode:
            url = "https://t.bilibili.com/forward123456"
            data["qrcode"] = create_qrcode_sync(url)
            data["url"] = url
        return data


# ==================== 预设场景 ====================

def get_all_mock_scenarios() -> Dict[str, Dict[str, Any]]:
    """
    获取所有预设的模拟场景
    返回: {场景名称: 渲染数据}
    """
    gen = MockDataGenerator()
    
    scenarios = {
        # ===== 视频动态 =====
        "视频动态_标准": gen.video_dynamic(),
        "视频动态_长标题": gen.video_dynamic(
            title="【4K120帧】这是一个超级超级超级长的视频标题用于测试UI在极端情况下的显示效果会不会出现溢出或者截断的问题",
            content="视频简介也可以很长，这里测试一下长文本的显示效果，看看会不会有什么问题。"
        ),
        "视频动态_无二维码": gen.video_dynamic(with_qrcode=False),
        "视频动态_长用户名": gen.video_dynamic(user_index=4),
        
        # ===== 图文动态 =====
        "图文动态_1图": gen.draw_dynamic(image_count=1),
        "图文动态_2图": gen.draw_dynamic(image_count=2),
        "图文动态_3图": gen.draw_dynamic(image_count=3),
        "图文动态_4图": gen.draw_dynamic(image_count=4),
        "图文动态_5图": gen.draw_dynamic(image_count=5),
        "图文动态_6图": gen.draw_dynamic(image_count=6),
        "图文动态_7图": gen.draw_dynamic(image_count=7),
        "图文动态_8图": gen.draw_dynamic(image_count=8),
        "图文动态_9图": gen.draw_dynamic(image_count=9),
        "图文动态_带话题": gen.draw_dynamic(with_topic=True, image_count=3),
        "图文动态_带表情": gen.draw_dynamic(with_emoji=True, image_count=2),
        "图文动态_带标题": gen.draw_dynamic(title="今日份的快乐分享", image_count=4),
        "图文动态_长文本": gen.draw_dynamic(
            content="这是一段非常长的动态内容，用于测试文本在卡片中的显示效果。" * 10,
            image_count=3
        ),
        
        # ===== 纯文字动态 =====
        "文字动态_标准": gen.word_dynamic(),
        "文字动态_带话题": gen.word_dynamic(with_topic=True),
        "文字动态_无表情": gen.word_dynamic(with_emoji=False),
        "文字动态_长文本": gen.word_dynamic(
            content="这是一段超长的纯文字动态内容，用于测试在没有图片的情况下，卡片如何显示大量文本。" * 15
        ),
        "文字动态_多行文本": gen.word_dynamic(
            content="第一行内容<br>第二行内容<br>第三行内容<br>第四行内容<br>第五行内容"
        ),
        
        # ===== 专栏文章 =====
        "专栏文章_标准": gen.article_dynamic(),
        "专栏文章_长标题": gen.article_dynamic(
            title="【深度长文】从零开始的异世界生活第二季深度解析：剧情、人物、世界观全方位分析"
        ),
        
        # ===== 转发动态 =====
        "转发动态_转发视频": gen.forward_dynamic(forward_type="video"),
        "转发动态_转发图文": gen.forward_dynamic(forward_type="draw"),
        "转发动态_转发文字": gen.forward_dynamic(forward_type="word"),
        "转发动态_长评论": gen.forward_dynamic(
            comment="这个视频/动态太棒了！强烈推荐给大家！" * 5,
            forward_type="video"
        ),
        
        # ===== 边界情况 =====
        "边界_空内容": {
            **create_base_render_data(),
            "name": "测试用户",
            "avatar": SAMPLE_AVATARS[0],
            "type": "DYNAMIC_TYPE_WORD",
        },
        "边界_无头像": {
            **create_base_render_data(),
            "name": "无头像用户",
            "avatar": "",
            "type": "DYNAMIC_TYPE_WORD",
            "text": "这是一个没有头像的用户发布的动态",
        },
        "边界_特殊字符": gen.word_dynamic(
            content="测试特殊字符: <script>alert('xss')</script> &lt;div&gt; &amp; © ® ™ 😀 🎉 🔥"
        ),
    }
    
    return scenarios


def get_scenario_names() -> List[str]:
    """获取所有场景名称列表"""
    return list(get_all_mock_scenarios().keys())


def get_scenario_by_name(name: str) -> Optional[Dict[str, Any]]:
    """根据名称获取指定场景的渲染数据"""
    scenarios = get_all_mock_scenarios()
    return scenarios.get(name)


# ==================== 分类获取 ====================

def get_scenarios_by_category() -> Dict[str, List[str]]:
    """按类别获取场景名称"""
    all_names = get_scenario_names()
    categories = {
        "视频动态": [],
        "图文动态": [],
        "文字动态": [],
        "专栏文章": [],
        "转发动态": [],
        "边界情况": [],
    }
    
    for name in all_names:
        for cat in categories:
            if name.startswith(cat.replace("情况", "")):
                categories[cat].append(name)
                break
    
    return categories


if __name__ == "__main__":
    # 测试输出
    print("可用的模拟场景:")
    for cat, names in get_scenarios_by_category().items():
        print(f"\n{cat}:")
        for name in names:
            print(f"  - {name}")

