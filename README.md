# MaiBot SnowLuma Adapter
本项目是对接SnowLuma的适配器，支持两种工作格式
- 直接使用MaiBot的maim_message库进行连接
- 作为Adapter插件被MaiBot加载

## 主动私聊工具

在 `[plugin]` 中将 `enable_private_chat_tool` 设置为 `true` 后，模型可以调用 `open_private_chat` 打开指定 QQ 用户的私聊聊天流并发送首条私聊消息。发送成功后，该用户 15 分钟内的私聊入站消息会绕过私聊名单黑白名单过滤，但仍会遵守全局屏蔽用户规则。

如果只知道某条消息的 `msg_id`，可以先调用 `get_qq_by_msg_id` 获取该消息发送者的 QQ 号，再传给 `open_private_chat`。
