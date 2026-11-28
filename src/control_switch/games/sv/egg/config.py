"""孵蛋刷闪的配置：玩法、走路路线、坐标、颜色阈值、等待时间。

坐标是占画面宽高的比例，720p（botbase）和 1080p（采集卡）通用；
照 PokemonAutomation（Arduino-Source）的 PokemonSV 孵蛋流程，真机上和上游不同的在 README 里写明。
几个脚本共用的画面判断（对话框、野外、野餐、主菜单）的配置在 SvConfig。
"""

from importlib.resources import files
from pathlib import Path

from control_switch.games.sv.config import SvConfig
from control_switch.types import Hsv, Press, Push, Rect

_DATA = files("control_switch.games.sv") / "data"


class EggConfig(SvConfig):
    """孵蛋刷闪的配置。"""

    log_dir = SvConfig.root / "runs" / "logs" / "sv-egg"

    # ---- 玩法 ----
    # 野餐队伍里的百变怪（不是亲代），日志和盒子面板上读到的名字
    ditto_name = "百变怪"
    # 做的三明治：超级花生酱三明治的食谱编号
    recipe_number = 17
    # 一次野餐最多收几个蛋，收蛋最多等几秒（三明治的效果 30 分钟）
    max_eggs = 30
    fetch_limit = 1800
    # 一共几个盒子。开始时开着的盒子放亲代和带队的，后面一个放蛋，再后面一个放留下的
    box_count = 32
    box_rows = 5
    box_columns = 6
    party_rows = 6

    # ---- 走路路线（上游的时间；Push 推左摇杆，Press 按键）----
    # 开野餐前：按 L 让镜头对准人面对的方向，往左后方走让人背对观测站，再按 L，往前走
    picnic_route: tuple[Push | Press, ...] = (
        Press("L", 0.72),
        Push(1.0, 0.75, 0.4, 0.4),
        Press("L", 0.72),
        Push(0.0, 1.0, 1.0, 0.0),
    )
    # 开了野餐，走到桌子前；没打开桌子的菜单、回到了野餐的画面时再往前走一点
    table_route: tuple[Push | Press, ...] = (Push(0.0, 1.0, 0.24, 0.32),)
    table_retry_route: tuple[Push | Press, ...] = (Push(0.0, 1.0, 0.8, 0.32),)
    # 做完三明治，从桌子前走到篮子前：先收起坐骑，往前、往左、往前过桌子、往右、往前、转向篮子、靠近、后退再往前，中间按 L 转镜头。
    # 镜头辅助开着关着都能用（上游 collect_eggs_after_sandwich 里 #if 1 的那一段）
    basket_route: tuple[Push | Press, ...] = (
        Press("PLUS", 0.84),
        Push(0.0, 1.0, 0.32, 0.48),
        Push(-1.0, 0.0, 0.08, 0.48),
        Press("L", 0.48),
        Push(0.0, 1.0, 0.32, 0.48),
        Push(1.0, 0.0, 0.08, 0.48),
        Press("L", 0.48),
        Push(0.0, 1.0, 0.64, 0.48),
        Push(1.0, 0.0, 0.08, 0.48),
        Press("L", 0.48),
        Push(0.0, 1.0, 0.32, 0.48),
        Push(1.0, 0.0, 0.08, 0.48),
        Press("L", 0.48),
        Push(0.0, 1.0, 0.8, 0.48),
        Push(0.0, -1.0, 0.2, 0.48),
        Push(0.0, 1.0, 0.08, 0.48),
        Press("L", 0.48),
    )
    # 孵蛋开始：骑上坐骑，往左后方走让人背对观测站，转镜头，往前走下坡
    ramp_route: tuple[Push | Press, ...] = (
        Press("PLUS", 0.8),
        Push(-1.0, -1.0, 0.4, 0.4),
        Press("L", 0.72),
        Push(0.0, 1.0, 2, 0.0),
    )
    # 每个蛋之前按 L 转镜头之后等几秒
    camera_wait = 1

    # ---- 桌子前和食谱 ----
    # 桌子前认出画面最多看几秒；打开食谱列表最多等几秒；列表认出之后再等几秒让它画完
    sandwich_state_timeout = 30.0
    recipe_enter_timeout = 60.0
    recipe_settle_wait = 1.0
    # 在桌子前按 A 之后等几秒
    table_press_wait = 0.8
    # 食谱列表：最多往下翻几次，每次翻页之前等几秒让画面稳定，方向键按完等几秒，等选中的箭头最多几秒
    recipe_scroll_limit = 100
    recipe_look_wait = 0.2
    recipe_move_wait = 0.48
    recipe_arrow_timeout = 10.0
    # 选中食谱之后按 A 进选签子的界面、开始做，按完等几秒；之后看几秒，画面还在原处就再按
    recipe_press_wait = 1.04
    recipe_start_look = 3.0
    # 桌子的菜单：选中第一项（做料理）的箭头
    table_arrow_area: Rect = ((0.7161, 0.3213), (0.7625, 0.4139))
    # 食谱列表：两列三行；每格的箭头（左上角、宽高）、编号（左上角、宽高）、两格之间的间距
    recipe_columns = 2
    recipe_rows = 3
    recipe_arrow_origin = (0.112, 0.0731)
    recipe_arrow_size = (0.0521, 0.0825)
    recipe_id_origin = (0.015, 0.240)
    recipe_id_size = (0.042, 0.048)
    recipe_step = (0.26, 0.277)
    # 编号是白色的数字：灰度不低于 recipe_id_white 的变成黑色，放大 recipe_id_scale 倍、加白边再认；食谱一共 151 个
    recipe_id_white = 180
    recipe_id_scale = 3
    recipe_id_border = 10
    recipe_max = 151
    # 选签子的界面：选中第一根签子的箭头
    pick_arrow_area: Rect = ((0.0208, 0.1611), (0.0672, 0.2537))

    # ---- 做三明治 ----
    # 做三明治的画面一出来就等手出现，最多几秒；盘子的标签要等几秒才出来
    hand_first_timeout = 30.0
    plate_label_wait = 2.4
    # 最开始手所在的框；中间的盘子（上面的标签）的框；三片香蕉要放的框
    hand_initial_box: Rect = ((0.440, 0.455), (0.552, 0.634))
    plate_box: Rect = ((0.455, 0.130), (0.545, 0.160))
    banana_targets: tuple[Rect, ...] = (
        ((0.386, 0.507), (0.446, 0.562)),
        ((0.470, 0.507), (0.530, 0.562)),
        ((0.554, 0.507), (0.614, 0.562)),
    )
    # 放完香蕉等几秒面包才出来；加面包之后连按 A 几秒、每次按完等几秒
    top_bread_wait = 0.5
    mash_seconds = 5.0
    mash_gap = 0.2
    # 吃三明治：最多等几秒，回到野餐之后再等几秒
    eat_timeout = 80.0
    eat_settle_wait = 1.0
    # 手：手的框的宽高；下次找手的范围往外扩多少倍、变成几倍（上游 expand_box）
    hand_width = 0.071
    hand_height = 0.106
    hand_expand_margin = 1.5
    hand_expand_scale = 4
    # 找手最多找几秒；找不到时把手往右下推到头再往左推一点，之后在整个画面里找几秒
    hand_look_timeout = 5.0
    hand_recover_route: tuple[tuple[float, float, float], ...] = (
        (1.0, -1.0, 4.0),
        (-1.0, 0.0, 0.8),
    )
    hand_recover_wait = 0.8
    hand_recover_look = 1.0
    # 手每轮推一下的时间和比例：按 16:9 算屏幕上的距离，4 格（宽度的 1/4）以内按距离推、再远满推；推完等几秒
    screen_width_units = 16
    screen_height_units = 9
    hand_gain = 0.25
    hand_push_seconds = 0.16
    hand_move_wait = 0.08
    # 抓着东西移到目标，松开 A 之后等几秒让手把东西放下；一次移动最多几秒
    hand_release_wait = 0.1
    hand_move_timeout = 120.0
    # 手是白色的（BGR 的下限、上限）；模板；找手时白色连通区域至少多大（1080p 的像素数）、比例误差、形状差异
    hand_white = ((150, 150, 150), (255, 255, 255))
    hand_template_free = Path(str(_DATA / "sandwich_hand_free.png"))
    hand_template_grabbing = Path(str(_DATA / "sandwich_hand_grabbing.png"))
    hand_min_area_free = 4000
    hand_min_area_grabbing = 3600
    hand_base_height = 1080
    hand_tolerance = 0.15
    hand_max_mismatch = 0.1
    # 盘子的标签：位置；抓着东西时变黄（BGR 的下限、上限），黄色像素至少多少（1080p 的像素数）
    plate_label_area: Rect = ((0.397, 0.268), (0.600, 0.312))
    plate_label_yellow = ((0, 161, 180), (100, 255, 255))
    plate_yellow_min = 200

    # ---- 篮子 ----
    # 野餐时左边出现 A 按钮的提示（「聊天」）：宝可梦在跟前挡着；白色像素占比超过 a_hint_ratio
    a_hint_area: Rect = ((0.020, 0.590), (0.055, 0.650))
    a_hint_white: tuple[Hsv, Hsv] = ((0, 0, 200), (180, 40, 255))
    a_hint_ratio = 0.05
    # 前面有宝可梦挡着：每隔几秒吹一次口哨，最多吹几次
    whistle_wait = 30.0
    whistle_rounds = 40
    # 查篮子：最多查几秒，每次看画面最多几秒，没有对话框要连着几秒才算，连着几次没有对话框就报错
    basket_check_timeout = 300.0
    basket_look_timeout = 5.0
    basket_none_hold = 0.5
    basket_none_limit = 10
    # 按 A、B 之后等几秒（对话、选择框）；认不出画面时右摇杆往左转视角几秒
    basket_talk_wait = 0.24
    basket_prompt_wait = 0.64
    basket_turn_seconds = 0.24
    # 隔多久查一次篮子（秒，不能超过 180，不然 Switch 会休眠）；等篮子时每隔几秒按一下键防休眠
    basket_interval = 180
    keepalive_button = "L"
    keepalive_gap = 30.0

    # ---- 孵蛋 ----
    # 绕圈最多几秒、每隔几秒看一次；孵出来之后右摇杆往左转几秒；等回到野外最多几秒
    cycle_timeout = 600.0
    cycle_interval = 0.5
    hatch_turn_seconds = 0.76
    hatch_end_timeout = 60.0
    # 重启游戏回档之后，看画面等回到野外最多几秒、回到之后再等几秒（flow.restart 在黑屏时就返回了）
    restart_timeout = 120.0
    restart_settle_wait = 2.0

    # ---- 盒子 ----
    # 读盒子编号、面板上的名字、有没有宝可梦、闪光：连着几帧读到一样的才算（光标刚移过去时面板还没换）
    stable_frames = 3
    # 带队的宝可梦的特性；面板能力页上特性的值、「特性」这个标签的位置（切到评定页时这里是「性格」）
    flame_body = "火焰之躯"
    ability_area: Rect = ((0.76, 0.53), (0.95, 0.585))
    ability_label_area: Rect = ((0.655, 0.53), (0.74, 0.585))
    ability_label = "特性"
    # 盒子第 0 行第 0 列的格子；蛋的模板（从 1080p 截图裁的蛋身中间一块），格子里匹配度超过 egg_score 是蛋
    box_cell: Rect = ((0.234, 0.183), (0.2965, 0.294))
    egg_template = Path(str(_DATA / "box_egg.png"))
    egg_template_height = 1080
    egg_score = 0.9
    # 光标：格子上方的箭头黄绿色那一段是个扁的方块（面积至少多少个 1080p 的像素、宽高比范围），
    # 中心在这个范围里；队伍第 0 行、盒子第 0 行第 0 列的箭头中心；两格之间的间距；横坐标小于 party_limit 是队伍
    # 色相下限比渐变箭头的高一点：1080p 采集卡的画面上，格子的黄色和箭头黄绿色那一段色相接近，低了会连成一块
    cursor_yellow: tuple[Hsv, Hsv] = ((32, 150, 200), (48, 255, 255))
    cursor_min_area = 220
    cursor_aspect = (0.8, 4.5)
    cursor_search: Rect = ((0.10, 0.12), (0.80, 0.80))
    cursor_origin = (0.265, 0.186)
    cell_step = (0.0656, 0.1167)
    party_limit = 0.20
    # 移光标最多按几下
    cursor_max_presses = 30
    # 右边面板：名字栏的黄色（有宝可梦）、名字、闪光的星星、六项能力
    panel_header: Rect = ((0.70, 0.01), (0.99, 0.06))
    panel_header_yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    panel_header_ratio = 0.5
    panel_name_area: Rect = ((0.70, 0.005), (0.86, 0.07))
    shiny_area: Rect = ((0.878, 0.081), (0.906, 0.127))
    shiny_std = 80.0
    panel_stats: tuple[Rect, ...] = (
        ((0.82, 0.195), (0.90, 0.24)),
        ((0.885, 0.305), (0.96, 0.35)),
        ((0.885, 0.405), (0.96, 0.45)),
        ((0.82, 0.47), (0.90, 0.515)),
        ((0.70, 0.405), (0.78, 0.45)),
        ((0.70, 0.305), (0.78, 0.35)),
    )
    # 评定页：六项能力读到判定词的至少 judge_min 项。不是的话按 PLUS 切换，按一下之后最多看几秒，
    # 按了 judge_timeout 秒还切不到说明评定功能没解锁
    judge_words = ("最棒", "了不起", "非常好", "相当好", "一般般", "也许不行")
    judge_min = 4
    judge_timeout = 3.0
    # 队伍里每一格的范围、名字的范围（第 0 行）；格子里内容少于 empty_slot_std 是空格
    party_cell: Rect = ((0.021, 0.185), (0.208, 0.296))
    party_name: Rect = ((0.03, 0.235), (0.17, 0.29))
    empty_slot_std = 20.0
    # 选择模式：底栏中间的按键提示都没有了（白色像素占比低于 bar_ratio）
    bar_area: Rect = ((0.391, 0.939), (0.791, 0.986))
    bar_white: tuple[Hsv, Hsv] = ((0, 0, 200), (180, 40, 255))
    bar_ratio = 0.01
    # 拿着一列移不过去最多重来几次
    column_attempts = 10
    # 放生：盒子里按 A 出来的操作菜单（移动、查看能力、携带持有物、标记、放生、取消）：
    # 找选中行的箭头的范围、箭头黄绿色那一段的宽高比上限、第 0 行的中心、行高、行数、「放生」是第几行
    operation_area: Rect = ((0.20, 0.19), (0.95, 0.53))
    operation_aspect = 0.8
    operation_first_row = 0.222
    operation_step = 0.0556
    operation_rows = 6
    move_row = 0
    release_row = 4
    # 放生确认框里「是」那一行箭头的位置（光标默认在下面的「否」）
    release_yes_area: Rect = ((0.7161, 0.5713), (0.7625, 0.6639))

    # ---- 飞到零区闸口（fly.py） ----
    gate_name = "零区闸口"
    # 地图画面：左上角的标题
    map_title: Rect = ((0.17, 0.12), (0.25, 0.18))
    map_title_text = "地图"
    # 黑屏之后等回到野外最多几秒；回到野外之后再等几秒，人能动了再按键
    fly_timeout = 30.0
