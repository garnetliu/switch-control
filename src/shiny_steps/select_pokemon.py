"""一局结束：检查抓到的宝可梦是不是闪光，带走或留下。"""

import logging
import time
import unicodedata
from pathlib import Path

from libs import ImageChecker, Switch
from tools import act_until, capture, move_menu_option, press_until, restart, save_check, wait_for


def select_pokemon(sw: Switch) -> str:
    """查闪光，带走或留下，再决定下一局，返回 "initialize"。"""
    if sw.game.num_caught == 0:
        _no_catch(sw)
        return "initialize"
    else:
        shiny, values = _check_shiny(sw)
        _decide_next_run(sw, shiny, values)
        return "initialize"


def _no_catch(sw: Switch) -> None:
    """一只都没抓到：截一张后面的界面，算输一局判断锁不锁定，先写战报，再重启或结束这一局。"""
    logging.info("一只都没抓到")
    # 一只都没抓到时后面是什么界面还没见过，等 15 秒截一张留着，之后照着改逻辑
    time.sleep(15)
    save_check(sw, capture(sw), "没抓住的界面", sw.config.rects.result_title)
    keep, lock = sw.game.finish_run(took_shiny=False)
    # 战报先发，后面收尾的按键卡住或出错也不影响
    if keep:
        _report(sw, -1, [], "一只都没抓到，重启游戏保留路线", lock)
        logging.info("重启游戏，keep path")
        restart(sw)
    else:
        _report(sw, -1, [], "一只都没抓到", lock)
        _back_to_scientist(sw)
        _press_until_black(sw)


def _check_shiny(sw: Switch) -> tuple[int, list[float]]:
    """等带走宝可梦的界面，查闪光，截图后回到列表。

    返回 (要带走的那只的序号，没有闪光是 -1；每只闪光框的占比，写进战报)。
    """
    wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.result_title, "选1只要带回去的宝可梦"),
        sw.config.timeout,
        "带走宝可梦的界面",
    )
    values = _find_shiny(sw)
    results = [_is_shiny(sw, value) for value in values]
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
    return shiny, values


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
        if index < last:
            _move_list_cursor(sw, index + 1)


def _save_screenshot(sw: Switch, image: ImageChecker, kind: str, shiny: bool) -> Path:
    """存一张战果截图，返回存下的文件：闪光的存进 catch_dir，文件名带 shiny-，Switch 自己也截一张
    存进相册；不是闪光的存进 result_dir。kind 是 summary（资料页）或 list（带走列表）。
    """
    directory = sw.config.catch_dir if shiny else sw.config.result_dir
    directory.mkdir(parents=True, exist_ok=True)
    name = f"shiny-{kind}" if shiny else kind
    path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.jpg"
    image.save(str(path))
    logging.info(f"战果截图: {path}")
    if shiny:
        sw.click("CAPTURE", 0)
    return path


def _decide_next_run(sw: Switch, shiny: int, values: list[float]) -> None:
    """决定下一局：带走闪光、重启游戏 keep path，或者结束这一局。

    先用 game.finish_run 记下胜负、算锁定还是解锁，再写战报，最后按键收尾；
    战报先发，收尾的按键卡住或出错也不影响。
    - 有闪光：光标移到那只上带走，不锁定。
    - 没有闪光：锁定就重启游戏，下一局还是这张图；不锁定就不带走，结束这一局。
    """
    keep, lock = sw.game.finish_run(took_shiny=shiny >= 0)
    if shiny >= 0:
        _report(sw, shiny, values, f"带走第 {shiny + 1} 只闪光", lock)
        _take(sw, shiny)
        _press_until_black(sw)
    elif keep:
        _report(sw, shiny, values, "不带走，重启游戏保留路线", lock)
        logging.info("重启游戏，keep path")
        restart(sw)
    else:
        _report(sw, shiny, values, "不带走", lock)
        _back_to_scientist(sw)
        _press_until_black(sw)


def _report(sw: Switch, shiny: int, values: list[float], outcome: str, lock: str) -> None:
    """把这一局的战报写进日志并推送，附上这一局存下的战果截图。格式：

    第 N 轮战报：（N 是 lock_results 里记录的局数）
    胜/负，倒下 X 次，Y 分钟，抓到 n/4
    路线：A → B → C
    得分：S，首发 名字（第 k 位）
    逐关：每一关抓到、团灭还是没抓，对手和属性；团灭之后的关卡不写。下面各另起一行，和「抓到」对齐：
    抓到的写是闪光还是非闪、闪光框的占比和阈值；这一关有倒下的写倒下几次
    处理：这一局结束时怎么处理抓到的宝可梦
    锁定：这张图锁定的情况，锁定以来的局数和总胜率、继续锁定还是解锁
    """
    game = sw.game
    language = sw.config.language
    maps = game.maps

    def name(name_id: str) -> str:
        return sw.data.pokemon_object(name_id).name(language)

    def types(name_id: str) -> str:
        return "/".join(t.get(language, "?") for t in sw.data.pokemon_object(name_id).types)

    won = game.num_caught == 4
    minutes: float = (time.time() - game.started) / 60
    lines = [
        f"第 {len(game.lock_results)} 轮战报：",
        f"{'胜' if won else '负'}，倒下 {4 - game.lives} 次，{minutes:.1f} 分钟，抓到 {game.num_caught}/4",
    ]
    nodes: list[str] = []
    if maps is not None and maps["route"]:
        nodes = [maps["rows"][str(row)][col]["encounter"] for row, col in maps["route"][1:-1]]
    starter = "?"
    if game.lock_pokemon_index is not None and game.lock_pokemon_index < len(game.candidates):
        starter = f"{name(game.candidates[game.lock_pokemon_index])}（第 {game.lock_pokemon_index + 1} 位）"
    route = " → ".join(name(node) for node in nodes) or "?"
    lines.append(f"路线：{route}")
    lines.append(f"得分：{game.route_score:.3f}，首发 {starter}")

    lines.append("逐关：")
    stages = []
    opponents: list[str] = [*nodes, game.boss]
    for index, opponent in enumerate(opponents):
        label = "首\u3000领" if index == len(nodes) else f"第{'一二三'[index]}关"
        if index < game.num_caught:
            result = "抓到"
        elif game.lives == 0:
            result = "团灭"
        else:
            result = "没抓"
        result += f" {name(opponent)}（{types(opponent)}）"
        faints = game.faints[index] if index < len(game.faints) else 0
        stages.append((label, result, faints))
        # 团灭之后的关卡没有打，不写
        if result.startswith("团灭"):
            break
    label_width = max(_display_width(label) for label, _, _ in stages) + 1
    for index, (label, result, faints) in enumerate(stages):
        lines.append(f"  {_pad(label, label_width)}{result}")
        # 闪光判定和倒下次数各另起一行，和上一行的「抓到」对齐；values 按抓到的顺序，和关卡一一对应
        if index < len(values):
            kind = "闪光" if _is_shiny(sw, values[index]) else "非闪"
            lines.append(
                f"  {_pad('', label_width)}{kind}（{values[index]:05.2f} / 阈值 {sw.config.shiny_min}）"
            )
        if faints:
            lines.append(f"  {_pad('', label_width)}倒下 {faints} 次")

    lines.append(f"处理：{outcome}")
    lines.append(f"锁定：{lock}")

    report = "\n".join(lines)
    logging.info("\n" + report)
    # 这一局存下的战果截图：开始时间之后存进闪光目录和战果目录的图片
    files = sorted(
        path
        for directory in (sw.config.catch_dir, sw.config.result_dir)
        if directory.exists()
        for path in directory.glob("*.jpg")
        if path.stat().st_mtime >= game.started
    )
    sw.notifier.send("```\n" + report + "\n```", files=files)


def _display_width(text: str) -> int:
    """等宽字体下的显示宽度，中文和全角字符算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _pad(text: str, width: int) -> str:
    """按显示宽度补空格，让等宽字体里的列对齐。"""
    return text + " " * max(0, width - _display_width(text))


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


def _find_shiny(sw: Switch) -> list[float]:
    """从第一只开始，按顺序打开资料页查闪光，返回每只闪光框的占比，用 _is_shiny 判断是不是闪光。"""
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
            lambda screen: bool(_summary_name(sw, screen)),
            sw.config.timeout,
            f"资料页上第 {index + 1} 只（{name}）的名字",
        )
        shown = _summary_name(sw, image)
        value = _shiny_value(image, sw)
        if _is_shiny(sw, value):
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
            path = _save_screenshot(sw, image, "summary", True)
            sw.notifier.send_everyone(f"闪光！第 {index + 1} 只 {name}", files=[path])
        else:
            logging.info(f"第 {index + 1} 只「{name}」不是闪光")
        results.append(value)
        # 只抓到 1 只时翻页名字不会变，会一直等到超时；多只时最后一只还要翻一次绕回第一只
        if len(names) == 1:
            break
        act_until(
            sw,
            lambda: sw.stick("LEFT", 0, -sw.config.stick_max, sw.config.stick_tick),
            lambda screen, before=shown: _summary_name(sw, screen) not in ("", before),
            "资料页换到下一只",
        )
    return results


def _summary_name(sw: Switch, image: ImageChecker) -> str:
    """资料页上的名字。

    区域要贴着名字那一格：区域里空白太多时，两个字的名字（比如「袋兽」）用 read_text 读不出来。
    """
    return image.read_text(sw.config.rects.summary_name)


def _back_to_scientist(sw: Switch) -> None:
    """一直按 B，直到出现「不带宝可梦回去了，你确定吗？」的是 / 否。"""
    press_until(
        sw,
        lambda screen: (
            screen.has_text(sw.config.rects.white_center_line1, "不带宝可梦回去")
            and screen.selected(list(sw.config.rects.yes_no)) >= 0
        ),
        "不带走的确认",
        button="B",
    )


def _shiny_value(image: ImageChecker, sw: Switch) -> float:
    """资料页闪光框里高饱和像素的占比，换算成 0 到 255。"""
    value = (
        image.color_ratio(
            sw.config.rects.shiny,
            sw.config.shiny_lower,
            sw.config.shiny_upper,
        )
        * 255
    )
    logging.debug(f"闪光框的占比 {value:.1f}")
    return value


def _is_shiny(sw: Switch, value: float) -> bool:
    """闪光框的占比在范围内就是闪光。"""
    return sw.config.shiny_min < value <= sw.config.shiny_max


def _press_until_black(sw: Switch) -> None:
    """一直按 A，画面变黑就停。

    带走和不带走之后都是：报酬页面 → 转场黑屏 → 回到科学家面前。黑屏之后科学家说什么不固定
    （打赢了有时还会写下位置记录），这里不再等结束语，后面的对话交给 initialize。
    """
    press_until(sw, lambda screen: screen.is_black(), "转场黑屏", timeout=sw.config.timeout * 2)
