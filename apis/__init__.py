"""API mixin 导出。"""

from .account import QQAccountApiMixin
from .file import QQFileApiMixin
from .group import QQGroupApiMixin
from .message import QQMessageApiMixin
from .qzone import QQQzoneApiMixin
from . import message_tool_patch as _message_tool_patch  # noqa: F401  （副作用导入：注册 find_user_qq_id 工具补丁）
from .support import QQApiSupportMixin
from .system import QQSystemApiMixin

__all__ = [
    "QQAccountApiMixin",
    "QQApiSupportMixin",
    "QQFileApiMixin",
    "QQGroupApiMixin",
    "QQMessageApiMixin",
    "QQQzoneApiMixin",
    "QQSystemApiMixin",
]
