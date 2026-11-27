"""按 B 退出盒子或菜单，直到回到野外；在野餐里就先收起野餐。"""

from control_switch.flow import capture
from control_switch.games.sv import verify
from control_switch.games.sv.session import SvSession

from .close_picnic import close_picnic


def exit_to_overworld(sw: SvSession) -> None:
    """按 B 退出盒子或菜单，直到回到野外；在野餐里就先收起野餐。按了 exit_presses 次还回不到野外抛 RuntimeError。"""
    config = sw.config
    presses = 0
    # 退回野外：最多按几次 B，每次之后等几秒
    exit_presses = 8
    while True:
        image = capture(sw, "退出到野外")
        if verify.is_overworld(image, config):
            return
        if verify.is_picnic(image, config):
            close_picnic(sw)
            continue
        if presses >= exit_presses:
            raise RuntimeError(f"按了 {exit_presses} 次 B，还是回不到野外")
        sw.click("B", config.wait.press_interval)
        presses += 1
