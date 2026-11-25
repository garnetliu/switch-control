"""initialize：找到内存里的存档块表。"""

from control_switch.log import new_log

from ..session import OutbreakSession


def initialize(sw: OutbreakSession) -> str:
    """找到存档块表。"""
    new_log(sw, "start")
    sw.blocks.locate()
    return "knockout" if sw.config.knockout else "refresh"
