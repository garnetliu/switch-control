"""孵蛋刷闪的配置：坐标、颜色阈值、等待时间、按键路线。坐标是占画面宽高的比例，按 1920×1080 量的。"""

from importlib.resources import files
from pathlib import Path

from control_switch.games.sv.config import SvConfig
from control_switch.types import Hsv, Rect


class EggConfig(SvConfig):
    """孵蛋刷闪的配置。"""

    log_dir = SvConfig.root / "runs" / "logs" / "sv-egg"

    # ---- 玩法 ----
    # 孵的宝可梦，也是亲代
    parent_name = "爱吃豚"
    # 能力最多 6 项「最棒」，亲代到了就不再比较孵出来的能力
    best_max = 6
    # 放蛋的盒子，按顺序。开野餐前盒子要停在第一个上，三个盒子的空格加起来不少于 max_eggs
    egg_boxes: tuple[int, ...] = (30, 31)
    # 野餐时火焰之躯放在这个盒子的第 1 格（这个盒子要空着，不能是放蛋的盒子）
    flame_box = 29
    # 看名字认队伍：火焰之躯和百变怪（盒子面板上读到的名字）
    flame_name = "鸭嘴火兽"
    ditto_name = "Ditto"
    # 一次野餐最多收几个蛋
    max_eggs = 30
    # 三明治效果 30 分钟，到时间就收野餐
    picnic_minutes = 29
    # 多久查一次篮子（秒），不能超过 180，不然 Switch 会休眠
    basket_interval = 150
    # 等篮子时每隔几秒按一下键，不让 Switch 休眠
    keepalive_button = "L"
    keepalive_gap = 30.0
    # panel_shiny 的阈值：三个通道标准差之和
    shiny_std = 80.0
    # 盒子一共几个
    box_count = 32
    # 光标最多按几下
    cursor_max_presses = 30
    # 按完等光标变化最多几秒
    cursor_wait = 2.0
    # 盒子里按键之后等几秒
    box_click_wait = 0.5
    # 按完 A（进主菜单的某一行）等几秒
    menu_confirm_wait = 0.5
    # 按完 A 走到桌子前、进食谱等几秒
    press_wait = 0.15
    # 按 Y、A 结束野餐之后等几秒
    end_picnic_wait = 0.5
    # 退出盒子最多按几次 B、每次之后等几秒
    exit_presses = 10
    exit_wait = 1.5

    # ---- 画面判断 ----
    dialog_corner: Rect = ((0.251, 0.724), (0.271, 0.741))
    dialog_body: Rect = ((0.292, 0.75), (0.708, 0.88))
    dialog_yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    dialog_corner_ratio = 0.3
    dialog_dark_max = 60
    dialog_dark_ratio = 0.8
    battle_button: Rect = ((0.78, 0.648), (0.969, 0.708))
    battle_ratio = 0.5
    # 小地图外圈：圆心和半径（半径按画面高度的比例），圈上按青、绿、黄分段着色。
    # 三种颜色在圈上各占至少 minimap_ratio 才算野外。只看一种颜色不行：盒子画面那里是青色，
    # 野餐画面是绿色；只看地图里的土黄色也不行，沙漠地形孵化动画时整片地面都是土黄色
    minimap_center = (0.90625, 0.8333)
    minimap_radii = (0.124, 0.128)
    minimap_colors: tuple[tuple[Hsv, Hsv], ...] = (
        ((80, 100, 150), (105, 255, 255)),
        ((40, 100, 150), (80, 255, 255)),
        ((20, 100, 150), (35, 255, 255)),
    )
    minimap_ratio = 0.1
    # 按 X 之后几秒没出主菜单就再按一次
    menu_retry = 3.0
    # 对话框按 A 之后几秒没关掉就再按一次
    dialog_retry = 1.5
    # 读不出盒子名时，几秒后往下按一格（第 1 行格子上方的名字会挡住盒子名）
    title_retry = 2.0
    picnic_icons: tuple[Rect, ...] = (
        ((0.024, 0.702), (0.048, 0.747)),
        ((0.024, 0.866), (0.048, 0.911)),
        ((0.024, 0.917), (0.048, 0.962)),
    )
    picnic_white: tuple[Hsv, Hsv] = ((0, 0, 200), (180, 40, 255))
    picnic_ratio = 0.15
    prompt_area: Rect = ((0.6, 0.45), (0.95, 0.72))
    menu_rows = 6
    menu_left = 0.693
    menu_right = 0.953
    menu_top = 0.224
    menu_row_height = 0.0736
    menu_yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    menu_ratio = 0.4
    riding_text: Rect = ((0.11, 0.935), (0.23, 0.99))
    box_title_area: Rect = ((0.34, 0.11), (0.56, 0.165))
    # 队伍第 0 格、盒子第 0 行第 0 列的范围，和相邻格子的间距（横向, 纵向）
    party_cell: Rect = ((0.021, 0.185), (0.208, 0.296))
    box_cell: Rect = ((0.234, 0.185), (0.2965, 0.296))
    cell_step = (0.0656, 0.1167)
    cursor_yellow: tuple[Hsv, Hsv] = ((20, 150, 200), (35, 255, 255))
    cursor_ratio = 0.5
    panel_name_area: Rect = ((0.70, 0.005), (0.86, 0.07))
    panel_stats: tuple[Rect, ...] = (
        ((0.82, 0.195), (0.90, 0.24)),
        ((0.885, 0.305), (0.96, 0.35)),
        ((0.885, 0.405), (0.96, 0.45)),
        ((0.82, 0.47), (0.90, 0.515)),
        ((0.70, 0.405), (0.78, 0.45)),
        ((0.70, 0.305), (0.78, 0.35)),
    )
    shiny_area: Rect = ((0.878, 0.081), (0.906, 0.127))
    # 蛋：格子下 3/4、横向中间一半里，白色和浅绿色的占比范围
    egg_white: tuple[Hsv, Hsv] = ((0, 0, 216), (180, 34, 255))
    egg_white_range = (0.17, 0.27)
    egg_green: tuple[Hsv, Hsv] = ((35, 61, 151), (80, 255, 255))
    egg_green_range = (0.03, 0.15)
    recipe_title: Rect = ((0.05, 0.0), (0.2, 0.06))
    recipe_name: Rect = ((0.57, 0.21), (0.80, 0.26))

    # ---- 野餐和三明治 ----
    picnic_timeout = 30.0
    camera_wait = 0.7
    ride_wait = 2.5
    walk_to_table = 0.24
    dialog_wait = 3.0
    whistle_wait = 5.0
    table_attempts = 5
    recipe_wait = 1.0
    recipe_downs = 5
    recipe_down_wait = 0.6
    recipe_name_text = "超级花生酱"
    pick_wait = 2.0
    start_wait = 7.0
    # 放材料：("U"|"D"|"L"|"R", 秒) 左摇杆推满；("A+", 秒) 按住 A；("A+方向", 秒) 按住 A 的同时推；("A-", 秒) 松开 A 再等
    filling_moves: tuple[tuple[str, float], ...] = (
        ("U", 0.65), ("A+", 0.5), ("A+D", 0.65), ("A+L", 0.45), ("A-", 0.8),
        ("U", 0.65), ("R", 0.45), ("A+", 0.5), ("A+D", 0.65), ("A-", 0.8),
        ("U", 0.65), ("A+", 0.5), ("A+D", 0.65), ("A+R", 0.45), ("A-", 1.5),
    )  # fmt: skip
    bread_left = 0.35
    bread_wait = 5.0
    skewer_wait = 18.0
    eat_wait = 4.0
    eat_timeout = 60.0

    # ---- 去篮子和收蛋 ----
    unride_wait = 1.0
    # ("U"|"D"|"L"|"R", 秒) 左摇杆推满这么多秒再等 basket_step_wait；("btn:L", 秒) 按 L 再等这么多秒
    basket_route: tuple[tuple[str, float], ...] = (
        ("U", 0.32), ("L", 0.08), ("btn:L", 0.48), ("U", 0.32),
        ("R", 0.08), ("btn:L", 0.48), ("U", 0.64),
        ("R", 0.08), ("btn:L", 0.48), ("U", 0.32),
        ("R", 0.08), ("btn:L", 0.48),
        ("U", 0.8), ("D", 0.2), ("U", 0.08), ("btn:L", 0.48),
    )  # fmt: skip
    basket_step_wait = 0.48
    collect_wait = 1.2
    collect_attempts = 20
    camera_turn_every = 10
    camera_turn_hold = 0.24

    # ---- 孵蛋 ----
    ride_circle_wait = 0.5
    circle_interval = 0.5
    hatch_press_wait = 1.0
    hatch_timeout = 60.0
    circle_timeout = 600.0
    flee_downs = 3
    flee_down_wait = 0.4
    flee_wait = 5.0
    flee_attempts = 5
    eggs_per_load = 5

    # ---- 检查和放生 ----
    release_downs = 4
    release_down_wait = 0.4
    swap_wait = 1.0

    # ---- 修改 4：确认、重试和超时 ----
    # 拿着宝可梦时盒子底栏只剩「显示宝可梦」「返回」，没有「替换」
    holding_area: Rect = ((0.30, 0.94), (0.70, 0.99))
    holding_text = "替换"
    pick_interval = 1.0
    pick_timeout = 10.0
    # 能力判定页：六项能力读到这些词的至少 judge_min 项，不是的话按 PLUS 切换
    judge_words = ("最棒", "了不起", "非常好", "相当好", "一般般", "也许不行")
    judge_min = 4
    judge_wait = 1.84
    judge_tries = 10
    # 读面板：连续两帧一样才算，每帧之间隔几秒，最多读几次
    read_gap = 0.2
    read_tries = 5
    # 光标到位后等几秒
    cursor_settle_wait = 0.3
    # 换盒子：每按一下之后等几秒，到位后等几秒；盒子编号、蛋的位置连续两帧一样才用，帧间隔几秒
    box_turn_wait = 0.3
    box_settle_wait = 0.8
    box_frame_gap = 0.3
    box_rounds = 5
    box_title_tries = 10
    # 收蛋循环
    collect_timeout = 300.0
    quiet_frames = 3
    quiet_gap = 0.3
    # 孵化结束：野外连续几帧、每帧间隔几秒
    stable_frames = 4
    stable_gap = 0.5
    # 结束野餐：按 Y 等确认框、按 A 等回到野外，每隔几秒重按，最多等几秒，最后再等几秒
    leave_prompt_interval = 5.0
    leave_prompt_timeout = 25.0
    leave_overworld_interval = 1.2
    leave_overworld_timeout = 20.0
    leave_final_wait = 3.0
    # 战斗菜单四行（战斗、宝可梦、包包、逃走）：第 0 行的范围用 battle_button，每行往下的间距
    battle_rows = 4
    # 四行（战斗、宝可梦、包包、逃走）的间距，真机量的：每行 87 像素（1080 高）
    battle_row_step = 0.0806
    flee_row = 3
    # 逃走：回到野外要连续几帧、最多等几秒、每帧间隔几秒
    flee_stable_frames = 2
    flee_timeout = 10.0
    flee_gap = 0.5
    flee_move_interval = 1.0
    # 做三明治：桌子菜单按 A 的间隔和超时；选签子界面的识别；进选签子、开始做的按 A 间隔
    table_interval = 1.5
    table_timeout = 15.0
    pick_title: Rect = ((0.0, 0.0), (0.3, 0.06))
    pick_title_text = "食谱模式"
    pick_hint: Rect = ((0.5, 0.0), (1.0, 0.08))
    pick_hint_text = "签"
    pick_press_interval = 2.0
    make_press_interval = 1.5
    # 主菜单按 A 进某一行之后，菜单没消失就隔几秒重按
    menu_enter_interval = 1.5
    # 开野餐认出之后等几秒（丢精灵球的动画期间人不能动）
    picnic_settle_wait = 8.0
    # 存档：按 R 等确认框、按 A 等对话，各最多几秒；按键之后等几秒
    save_prompt_timeout = 10.0
    save_dialog_timeout = 15.0
    save_click_wait = 0.5
    # 盒子里按 A 出来的操作菜单：选项的范围（第 0 行）、行高、行数、黄色占比
    operation_rect: Rect = ((0.235, 0.194), (0.385, 0.2496))
    operation_rows = 6
    operation_step = 0.0556
    operation_ratio = 0.3
    operation_interval = 1.5
    release_text = "放生"

    # ---- 飞到零区闸口（fly.py） ----
    gate_name = "零区闸口"
    fly_icon = Path(str(files("control_switch.games.sv") / "data" / "fly_icon.png"))
    fly_icon_score = 0.8
    # 地图画面：左上角的标题、能看到地图的范围、光标的位置（画面中间）、光标上方的地点名
    map_title: Rect = ((0.17, 0.12), (0.25, 0.18))
    map_title_text = "地图"
    map_area: Rect = ((0.13, 0.19), (0.87, 0.81))
    map_cursor = (0.5, 0.5)
    map_tooltip: Rect = ((0.40, 0.32), (0.60, 0.42))
    # 摇杆推满时地图光标每秒移动多少（占画面宽度的比例，真机量的约 0.45）
    map_cursor_speed = 0.45
    map_move_min = 0.05
    map_move_wait = 0.8
    map_moves = 10
    map_retry = 2.0
    fly_timeout = 30.0
    # 看不到飞行点时轻推光标的方向（x, y，y 正数向上）、摇杆推多少、推几秒；PokemonAutomation 是往下推 0.252 推 0.16 秒
    map_probes: tuple[tuple[int, int], ...] = (
        (0, -1),
        (0, 1),
        (0, 1),
        (0, -1),
        (1, 0),
        (-1, 0),
        (-1, 0),
    )
    map_probe_tilt = 0.252
    map_probe_time = 0.16
    # 地图上按 A 出的菜单（飞翔、设置为目的地、取消）
    fly_menu_area: Rect = ((0.50, 0.45), (0.72, 0.80))
    fly_text = "飞翔"
    cancel_text = "取消"
    # 离开飞行点：摇杆往右前方推 gate_turn 秒（y 是推多少），再往前走；野餐走 1 秒、孵蛋骑着走 1.6 秒（PokemonAutomation 的数）
    gate_turn = 0.4
    gate_turn_y = 0.75
    picnic_walk = 1.0
    ramp_walk = 1.6
    # 野餐时左下角坐骑的提示：「收回故勒顿」说明坐骑在外面
    ride_hint: Rect = ((0.05, 0.81), (0.2, 0.86))
    ride_out_text = "收回"
    # 对话框里的文字；桌子的对话是「是野餐组合！」
    dialog_text: Rect = ((0.27, 0.75), (0.73, 0.88))
    table_text = "野餐组合"
    # 做三明治的画面：底下的提示「长按以抓起」
    making_hint: Rect = ((0.40, 0.93), (0.60, 0.995))
    making_hint_text = "长按以抓起"
