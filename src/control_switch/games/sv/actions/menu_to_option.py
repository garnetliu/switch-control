
from control_switch.flow import press_until
from control_switch.games.sv import verify
from control_switch.games.sv.session import SvSession


def menu_to_option(sw: SvSession):
    """
    从菜单中选择一个选项
    """
    config = sw.config
    # 按 A 出操作菜单（底下有「要拿……怎么办？」的对话框），没出来就再按
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: verify.has_dialog_box(s, config),
        "盒子的操作菜单",
    )