"""一局结束：检查抓到的宝可梦是不是闪光，带走或留下。"""

import logging
import os
import time

from libs import ImageChecker, Switch
from tools import act_until, capture, move_menu_option, press_until, restart, save_check, wait_for


def select_pokemon(sw: Switch) -> str:
    """查闪光，带走或留下，再决定下一局，返回 "initialize"。"""
    if sw.game.num_caught == 0:
        logging.info("一只都没抓到")
        # 一只都没抓到时后面是什么界面还没见过，等 15 秒截一张留着，之后照着改逻辑
        time.sleep(15)
        save_check(sw, capture(sw), "没抓住的界面", sw.config.rects.result_title)
        _back_to_scientist(sw)
        _press_until_thanks_gone(sw)
        return "initialize"
    else:
        shiny = _check_shiny(sw)
        _decide_next_run(sw, shiny)
        return "initialize"


def _check_shiny(sw: Switch) -> int:
    """等带走宝可梦的界面，查闪光，截图后回到列表。返回要带走的那只的序号，没有闪光返回 -1。"""
    wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.result_title, "选1只要带回去的宝可梦"),
        sw.config.timeout,
        "带走宝可梦的界面",
    )
    results = _find_shiny(sw)
    # 从资料页退回带走宝可梦的列表
    act_until(
        sw,
        lambda: sw.click("B", 0),
        lambda screen: screen.has_text(sw.config.rects.result_title, "选1只要带回去的宝可梦"),
        "回到带走宝可梦的界面",
    )
    _save_list_screenshots(sw, results)
    # 有好几只闪光时带走最后一只，也就是排在最后的神兽
    shiny = max((index for index, found in enumerate(results) if found), default=-1)
    return shiny


def _save_list_screenshots(sw: Switch, results: list[bool]) -> None:
    """在带走列表上从第一只往下，把闪光的和最后一只（神兽）的截图存下来。没有闪光也要截神兽。

    资料页查完最后一只还会往下切一次，绕回第一只，所以退回列表时光标在第一只上。
    闪光的那只还要用 Switch 自己截一张。
    """
    rects = sw.config.rects
    last = len(results) - 1
    for index, shiny in enumerate(results):
        if shiny or index == last:
            # 左边的预览要晚一点才画出来，等它出来再截图
            image = wait_for(
                sw,
                lambda screen: (
                    1
                    - screen.color_ratio(
                        rects.result_preview,
                        sw.config.result_preview_lower,
                        sw.config.result_preview_upper,
                    )
                    > sw.config.result_preview_ratio
                ),
                sw.config.timeout,
                "列表左边的宝可梦",
            )
            _save_screenshot(sw, image, "list", shiny)
        _move_list_cursor(sw, index + 1)


def _save_screenshot(sw: Switch, image: ImageChecker, kind: str, shiny: bool) -> None:
    """存一张战果截图：闪光的存进 catch_dir，文件名带 shiny-，Switch 自己也截一张存进相册；
    不是闪光的存进 result_dir。kind 是 summary（资料页）或 list（带走列表）。
    """
    directory = sw.config.catch_dir if shiny else sw.config.result_dir
    directory.mkdir(parents=True, exist_ok=True)
    name = f"shiny-{kind}" if shiny else kind
    path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.jpg"
    image.save(str(path))
    logging.info(f"战果截图: {path}")
    if shiny:
        sw.click("CAPTURE", 0)


def _decide_next_run(sw: Switch, shiny: int) -> None:
    """决定下一局：带走闪光、重启游戏 keep path，或者结束这一局。

    - 有闪光：光标移到那只上，一直按 A 到画面变黑。带走后下一局 seed 不一样，join 会清掉状态。
    - 没有闪光，倒下次数和用时都在范围内：重启游戏，下一局 seed 和 boss 不变就是 keep path。
    - 都不是：一直按 B 到画面变黑。
    """
    sw.game.save()
    if shiny >= 0:
        _take(sw, shiny)
        _press_until_thanks_gone(sw)
    else:
        faints = 4 - sw.game.lives
        minutes: float = (time.time() - sw.game.started) / 60
        logging.info(f"这一局倒下 {faints} 次，用时 {minutes:.1f} 分钟")
        # keep path 要重启游戏，下次和科学家说话要付极矿石，矿石不够时用环境变量关掉
        keep_path = os.environ.get("KEEP_PATH") == "1"
        if (
            keep_path
            and faints <= sw.config.lock_max_faints
            and minutes <= sw.config.lock_max_minutes
        ):
            logging.info("重启游戏，keep path")
            restart(sw)
        else:
            _back_to_scientist(sw)
            _press_until_thanks_gone(sw)


def _take(sw: Switch, index: int) -> None:
    """带走第 index 只：光标移到那只上，一直按 A 到画面变黑。"""
    _move_list_cursor(sw, index)
    logging.info(f"带走了第 {index + 1} 只 {sw.game.caught[index]}")


def _move_list_cursor(sw: Switch, index: int) -> None:
    """把带走列表的光标移到第 index 只（按抓到的顺序，从 0 开始）。"""
    rows = list(sw.config.rects.result_rows[: sw.game.num_caught])
    current = capture(sw).selected(rows)
    # 往上推是 +stick_max，往下推是 -stick_max
    direction = 1 if index < current else -1
    act_until(
        sw,
        lambda: sw.stick("LEFT", 0, direction * sw.config.stick_max, sw.config.stick_tick),
        lambda screen: screen.selected(rows) == index,
        f"列表光标移到第 {index + 1} 只",
    )


def _find_shiny(sw: Switch) -> list[bool]:
    """从第一只开始，按顺序打开资料页查闪光，返回每只是不是闪光。"""
    rects = sw.config.rects
    # 光标在列表第一只上，按 A 弹出菜单，菜单的位置是固定的
    image = act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: screen.has_text(rects.result_view_ability, "查看能力"),
        "「选择 / 查看能力 / 取消」",
    )
    move_menu_option(
        sw,
        image,
        "查看能力",
        lambda: sw.click("DDOWN", 0),
        "战果菜单",
        rects.result_option_menu,
    )
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(rects.result_view_ability, "查看能力"),
        "进资料页",
    )
    # 日志里的名字按抓到的顺序从这一局的记录里取；数据里的中文名可能和游戏里不一样，不拿来比画面
    names = [sw.data.pokemon_object(name_id).name(sw.config.language) for name_id in sw.game.caught]
    results = []
    for index, name in enumerate(names):
        image = wait_for(
            sw,
            lambda screen: bool(screen.read_text(rects.summary_name).strip()),
            sw.config.timeout,
            f"资料页上第 {index + 1} 只（{name}）的名字",
        )
        shown = image.read_text(rects.summary_name).strip()
        shiny = _is_shiny(sw, image)
        if shiny:
            logging.warning(f"闪光！第 {index + 1} 只 {name}")
            # 资料页右边的宝可梦要晚一点才画出来，等它出来再截图
            image = wait_for(
                sw,
                lambda screen: (
                    screen.edge_ratio(rects.summary_sprite) > sw.config.summary_sprite_edge
                ),
                sw.config.timeout,
                "资料页右边的宝可梦",
            )
            _save_screenshot(sw, image, "summary", True)
        else:
            logging.info(f"第 {index + 1} 只「{name}」不是闪光")
        results.append(shiny)
        act_until(
            sw,
            lambda: sw.stick("LEFT", 0, -sw.config.stick_max, sw.config.stick_tick),
            lambda screen, before=shown: (
                screen.read_text(rects.summary_name).strip() not in ("", before)
            ),
            "资料页换到下一只",
        )
    return results


def _back_to_scientist(sw: Switch) -> None:
    """一直按 B，直到出现「不带宝可梦回去了，你确定吗？」的是 / 否；再一直按 A，直到科学家的「辛苦了。」消失。"""
    press_until(
        sw,
        lambda screen: (
            screen.has_text(sw.config.rects.dialog, "不带宝可梦回去")
            and screen.selected(list(sw.config.rects.yes_no)) >= 0
        ),
        "不带走的确认",
        button="B",
    )


def _is_shiny(sw: Switch, image: ImageChecker) -> bool:
    """资料页闪光框里高饱和像素占比在范围内。"""
    value = (
        image.color_ratio(
            sw.config.rects.shiny,
            sw.config.shiny_lower,
            sw.config.shiny_upper,
        )
        * 255
    )
    logging.debug(f"闪光框的占比 {value:.1f}")
    return sw.config.shiny_min < value <= sw.config.shiny_max


def _press_until_thanks_gone(sw: Switch) -> None:
    """一直按 A，先等科学家的「辛苦了。」出来，再按到它消失。

    带走和不带走之后都是：报酬页面 → 转场黑屏 → 回到科学家面前说「辛苦了。」。
    """
    press_until(
        sw,
        lambda screen: screen.has_text(sw.config.rects.dialog, "辛苦了"),
        "科学家的「辛苦了。」",
        timeout=sw.config.timeout * 2,
    )
    press_until(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.dialog, "辛苦了"),
        "「辛苦了。」消失",
    )
