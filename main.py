from util.plugin_dev.api.v1.bot import Context, AstrMessageEvent, CommandResult
from util.plugin_dev.api.v1.config import *

class Main:
    """
    AstrBot 会传递 context 给插件。
    """
    def __init__(self, context: Context) -> None:
        self.context = context
        self.context.register_commands("helloworld", "helloworld", "内置测试指令。", 1, self.helloworld)

    def helloworld(self, message: AstrMessageEvent, context: Context):
        return CommandResult().message("Hello, World!")