"""出站编解码导出。"""

from .message_codec import QQOutboundCodec
from .segment_encoder import QQOutboundSegmentEncoder

__all__ = ["QQOutboundCodec", "QQOutboundSegmentEncoder"]
