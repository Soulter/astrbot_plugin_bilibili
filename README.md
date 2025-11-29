# astrbot_plugin_bilibili

这是一个为 [AstrBot](https://github.com/Soulter/AstrBot) 设计的多功能 Bilibili 插件。

## ✨ 功能特性

  - **Bilibili 视频解析**：自动识别消息中的 `BV` 号，并返回视频的详细信息。
  - **UP 主动态订阅**：
      - 支持订阅 `视频动态`、`图文动态` 和 `直播`。
      - 提供灵活的关键词和类型过滤。
      - 默认轮询时间为 `5` 分钟，可根据需要在插件配置中修改。
  - **多卡片样式**：
      - 支持多种动态卡片渲染样式。
      - 管理员可通过指令切换样式。
  - **推荐番剧**
      - 试着对 LLM 说 `推荐一些催泪的番剧，2016年之后的`。
      - 支持类别、番剧起始年份、番剧结束年份、番剧季度（一月番等）
      - 需要支持函数调用的 LLM。如 gpt-4o-mini
  - **QQ 小程序解析**：自动识别并解析 QQ 聊天中分享的 Bilibili 小程序，提取并返回直链。
  - 后续还会增加更多功能！！

![image](https://github.com/user-attachments/assets/972b2b99-b801-45cf-a882-6d841c9e8137)
## 🚀 安装

- 在插件市场下载
- 通过以下指令进行安装：

```shell
plugin i https://github.com/Soulter/astrbot_plugin_bilibili
```

## ⚙️ 配置

插件需要配置 `sessdata` 才能正常获取 Bilibili 数据。

参考 [此指南](https://nemo2011.github.io/bilibili-api/#/get-credential) 获取你的 `sessdata`。

<img width="1453" alt="image" src="https://github.com/user-attachments/assets/d5342767-8e5c-4222-81da-f1cdb4b30c95">

## 📖 使用说明

### 动态订阅指令

| 指令 | 参数 | 说明 | 别名 |
| :--- | :--- | :--- | :--- |
| **订阅动态** | `<B站UID> [过滤器...]` | 订阅指定 UP 主的动态。可以添加多个过滤器（以空格分隔）以排除不感兴趣的内容。 | `bili_sub` |
| **订阅列表** | (无) | 显示当前会话的所有订阅。 | `bili_sub_list` |
| **订阅删除** | `<B站UID>` | 删除当前会话中对指定 UP 主的订阅。 | `bili_sub_del` |
| **全局删除** | `<SID>` | **[管理员]** 删除指定 SID 会话的所有订阅。使用 `/sid` 指令可查看会话 SID。 | `bili_global_del` |
| **全局列表** | (无) | **[管理员]** 查看所有会话的订阅情况。 | `bili_global_list` |
| **全局订阅** | `<SID> <B站UID> [过滤器...]` | **[管理员]** 为指定 SID 会话添加对 UP 主的订阅。 | `bili_global_sub` |
| **订阅测试** | `<B站UID>` | 测试订阅功能。仅测试获取动态与渲染图片功能，不保存订阅信息。 | `bili_sub_test` |
| **卡片样式** | `[样式名]` | **[管理员]** 切换动态卡片渲染样式。不带参数查看可用样式列表。 | `bili_card_style` |

#### 过滤器说明

过滤器可以是以下几种类型：

  - `forward`：过滤掉转发动态。
  - `lottery`：过滤掉互动抽奖动态。
  - `video`：过滤掉视频发布动态。
  - `article`：过滤掉专栏动态。
  - `draw`：过滤掉图文动态。
  - `live`：过滤掉直播动态。
  - **正则表达式**：任何不属于上述关键字的字符串都将被视为正则表达式，用于过滤动态文本内容。

**示例**：
`/订阅动态 123456 lottery 关注`
`/bili_sub 123456 lottery 关注`
这条指令会订阅 UID 为 `123456` 的 UP 主，但会过滤掉**抽奖动态**以及动态内容中包含“**关注**”二字的动态。

> **提示**：该指令也用于更新已订阅 UP 主的过滤条件。

## 适用平台/适配器

  - aiocqhttp
  - nakuru

## Contributors

1. [@Flartiny](https://github.com/Flartiny)
2. [@Soulter](https://github.com/Soulter)

## 常见问题

1. 渲染图片失败 (尝试次数: 1): 500, message='Internal Server Error'  
一般是公共接口不稳定性导致，详见[issue43](https://github.com/Soulter/astrbot_plugin_bilibili/issues/43)

2. 错误代码-352  
尝试[issue34](https://github.com/Soulter/astrbot_plugin_bilibili/issues/34)中方法

3. AstrBot更新到4.0版本后订阅失效  
UMO结构发生了变化，已为"全局列表"指令添加了具体订阅信息，使用该指令查看后重新订阅即可。
简便的方法是进入data/plugin_data/astrbot_plugin_bilibili文件夹修改UMO的第一部分（使用"/sid"指令了解区别）。

## 更新日志

### v1.4.16
- 新增多卡片样式支持，内置 `modern`（现代风格）和 `classic`（经典风格）两种样式
- 新增管理员指令 `/卡片样式` 用于切换和查看动态卡片渲染样式

### v1.4.15
- 修复412导致的无法获取直播动态
- 注意到图片缓存占用空间过大，先新增自动清理功能
- 优化b站链接自动解析，现可解析短链接

### v1.4.14

- 清除了v1.4.8添加的自部署t2i接口相关代码，完全应用上游接口。详见AstrBot PR[#1947](https://github.com/AstrBotDevs/AstrBot/pull/1947)。统一自部署t2i接口配置项到"配置文件-系统配置-文本转图像服务 API 地址"
- 引入动态缓存，尽量保证有效动态推送且仅推送一次
- ‼️astrbot_plugin_bilibili >= v1.4.14 需要 Astrbot >= 4.5.2；原因是使用了Astrbot >= 4.5.2推荐的函数调用写法，而Astrbot >= 4.5.3修复了webui工具显示错误，推荐升级到Astrbot >= 4.5.3

历史日志见 [CHANGELOG.md](CHANGELOG.md)
