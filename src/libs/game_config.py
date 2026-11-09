"""新代码的配置：路径、计时、界面区域、游戏参数。"""

from pathlib import Path
from typing import ClassVar, cast

from type import Hsv, Rect

ROOT = Path(__file__).resolve().parents[2]


class Addresses:
    """游戏内存地址。"""

    # 当前冒险 seed，8 字节
    seed = 0x4514A4B0
    # 目标首领 PK8 指针链：main+... → ...
    boss_pointer = (0x26365B8, 0x68, 0x78, 0x88, 0xD08, 0x950, 0xD0)
    # 租借候选 1–3，各 0x158 字节
    starter_candidates = (0x83E93070, 0x83E93300, 0x83E93590)
    # 队伍 P1–P4，各 0x158 字节；P1 是自己
    party = (0x886B67C8, 0x886BC348, 0x886B9588, 0x886BF108)
    # 当前对手，0x158 字节
    opponent = 0x886A95B8
    # LairSpeciesNote 1–4，每项开头 2 字节是 species
    lair_notes = (0x50B12278, 0x50B122B0, 0x50B122E8, 0x50B12320)
    # 冒险界面状态
    interface = 0x16E498
    # 冒险辅助界面状态（main）
    aux_interface = 0x2955BA0
    # 招式数据，下一条 +0xC
    moves = 0x840A5B10
    # 团体战大厅
    raid_lobby = 0xAF285118
    # 团体战房主所选宝可梦 species；形态 +0x4、性别 +0x8、闪光 +0xC、锁定 +0x1C
    raid_owner_species = 0x8398A294
    # 团体战首领
    raid_boss = 0x8398A25C
    # 战斗状态（剑）：0 不在战斗，0x40/0x41 在战斗
    battle_state_sword = 0x3F128624
    # 战斗状态（盾）
    battle_state_shield = 0x3F128626


class Rects:
    """画面上的坐标范围。"""

    # 画面下方白色对话框的第一行
    dialog: Rect = ((0.20, 0.815), (0.83, 0.888))
    # 找对话菜单时的搜索范围，比菜单大一圈
    menu_search: Rect = ((0.60, 0.45), (0.90, 0.79))
    # 极巨大冒险大厅右下角的菜单
    lobby_menu: Rect = ((0.6, 0.65), (0.98, 0.92))
    # 选初始宝可梦界面左上角的「按顺序选择」
    starter_hint: Rect = ((0.015, 0.068), (0.14, 0.122))
    # 选初始宝可梦界面右侧三个候选的名字区域，选中的是黑底
    starter_candidates: tuple[Rect, Rect, Rect] = (
        ((0.485, 0.150), (0.665, 0.385)),
        ((0.485, 0.395), (0.665, 0.645)),
        ((0.485, 0.655), (0.665, 0.907)),
    )
    # 路线图第 2 层的四列，覆盖镜头上下移动时属性标签可能出现的高度
    path_second_row: tuple[Rect, Rect, Rect, Rect] = (
        ((0.14, 0.24), (0.32, 0.92)),
        ((0.38, 0.24), (0.55, 0.92)),
        ((0.61, 0.24), (0.78, 0.92)),
        ((0.84, 0.24), (1.0, 0.92)),
    )
    # 路线图下方「要走哪条路？」的文字
    den_text: Rect = ((0.27, 0.80), (0.72, 0.92))
    # 岔路口每个节点的光标区域，按地图类型分开：{地图类型: {层号: (第 0 列, ...)}}
    # 三种地图先分开写，坐标等真机截图量出来再补
    _EMPTY_CURSORS: ClassVar[tuple[Rect, ...]] = cast(tuple[Rect, ...], ())
    path_cursors: ClassVar[dict[str, dict[int, tuple[Rect, ...]]]] = {
        "2x3": {1: _EMPTY_CURSORS, 2: _EMPTY_CURSORS, 3: _EMPTY_CURSORS},
        "3x2": {1: _EMPTY_CURSORS, 2: _EMPTY_CURSORS, 3: _EMPTY_CURSORS},
        "2x2": {1: _EMPTY_CURSORS, 2: _EMPTY_CURSORS, 3: _EMPTY_CURSORS},
    }


class GameConfig:
    """新代码的配置。"""

    # 要找的传说宝可梦，数据文件里的 name_id
    boss = "solgaleo"
    # 数据文件和图片资源
    data_dir = ROOT / "data"
    # 运行状态快照：YAML 文件 run/game.yaml
    game_state_file = ROOT / "run" / "game.yaml"
    # 游戏的语言，对应数据文件里 names 的键
    language = "zh-Hans"
    # 游戏内存地址
    addresses = Addresses()
    # 画面上的坐标范围
    rects = Rects()
    # 日志和出错时的截图
    log_dir = ROOT / "logs"
    # 路线图第 2 层四个标签的纵向间距对应的地图类型
    path_types: ClassVar[dict[int, str]] = {135: "2x2", 180: "2x3", 65: "3x2"}
    # 属性图标匹配：白色范围、最低匹配度、同一层允许的最大高度差（占画面高度的比例）
    label_icon_lower: Hsv = (0, 0, 200)
    label_icon_upper: Hsv = (180, 50, 255)
    label_icon_score = 0.80
    row_max_spread = 0.2
    # 岔路口光标是白色，白色占比超过这个值才算选中
    cursor_white_lower: Hsv = (0, 0, 220)
    cursor_white_upper: Hsv = (180, 40, 255)
    cursor_white_ratio = 0.02
    # 摇杆坐标最大值和推一格保持的时间
    stick_max = 0x7FFF
    stick_tick = 0.08
    # 等画面变化和操作超时
    timeout = 60.0
    # 两次截图之间的间隔
    interval = 0.3
