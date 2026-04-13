from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..send_handler.message_send_handler import LumaSendHandler


class LumaAPI:
    def __init__(self, send_handler: "LumaSendHandler"):
        self.send_handler: "LumaSendHandler" = send_handler
