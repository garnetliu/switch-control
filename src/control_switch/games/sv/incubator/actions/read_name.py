from control_switch.flow import read_stable

from .. import verify
from ..session import IncubatorSession


def read_name(sw: IncubatorSession) -> str:
    """读面板上的名字，连着几帧一样、不是空的才算。"""
    return read_stable(sw, lambda s: verify.panel_name(s) or None, "面板的名字")
