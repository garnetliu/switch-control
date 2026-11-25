"""极巨大冒险测试共用的 fixture：固定了手写名单和打分参数的配置、数据、基准 seed 的 Lair。

GameConfig 里的已抓名单（lair_caught）、第一次抽数的上限和各项打分参数以后会改，
测试里用子类把它们固定成现在的值，期望值就不会跟着配置变。
"""

import importlib
import shutil
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from control_switch.config import WaitConfig
from control_switch.device import Devices
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.lair import Lair
from control_switch.games.swsh.lair.session import LairSession
from control_switch.settings import Settings, build_settings
from control_switch.types import Hsv, Rect
from control_switch.vision import ImageChecker
from control_switch.vision.text import contains

# 超梦基准图的 seed，见 game_config.py 里 boss_faint_half 的注释
SEED = 3076008315599927110


class FixedConfig(GameConfig):
    """已抓名单（还能遇到的神兽 21 只）、第一次抽数的上限、打分和极巨化轮换的参数都固定。"""

    lair_caught = (
        "tapu-fini",
        "xerneas",
        "tapu-koko",
        "solgaleo",
        "mewtwo",
        "tapu-bulu",
        "tornadus-incarnate",
        "tapu-lele",
    )
    # 剑的存档：遇不到盾限定的 8 只
    lair_other_version = GameConfig.lair_version_exclusives["0100ABF008968000"]
    lair_first_draw_top = 20
    dynamax_turns = 3
    dynamax_wait = 3
    dynamax_hp = 1.9
    stage_sure_damage = 1.0
    stage_likely_damage = 0.6
    stage_own_rate = 1.0
    stage_team_rate = 1.4
    stage_base_rate = 0.05
    stage_max_turns = 10
    stage_weak_turns = 1.58
    boss_kill_attack = 1.0
    boss_turn_rate = 0.68
    boss_turns = 3
    boss_max_turns = 10
    boss_faint_half = 0.8
    boss_faint_power = 4
    boss_hurt_scale = 3.0
    boss_hurt_exponent = 3
    stage_weights = (0.3, 0.2, 0.1)
    no_swap_probability = 1 / 8


@pytest.fixture(scope="session")
def fixed_config() -> FixedConfig:
    """固定了名单和参数的配置。"""
    return FixedConfig()


@pytest.fixture(scope="session")
def fixed_data(fixed_config: FixedConfig) -> GameData:
    """用固定了名单的配置读 src/control_switch/games/swsh/data/，只读。"""
    return GameData(fixed_config)


@pytest.fixture
def lair0(fixed_data: GameData) -> Lair:
    """基准 seed，extra 是 0。"""
    return Lair(fixed_data, SEED, 0)


class RecordingNotifier:
    """假 notifier：记下 send 和 send_everyone 的文字和附件，不发消息。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[Path]]] = []
        self.sent_everyone: list[tuple[str, list[Path]]] = []

    def send(self, text: str, files: Sequence[str | Path] | None = None) -> None:
        self.sent.append((text, [Path(path) for path in files or []]))

    def send_everyone(self, text: str, files: Sequence[str | Path] | None = None) -> None:
        self.sent_everyone.append((text, [Path(path) for path in files or []]))


class FakeImage:
    """假截图：用字典说明各个区域上读到的文字、颜色占比、菜单这些，代替真的 ImageChecker。

    没有写到的区域，读到的文字是空字符串，颜色占比是 0，selected 是 -1，找不到菜单。
    颜色占比也可以给一个函数 ratio_fn(区域, 颜色下限)，每次问的时候现算（画面要随着按键变化时用）。
    """

    def __init__(
        self,
        *,
        texts: Mapping[Rect, str] | None = None,
        black: bool = False,
        ratios: Mapping[tuple[Rect, Hsv], float] | None = None,
        ratio_fn: Callable[[Rect, Hsv], float] | None = None,
        selected: int | Mapping[tuple[Rect, ...], int] = -1,
        menu: tuple[Rect, list[tuple[str, Rect]]] | None = None,
        lines: Mapping[Rect, list[tuple[str, Rect]]] | None = None,
        edge: float = 0.0,
    ) -> None:
        self._texts = dict(texts or {})
        self._black = black
        self._ratios = dict(ratios or {})
        self._ratio_fn = ratio_fn
        self._selected = selected
        self._menu = menu
        self._lines = dict(lines or {})
        self._edge = edge
        self.saved: list[str] = []

    def read_text(self, rect: Rect) -> str:
        return self._texts.get(rect, "")

    def has_text(self, rect: Rect, text: str, min_similarity: float = 0.8) -> bool:
        return contains(self.read_text(rect), text, min_similarity)

    def is_black(self) -> bool:
        return self._black

    def color_ratio(self, rect: Rect, lower: Hsv, upper: Hsv) -> float:
        if self._ratio_fn is not None:
            return self._ratio_fn(rect, lower)
        return self._ratios.get((rect, lower), 0.0)

    def selected(self, rects: Sequence[Rect]) -> int:
        if isinstance(self._selected, int):
            return self._selected
        return self._selected.get(tuple(rects), -1)

    def find_menu(self, area: Rect) -> tuple[Rect, list[tuple[str, Rect]]] | None:
        return self._menu

    def text_lines(self, rect: Rect) -> list[tuple[str, Rect]]:
        return self._lines.get(rect, [])

    def edge_ratio(self, rect: Rect) -> float:
        return self._edge

    def save(self, path: str) -> None:
        self.saved.append(path)
        Path(path).write_bytes(b"fake image")


class FakeImages:
    """假截图的登记处：每张假截图换成一串独一无二的字节，放进假 Screen 里；
    flow.wait 里创建 ImageChecker 的地方换成按这串字节找回假截图，不认识的字节（真截图）照常用真的 ImageChecker。
    """

    def __init__(self) -> None:
        self._images: dict[bytes, FakeImage] = {}

    def add(self, **kwargs: Any) -> bytes:
        """登记一张假截图，返回它在假 Screen 里的字节。参数同 FakeImage。"""
        token = f"fake-image-{len(self._images)}".encode()
        self._images[token] = FakeImage(**kwargs)
        return token

    def checker(self, data: bytes) -> Any:
        """代替 ImageChecker(data)。"""
        image = self._images.get(data)
        return image if image is not None else ImageChecker(data)

    def image(self, token: bytes) -> FakeImage:
        """按字节取回登记过的假截图。"""
        return self._images[token]


@pytest.fixture
def fake_images(monkeypatch: pytest.MonkeyPatch) -> FakeImages:
    """假截图的登记处，flow.wait 里的 ImageChecker 已经换成按它找回假截图。"""
    images = FakeImages()
    wait_module = importlib.import_module("control_switch.flow.wait")
    monkeypatch.setattr(wait_module, "ImageChecker", images.checker)
    return images


@pytest.fixture
def lair_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """GameConfig 的数据目录、运行状态、日志、战果和闪光截图目录都指到临时目录，计时设成最短。

    data_dir 是把仓库里的 src/control_switch/games/swsh/data 复制过去的，path 步骤会写 lair_event_LUT.json，不能写仓库里的。
    名单、打分参数固定成 FixedConfig 里的值，首领是 tapu-lele。
    要在创建 LairSession 之前用，所以要用 LairSession 的测试都要用到它。
    """
    root = tmp_path / "lair"
    data_dir = root / "data" / "swsh"
    shutil.copytree(GameConfig.data_dir, data_dir)
    for name, value in vars(FixedConfig).items():
        if not name.startswith("__"):
            monkeypatch.setattr(GameConfig, name, value)
    monkeypatch.setattr(GameConfig, "boss", "tapu-lele")
    monkeypatch.setattr(GameConfig, "data_dir", data_dir)
    monkeypatch.setattr(GameConfig, "game_state_file", root / "runs" / "state" / "game.yaml")
    log_dir = root / "runs" / "logs" / "swsh-lair"
    monkeypatch.setattr(GameConfig, "log_dir", log_dir)
    monkeypatch.setattr(GameConfig, "result_dir", log_dir / "results")
    monkeypatch.setattr(GameConfig, "shiny_dir", root / "runs" / "shinys")
    # 不要比 1 秒短：第一次建 ImageChecker 要初始化 OCR
    monkeypatch.setattr(WaitConfig, "timeout", 1.0)
    monkeypatch.setattr(WaitConfig, "interval", 0.0)
    monkeypatch.setattr(WaitConfig, "press_interval", 0.0)
    yield root


@pytest.fixture
def make_lair_session(
    lair_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_screen: Callable[..., Any],
    controller: Any,
    make_memory: Callable[..., Any],
) -> Callable[..., LairSession]:
    """返回一个函数：用假设备建 LairSession，notifier 换成 RecordingNotifier。

    参数：images 是假 Screen 依次给的图片字节（不给就是一张空白）；title_id、data（地址对应的字节）、
    pointers 给假 Memory；settings 不给就是 build_settings({})；keep_path 设到 GameConfig.keep_path，不给是 False。假 Controller 就是 controller 这个 fixture；假 Screen 和假 Memory
    可以通过 session.screen、session.memory 取到。
    """

    def factory(
        images: Sequence[bytes] = (b"blank",),
        *,
        title_id: str | None = None,
        data: Mapping[int, bytes] | None = None,
        pointers: Mapping[tuple[int, ...], int] | None = None,
        settings: Settings | None = None,
        keep_path: bool = False,
    ) -> LairSession:
        monkeypatch.setattr(GameConfig, "keep_path", keep_path)
        memory = (
            make_memory(data=data, pointers=pointers)
            if title_id is None
            else make_memory(title_id, data, pointers)
        )
        devices = Devices(make_screen(images), controller, memory)
        session = LairSession(settings or build_settings({}), devices)
        monkeypatch.setattr(session, "notifier", RecordingNotifier())
        return session

    return factory
