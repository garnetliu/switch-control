"""菜单光标：找到目标选项，把光标移过去。"""

from collections.abc import Callable, Sequence

from config.timing import POLL_INTERVAL
from lib.log import log
from tool.check_image import ImageChecker
from tool.image import text_lines
from tool.text import levenshtein
from tool.wait import act_until
from typedefs.image import Rect


def move_to(
    image: ImageChecker,
    target: int | str,
    move: Callable[[], None],
    what: str,
    *,
    options: Sequence[Rect] | None = None,
    area: Rect | None = None,
    selected: Callable[[ImageChecker], int] | None = None,
    interval: float = POLL_INTERVAL,
) -> int:
    """找到目标选项，把光标移过去，返回选中项的下标。

    image: 当前截图。
    target: 第几项（从 0 开始）；传文字时按编辑距离和选项的文字比。
    move: 往目标方向移一格，按方向键或推摇杆。
    what: 是什么菜单，写进日志和报错里。
    options: 固定位置的选项，按顺序；用 area 从画面读选项时不用给。
    area: 选项所在的区域，给了就先从这里读出选项的文字和位置。
    selected: 从截图认出光标在第几项，认不出返回 -1。默认按深色底认（ImageChecker.selected）。
    interval: 移一格之后最多等几秒看光标有没有动，没动就再移一次（游戏会吞操作）。
    """
    texts = None
    if area is not None:
        lines = text_lines(image, area)
        if not lines:
            raise RuntimeError(f"{what}里读不到任何选项")
        options = [rect for _, rect in lines]
        texts = [text for text, _ in lines]
    if options is None:
        raise ValueError(f"{what}没有给选项的位置")
    rects = options

    label = None
    if isinstance(target, str):
        if texts is None:
            raise ValueError(f"{what}按文字找选项时没有给选项的文字")
        index = next(
            (i for i, text in enumerate(texts) if levenshtein(text, target) <= len(target) / 3),
            None,
        )
        if index is None:
            raise RuntimeError(f"{what}里找不到「{target}」，读到的选项: {list(texts)}")
        label = texts[index]
    else:
        index = target

    def current(screen: ImageChecker) -> int:
        if selected is not None:
            return selected(screen)
        return screen.selected(list(rects))

    for _ in range(len(rects)):
        found = current(image)
        if found == index:
            if label is not None:
                log(f"{what}选中了「{label}」")
            return index
        image = act_until(
            move,
            lambda screen, before=found: current(screen) not in (before, -1),
            f"{what}的光标移一格",
            interval=interval,
        )
    raise RuntimeError(f"{what}的光标移了 {len(rects)} 次，还是没到第 {index + 1} 项")
