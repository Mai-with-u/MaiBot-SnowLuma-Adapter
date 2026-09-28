"""通知文本渲染器（SnowLuma 富文本风格 + NapCat 全量事件分支）。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Mapping

from ...qq_face_map import QQ_FACE_DESCRIPTIONS

DisplayNameResolver = Callable[[str, str, str], Awaitable[str]]


class QQNoticeTextRenderer:
    """根据通知载荷生成可读文本。

    文本格式移植自 SnowLuma 适配器（``[事件-xxx]`` 前缀、操作者真名解析、
    poke raw_info 动作文、invite/kick/kick_me 区分、精华增删区分、消息 ID 后缀），
    并保留 NapCat 特有的全体禁言解除与自然解除分支。
    """

    async def build_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        self_id: str,
    ) -> str:
        """根据通知事件生成可读文本。

        Args:
            payload: 原始通知事件。
            resolve_display_name: 展示名解析回调（带缓存），签名为 ``(group_id, user_id, default)``。
            self_id: 当前机器人账号 ID。

        Returns:
            str: 生成的可读通知文本；返回空字符串表示无需注入。
        """
        notice_type = str(payload.get("notice_type") or "").strip()
        sub_type = str(payload.get("sub_type") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()

        if notice_type in {"group_recall", "friend_recall"}:
            return await self._build_recall_notice_text(payload, resolve_display_name, group_id, notice_type)
        if notice_type == "notify" and sub_type == "poke":
            return await self._build_poke_notice_text(payload, resolve_display_name, group_id, self_id)
        if notice_type == "notify" and sub_type == "group_name":
            new_name = str(payload.get("name_new") or payload.get("group_name") or "").strip()
            return f"[事件-群名变更] 群名称变更为 {new_name or '未知名称'}"
        if notice_type == "group_ban":
            return await self._build_group_ban_notice_text(payload, resolve_display_name, group_id, sub_type)
        if notice_type == "group_upload":
            return await self._build_group_upload_notice_text(payload, resolve_display_name, group_id)
        if notice_type == "group_increase":
            return await self._build_group_increase_notice_text(payload, resolve_display_name, group_id, sub_type)
        if notice_type == "group_decrease":
            return await self._build_group_decrease_notice_text(payload, resolve_display_name, group_id, sub_type)
        if notice_type == "group_admin":
            user_name = await resolve_display_name(group_id, str(payload.get("user_id") or "").strip(), "QQ用户")
            action_text = "被设为管理员" if sub_type == "set" else "被取消管理员"
            return f"[事件-群管理员变动] {user_name} {action_text}"
        if notice_type == "essence":
            return await self._build_essence_notice_text(payload, resolve_display_name, group_id, sub_type)
        if notice_type == "group_msg_emoji_like":
            return await self._build_emoji_like_notice_text(payload, resolve_display_name, group_id)
        return f"[notice] {notice_type}.{sub_type}".strip(".")

    async def _build_recall_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
        notice_type: str,
    ) -> str:
        """构造撤回通知文本（含消息 ID 后缀）。"""

        message_id = str(payload.get("message_id") or "").strip()
        suffix = f"（消息ID:{message_id}）" if message_id else ""
        if notice_type == "friend_recall":
            user_name = await resolve_display_name("", str(payload.get("user_id") or "").strip(), "QQ用户")
            return f"[事件-好友撤回] {user_name} 撤回了一条消息{suffix}"

        operator_name = await resolve_display_name(group_id, str(payload.get("operator_id") or "").strip(), "QQ用户")
        user_name = await resolve_display_name(group_id, str(payload.get("user_id") or "").strip(), "QQ用户")
        if operator_name and user_name and operator_name != user_name:
            return f"[事件-群消息撤回] {operator_name} 撤回了 {user_name} 的消息{suffix}"
        return f"[事件-群消息撤回] {operator_name or user_name} 撤回了一条消息{suffix}"

    async def _build_poke_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
        self_id: str,
    ) -> str:
        """构造戳一戳通知文本（含 raw_info 动作文）。"""

        user_id = str(payload.get("user_id") or "").strip()
        target_id = str(payload.get("target_id") or "").strip()
        if self_id and user_id == self_id:
            return ""

        user_name = await resolve_display_name(group_id, user_id, "QQ用户")
        target_name = await resolve_display_name(group_id, target_id, "麦麦")

        first_text = "戳了戳"
        second_text = ""
        raw_info = payload.get("raw_info")
        if isinstance(raw_info, list):
            first_text = self._extract_poke_raw_text(raw_info, 2, first_text)
            second_text = self._extract_poke_raw_text(raw_info, 4, second_text)

        if not group_id:
            # 私聊戳一戳没有群名片上下文，退回简单句式。
            target_text = f" -> {target_id}" if target_id else ""
            return f"{user_name} 发起了戳一戳{target_text}"
        return f"{user_name}{first_text}{target_name}{second_text}（这是QQ的一个功能，用于提及某人，但没那么明显）"

    @staticmethod
    def _extract_poke_raw_text(raw_info: List[Any], index: int, default: str) -> str:
        """从戳一戳 raw_info 中提取动作文本。"""

        if index >= len(raw_info):
            return default
        raw_item = raw_info[index]
        if not isinstance(raw_item, Mapping):
            return default
        return str(raw_item.get("txt") or default)

    async def _build_group_ban_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
        sub_type: str,
    ) -> str:
        """构造群禁言通知文本（含全体禁言与自然解除分支）。"""

        operator_name = await resolve_display_name(group_id, str(payload.get("operator_id") or "").strip(), "QQ用户")
        target_user_id = str(payload.get("user_id") or "").strip()
        target_name = await resolve_display_name(group_id, target_user_id, "QQ用户")
        duration = payload.get("duration")
        is_natural_lift = bool(payload.get("is_natural_lift", False))

        if sub_type == "ban":
            if target_user_id in {"", "0"}:
                return f"[事件-群禁言] {operator_name} 开启了全员禁言"
            duration_text = f"，时长 {duration} 秒" if duration not in (None, "") else ""
            return f"[事件-群禁言] {operator_name} 禁言了 {target_name}{duration_text}"
        if sub_type == "whole_lift_ban":
            if is_natural_lift:
                return "群全体禁言已自然解除"
            return f"[事件-群禁言] {operator_name} 解除了全员禁言"
        if sub_type == "lift_ban":
            if is_natural_lift:
                return f"用户 {target_name} 的禁言已自然解除"
            return f"[事件-群禁言] {operator_name} 解除了 {target_name} 的禁言"
        return f"[notice] group_ban.{sub_type}".strip(".")

    async def _build_group_upload_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
    ) -> str:
        """构造群文件上传通知文本。"""

        user_name = await resolve_display_name(group_id, str(payload.get("user_id") or "").strip(), "QQ用户")
        file_info = payload.get("file", {})
        if not isinstance(file_info, Mapping):
            file_info = {}
        file_name = str(file_info.get("name") or file_info.get("file") or "未知文件").strip()
        file_size = str(file_info.get("size") or file_info.get("file_size") or "").strip()
        size_suffix = f"，大小 {file_size}" if file_size else ""
        return f"[事件-群文件上传] {user_name} 上传了文件 {file_name}{size_suffix}"

    async def _build_group_increase_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
        sub_type: str,
    ) -> str:
        """构造入群通知文本（区分邀请入群）。"""

        user_name = await resolve_display_name(group_id, str(payload.get("user_id") or "").strip(), "QQ用户")
        increase_type = sub_type or str(payload.get("increase_type") or "").strip()
        action_text = "被邀请入群" if increase_type == "invite" else "加入了群聊"
        return f"[事件-群成员增加] {user_name} {action_text}"

    async def _build_group_decrease_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
        sub_type: str,
    ) -> str:
        """构造退群通知文本（区分 kick / kick_me）。"""

        if sub_type == "kick_me":
            return "[事件-群成员减少] 麦麦被移出了群聊"
        user_name = await resolve_display_name(group_id, str(payload.get("user_id") or "").strip(), "QQ用户")
        if sub_type == "kick":
            operator_name = await resolve_display_name(group_id, str(payload.get("operator_id") or "").strip(), "QQ用户")
            return f"[事件-群成员减少] {user_name} 被 {operator_name} 移出了群聊"
        return f"[事件-群成员减少] {user_name} 离开了群聊"

    async def _build_essence_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
        sub_type: str,
    ) -> str:
        """构造精华消息通知文本（区分设精 / 移除）。"""

        operator_name = await resolve_display_name(group_id, str(payload.get("operator_id") or "").strip(), "QQ用户")
        sender_name = await resolve_display_name(group_id, str(payload.get("sender_id") or "").strip(), "QQ用户")
        message_id = str(payload.get("message_id") or "").strip()
        suffix = f"（消息ID:{message_id}）" if message_id else ""
        if sub_type == "add":
            return f"[事件-精华消息] {operator_name} 将 {sender_name} 的消息设为精华{suffix}"
        if sub_type == "delete":
            return f"[事件-精华消息] {operator_name} 移除了 {sender_name} 的精华消息{suffix}"
        return f"[事件-精华消息] 精华消息发生变动{suffix}"

    async def _build_emoji_like_notice_text(
        self,
        payload: Mapping[str, Any],
        resolve_display_name: DisplayNameResolver,
        group_id: str,
    ) -> str:
        """构造群消息表情回应通知文本。"""

        user_name = await resolve_display_name(group_id, str(payload.get("user_id") or "").strip(), "QQ用户")
        likes = payload.get("likes", [])
        emoji_texts: List[str] = []
        if isinstance(likes, list):
            for like in likes:
                if not isinstance(like, Mapping):
                    continue
                emoji_id = str(like.get("emoji_id", "")).strip()
                count = like.get("count", 1)
                emoji_text = QQ_FACE_DESCRIPTIONS.get(emoji_id, f"未知表情{emoji_id}") if emoji_id else "未知表情"
                if count and count != 1:
                    emoji_texts.append(f"[{emoji_text}]x{count}")
                else:
                    emoji_texts.append(f"[{emoji_text}]")
        emoji_summary = "、".join(emoji_texts) if emoji_texts else "未知表情"
        message_id = str(payload.get("message_id") or "").strip()
        return f"[事件-群消息表情回应] {user_name} 对消息(ID:{message_id or '未知'})表达了 {emoji_summary}"
