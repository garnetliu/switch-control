"""一局结束：检查抓到的宝可梦是不是闪光，带走或留下。"""

import logging
import time
import unicodedata
from pathlib import Path

from control_switch.flow import act_until, capture, move_menu_option, press_until, restart, wait_for
from control_switch.games.swsh.lair.session import LairSession
from control_switch.vision import ImageChecker


def select_pokemon(sw: LairSession) -> str:
    """查闪光，带走或留下，再决定下一局，返回 "initialize"。"""
    if sw.game.num_caught == 0:
        _no_catch(sw)
        return "initialize"
    else:
        shinies, values = _check_shiny(sw)
        _decide_next_run(sw, shinies, values)
        return "initialize"


def _no_catch(sw: LairSession) -> None:
    """一只都没抓到：打完直接回到科学家面前。算输一局判断锁不锁定，先写战报，锁定就重启，不锁定交给 initialize。"""
    logging.info("一只都没抓到")
    keep, lock = sw.game.finish_run([])
    # 战报先发，后面收尾的按键卡住或出错也不影响
    _report(sw, [], [], keep, lock)
    if keep:
        logging.info("重启游戏，keep path")
        restart(sw)


def _check_shiny(sw: LairSession) -> tuple[list[int], list[float]]:
    """等带走宝可梦的界面，查闪光，截图后回到列表。

    返回 (闪光的那几只的序号，没有闪光是空列表；每只闪光框的占比，写进战报)。
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
    return [index for index, shiny in enumerate(results) if shiny], values


def _save_list_screenshots(sw: LairSession, results: list[bool]) -> None:
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


def _save_screenshot(sw: LairSession, image: ImageChecker, kind: str, shiny: bool) -> Path:
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


def _decide_next_run(sw: LairSession, shinies: list[int], values: list[float]) -> None:
    """决定下一局：带走闪光、重启游戏 keep path，或者结束这一局。

    先用 game.finish_run 记下胜负、算锁定还是解锁，再写战报，最后按键收尾；
    战报先发，收尾的按键卡住或出错也不影响。
    - 有闪光：交给 _take，一只就带走，不止一只停下来等人选；不锁定。
    - 没有闪光：锁定就重启游戏，下一局还是这张图；不锁定就不带走，结束这一局。
    """
    keep, lock = sw.game.finish_run(shinies)
    _report(sw, shinies, values, keep, lock)
    if shinies:
        _take(sw, shinies)
        _press_until_black(sw)
    elif keep:
        logging.info("重启游戏，keep path")
        restart(sw)
    else:
        _back_to_scientist(sw)
        _press_until_black(sw)


def _report(
    sw: LairSession, shinies: list[int], values: list[float], keep: bool, lock: str
) -> None:
    """把这一局的战报写进日志并推送，附上这一局存下的战果截图。

    shinies 是闪光的那几只的序号，values 是每只闪光框的占比，keep 是要不要重启游戏保留路线，
    lock 是 game.finish_run 返回的锁定情况。格式：

    第 N 轮战报：（N 是 lock_results 里记录的局数）
    胜/负，倒下 X 次，Y 分钟，抓到 n/4；输了但还有命的是超回合，写成「负（超回合）」
    路线：A → B → C
    得分：S（自己 a + 队友 b），首发 名字（第 k 位）；旧版本锁定的图没有括号里的两项
    逐关：每一关抓到、团灭还是超回合，对手和属性；输掉的那一关之后的关卡不写。
    下面各另起一行，和「抓到」对齐：
    抓到的写是闪光还是非闪、闪光框的占比和阈值；这一关有倒下的写倒下几次
    处理：这一局结束时怎么处理抓到的宝可梦。一只闪光带走；不止一只停下来等人选；
    没有闪光不带走，一只都没抓到另外写明；要重启游戏保留路线的在后面加一句
    锁定：这张图锁定的情况，锁定以来的局数和总胜率、继续锁定还是解锁
    剩余：这时从内存读到的极矿石和抓宝可梦用的球的数量
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
    # 输了但命没扣完：回合用完还没打倒对手，被风刮出巢穴
    overtime = not won and game.lives > 0
    verdict = "胜" if won else "负（超回合）" if overtime else "负"
    lines = [
        f"第 {len(game.lock_results)} 轮战报：",
        f"{verdict}，倒下 {4 - game.lives} 次，{minutes:.1f} 分钟，抓到 {game.num_caught}/4",
    ]
    nodes: list[str] = []
    if maps is not None and maps["route"]:
        nodes = [maps["rows"][str(row)][col]["encounter"] for row, col in maps["route"][1:-1]]
    starter = "?"
    if game.lock_pokemon_index is not None and game.lock_pokemon_index < len(game.candidates):
        starter = f"{name(game.candidates[game.lock_pokemon_index])}（第 {game.lock_pokemon_index + 1} 位）"
    route = " → ".join(name(node) for node in nodes) or "?"
    lines.append(f"路线：{route}")
    score = f"{game.route_score:.3f}"
    if game.stage_score:
        score += f"（三关 {game.stage_score:.3f}，首领 {game.boss_score:.3f}）"
    lines.append(f"得分：{score}，首发 {starter}")

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
            result = "超回合"
        result += f" {name(opponent)}（{types(opponent)}）"
        faints = game.faints[index] if index < len(game.faints) else 0
        stages.append((label, result, faints))
        # 输掉的那一关之后的关卡没有打，不写
        if index >= game.num_caught:
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

    numbers = "、".join(str(index + 1) for index in shinies)
    if len(shinies) == 1:
        outcome = f"带走第 {numbers} 只闪光"
    elif shinies:
        outcome = f"有 {len(shinies)} 只闪光（第 {numbers} 只），停下来等人选"
    else:
        outcome = "不带走" if game.num_caught else "一只都没抓到"
        if keep:
            outcome += "，重启游戏保留路线"
    lines.append(f"处理：{outcome}")
    lines.append(f"锁定：{lock}")
    left = [f"极矿石 {sw.ore_count()} 个"]
    left += [f"{ball} {count} 个" for ball, count in sw.ball_counts().items()]
    lines.append(f"剩余：{'，'.join(left)}")

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


def _take(sw: LairSession, shinies: list[int]) -> None:
    """带走闪光：只有一只就把光标移到那只上，一直按 A 到画面变黑。

    一局只能带走一只：闪光不止一只时程序不替人选，发 @全体 的通知后退出程序（SystemExit），
    游戏留在带走宝可梦的列表上。这时战报已经发了，胜负也记了。
    """
    if len(shinies) > 1:
        numbers = "、".join(str(index + 1) for index in shinies)
        text = f"这一局有 {len(shinies)} 只闪光（第 {numbers} 只），程序停在带走宝可梦的列表上，等你来选"
        logging.warning(text)
        sw.notifier.send_everyone(text)
        # 不是出错：直接退出，入口不会把它当成程序出错来存截图和发通知
        raise SystemExit(text)
    index = shinies[0]
    _move_list_cursor(sw, index)
    logging.info(f"带走了第 {index + 1} 只 {sw.game.caught[index]}")


def _move_list_cursor(sw: LairSession, index: int) -> None:
    """把带走列表的光标移到第 index 只（按抓到的顺序，从 0 开始）。"""
    rows = list(sw.config.rects.result_rows[: sw.game.num_caught])
    current = capture(sw, "带走列表的光标").selected(rows)
    # 往上推是 +stick_max，往下推是 -stick_max
    direction = 1 if index < current else -1
    act_until(
        sw,
        lambda: sw.stick("LEFT", 0, direction * sw.config.stick_max, sw.config.stick_tick),
        lambda screen: screen.selected(rows) == index,
        f"列表光标移到第 {index + 1} 只",
    )


def _find_shiny(sw: LairSession) -> list[float]:
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


def _summary_name(sw: LairSession, image: ImageChecker) -> str:
    """资料页上的名字。

    区域要贴着名字那一格：区域里空白太多时，两个字的名字（比如「袋兽」）用 read_text 读不出来。
    """
    return image.read_text(sw.config.rects.summary_name)


def _back_to_scientist(sw: LairSession) -> None:
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


def _shiny_value(image: ImageChecker, sw: LairSession) -> float:
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


def _is_shiny(sw: LairSession, value: float) -> bool:
    """闪光框的占比在范围内就是闪光。"""
    return sw.config.shiny_min < value <= sw.config.shiny_max


def _press_until_black(sw: LairSession) -> None:
    """一直按 A，画面变黑就停。

    带走和不带走之后都是：报酬页面 → 转场黑屏 → 回到科学家面前。黑屏之后科学家说什么不固定
    （打赢了有时还会写下位置记录），这里不再等结束语，后面的对话交给 initialize。
    """
    press_until(sw, lambda screen: screen.is_black(), "转场黑屏", timeout=sw.config.timeout * 2)
