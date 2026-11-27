from control_switch.log import new_log

from ..session import IncubatorSession


def initialize(sw: IncubatorSession) -> str:
    new_log(sw, "start")
    return "fetch"
