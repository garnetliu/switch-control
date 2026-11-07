import time
import unicodedata
from time import sleep

from config.game import (
    BASE_BALL,
    LEGENDARY_BALL,
    LOCK_EARLY_FAILS,
    LOCK_MAX_FAINTS,
    LOCK_MAX_MINUTES,
    LOCK_MIN_WIN_RATE,
    LOCK_WINDOW_ROUNDS,
    RECORD_LOCATION,
)
from config.layout import (
    DIALOG_RECT,
    RESULT_MENU_RECT,
    RESULT_PREVIEW_RECT,
    RESULT_ROW_RECTS,
    RESULT_TITLE_RECT,
    SHINY_RECT,
    SUMMARY_NAME_LABEL_RECT,
    SUMMARY_NAME_RECT,
    SUMMARY_SPRITE_RECT,
    YES_NO_RECTS,
)
from config.paths import CATCH_DIR
from config.timing import DEFAULT_TIMEOUT, LOAD_TIMEOUT, TICK_SECONDS
from lib import data, run, switch
from lib.dialog import advance_until, press_until
from lib.game import restart
from lib.log import log, take_warnings
from lib.notify import send
from lib.wait import act_until, capture, wait_for
from tool.check_image import ImageChecker
from tool.image import save, small_difference, text_lines

# 带走界面的标题
RESULT_TEXT = "选1只要带回去的宝可梦"
# 列表左侧预览和初始画面的差别（缩小到 16×16 后的灰度差）：同一只的动画 1.4 以下，
# 宝可梦画出来或者换成另一只 5 以上。不要用原尺寸逐像素差：预览里的宝可梦在动，差值和空背景差不多
PREVIEW_MIN_DIFF = 3
# 资料页闪光框里高饱和像素的占比（0 到 255）超过 SHINY_MIN 就是闪光；超过 SHINY_MAX 说明画面不是资料页
SHINY_MIN, SHINY_MAX = 10, 100
# 列表上按 B 之后的确认「不带宝可梦回去了，你确定吗？」（真机实测）
LEAVE_TEXT = "不带宝可梦回去"
# 结算对话里科学家说的「辛苦了。」，之后才问要不要保留位置记录或者结束对话（真机实测）
THANKS_TEXT = "辛苦了"
# 打赢之后科学家问「您需要我为您保留×××所在位置的记录吗？」（真机实测），关键词取第一行的
RECORD_TEXT = "为您保留"


def select_pokemon() -> str | None:
    """一局结束：一只只查抓到的宝可梦是不是闪光，有闪光就带走，然后按 keep path 收尾。照搬上游。

    开始时游戏在 catch 或 battle 结束之后。使用全局连接，需要先调用 switch.connect。
    要不要 keep path 在这里按这一局的结果决定，见 _update_keep_path。
    - 一只都没抓到：keep path 重启游戏，否则回到科学家面前。
    - 有闪光：带走，回到科学家面前继续刷。
    - 没有闪光：keep path 重启游戏；否则不带走，打赢了按配置记录位置。
    返回 "join" 接着刷；球不够下一局、或者要等人决定记不记录位置时返回 None，脚本停下。
    """
    current = run.get()
    if current.num_caught == 0:
        log("一只都没抓到")
        if _update_keep_path():
            _report()
            _restart_same_seed()
            return "join"
        _report()
        run.save()
        return "join" if _back_to_scientist() else None

    wait_for(lambda screen: screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT), 60, "带走宝可梦的界面")
    shiny = _find_shiny()
    if shiny is not None:
        _take(shiny)
        # 带走了，这张图就打完了，下一局是新的图
        current.keep_path = False
    elif _update_keep_path():
        _report()
        _restart_same_seed()
        return "join"
    else:
        _leave()
    _report()
    if shiny == 3:
        # 闪光的神兽带走了，这只刷完了，清掉所有状态
        log("带走了闪光的神兽，清掉所有状态")
        run.clear()
    else:
        run.save()
    if not _back_to_scientist():
        return None

    # 下一局要 3 个普通球和 1 个首领球，两种是同一种球时要 4 个
    balls = current.balls
    enough = (
        balls.get(BASE_BALL, 4) >= 4
        if BASE_BALL == LEGENDARY_BALL
        else balls.get(BASE_BALL, 3) >= 3 and balls.get(LEGENDARY_BALL, 1) >= 1
    )
    if not enough:
        log(f"球不够下一局了: {balls}", "WARNING")
        return None
    return "join"


def _report() -> None:
    """把这一局的战报写进日志，格式是固定的：

    第 N 轮（本次启动）战报：胜/负，倒下 X 次，Y 分钟，抓到 n/4
    路线：A → B → C（得分 S），首发 英文名（第 k 位）
    逐关：每一关的对手、抓到的；首领抓到还是团灭、这一关倒下几次
    闪光（逐只）：中文名 非闪光（峰值 / 阈值）
    锁定、异常（这一局记过的警告）
    """
    current = run.get()
    names = data.type_names()
    won = current.num_caught == 4
    minutes = (time.time() - current.started) / 60
    route = [node.name for node in current.target_path[1:-1]]
    score = f"（得分 {current.path_score:.3f}）" if current.path_score is not None else ""
    starter = current.start_members[0]["name_id"] if current.start_members else "?"
    selection = current.selection + 1 if current.selection is not None else "?"
    lines = [
        (
            f"第 {current.round} 轮（本次启动）战报：{'胜' if won else '负'}，"
            f"倒下 {4 - current.lives} 次，{minutes:.1f} 分钟，抓到 {current.num_caught}/4"
        ),
        f"路线：{' → '.join(names.get(t, t) for t in route)}{score}，首发 {starter}（第 {selection} 位）",
        "逐关：",
    ]
    stages = []
    for index in range(1, len(current.target_path)):
        opponent = current.opponents.get(index)
        battle = index - 1
        if index == len(current.target_path) - 1:
            label = "首领"
            kind = f"{current.boss}（{_type_names(current.boss)}）"
        else:
            label = f"第{index}关"
            node_type = names.get(current.target_path[index].name, "?")
            kind = f"{opponent or '?'}（{_type_names(opponent, node_type)}）"
        if battle < current.num_caught:
            caught = current.caught[battle]
            pokemon = data.boss_pokemon().get(caught) or data.rental_pokemon().get(caught)
            result = f"抓到 {pokemon.name() if pokemon else caught}"
        elif index in current.battle_faints:
            result = "团灭"
        else:
            result = "没打到"
        faints = current.battle_faints.get(index)
        if faints:
            result += f"，倒下 {faints} 次"
        stages.append((label, kind, result))
    label_width = max(_display_width(label) for label, _, _ in stages) + 2
    kind_width = max(_display_width(kind) for _, kind, _ in stages) + 2
    for label, kind, result in stages:
        lines.append(f"  {_pad(label, label_width)}{_pad(kind, kind_width)}{result}")
    lines.append("闪光（逐只）：")
    if current.shiny_peaks:
        name_width = max(_display_width(name) for name, _ in current.shiny_peaks) + 2
        for name, peak in current.shiny_peaks:
            status = "闪光" if SHINY_MIN < peak <= SHINY_MAX else "非闪光"
            lines.append(f"  {_pad(name, name_width)}{status}（{peak:.1f} / {SHINY_MIN}）")
    else:
        lines.append("  没有查")
    if current.plan is not None:
        recent = current.lock_results[-LOCK_WINDOW_ROUNDS:]
        rate = recent.count(True) / len(recent) * 100 if recent else 0
        lock = (
            f"keep path 局，{len(current.lock_results)} 局，最近 {len(recent)} 局胜率 {rate:.0f}%，"
            f"{'继续锁定' if current.keep_path else '已解锁'}"
        )
    else:
        lock = "锁定这张图（之后 keep path）" if current.keep_path else "不锁定"
    lines.append(f"锁定：{lock}")
    warnings = take_warnings()
    lines.append(f"异常：{'；'.join(warnings) if warnings else '无'}")
    report = "\n".join(lines)
    log("\n" + report)
    send("```\n" + report + "\n```", files=current.screenshots)


def _display_width(text: str) -> int:
    """等宽字体下的显示宽度，中文和全角字符算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _pad(text: str, width: int) -> str:
    """按显示宽度补空格，让等宽字体里的列对齐。"""
    return text + " " * max(0, width - _display_width(text))


def _type_names(name_id: str | None, fallback: str = "?") -> str:
    """宝可梦的属性，双属性用 / 连起来；查不到用 fallback。"""
    if not name_id:
        return fallback
    pokemon = data.boss_pokemon().get(name_id) or data.rental_pokemon().get(name_id)
    if pokemon is None:
        return fallback
    names = data.type_names()
    return "/".join(names.get(type_id, type_id) for type_id in pokemon.type_ids)


def _find_shiny() -> int | None:
    """打开资料页，从最后抓到的那只（打赢了就是首领）开始一只只往前查闪光，
    返回第一只闪光在列表上的位置（从 0 开始，和抓到的顺序一致），都不是返回 None。

    列表上光标在第一只，往上推一下绕到最后一只；按 A 弹出「选择 / 查看能力 / 取消」，
    往下推一下到「查看能力」再按 A 进资料页；资料页上往上推一下就是前一只（真机实测）。
    """
    current = run.get()
    sw = switch.get()
    last = current.num_caught - 1
    rows = list(RESULT_ROW_RECTS[: last + 1])
    reference = capture()
    # 推摇杆移光标：列表刚出来时会被吞掉（真机上光标没动、超时过），没反应就再推一次。
    # 按 A 不能重按：菜单要 1.3 秒才出来，选中项还会闪（认出来和认不出来一帧一帧交替），
    # 重按过一次，第二下 A 直接在菜单上点了「选择」，差点把不是闪光的首领带走（真机上发生过）
    if reference.selected(rows) != last:
        act_until(
            lambda: sw.stick("LEFT", 0, switch.STICK_MAX, TICK_SECONDS),
            lambda screen: screen.selected(rows) == last,
            "列表光标移到最后一只",
            interval=2.0,
        )
        image = wait_for(
            lambda screen: (
                screen.selected(rows) == last
                and _preview_shown(screen)
                and small_difference(reference, screen, RESULT_PREVIEW_RECT) >= PREVIEW_MIN_DIFF
            ),
            DEFAULT_TIMEOUT,
            "最后一只的左侧预览",
        )
    else:
        # 光标本来就在最后一只上（上一只也停在这里），预览不用等
        image = reference
    _save_screenshot(image, "list")
    sw.click("A", 0)
    wait_for(lambda screen: _menu_selected(screen) == 0, DEFAULT_TIMEOUT, "选择 / 查看能力 / 取消")
    act_until(
        lambda: sw.stick("LEFT", 0, -switch.STICK_MAX, TICK_SECONDS),
        lambda screen: _menu_selected(screen) == 1,
        "光标移到「查看能力」",
        interval=2.0,
    )
    sw.click("A", 0)
    # 资料页上左边的文字先出来，右边的宝可梦要晚一点才画出来（真机上截到过空的），等它出来再截图、查闪光
    image = wait_for(
        lambda screen: screen.has_text(SUMMARY_NAME_LABEL_RECT, "名字") and _sprite_shown(screen),
        LOAD_TIMEOUT,
        "资料页和上面的宝可梦",
    )

    for index in range(last, -1, -1):
        name = image.read_text(SUMMARY_NAME_RECT).strip()
        if index == last:
            sleep(0.2)
            _save_screenshot(image, "summary")
        if _is_shiny(name):
            log(
                f"闪光！第 {index + 1} 只 {current.caught[index]}（资料页上是「{name}」）",
                "WARNING",
            )
            return index
        log(f"第 {index + 1} 只「{name}」不是闪光")
        if index > 0:
            # 名字一换就算推成功了，不等宝可梦画出来，免得等的时候又推一次跳过一只
            act_until(
                lambda: sw.stick("LEFT", 0, switch.STICK_MAX, TICK_SECONDS),
                lambda screen, before=name: (
                    screen.read_text(SUMMARY_NAME_RECT).strip() not in ("", before)
                ),
                "资料页换到前一只",
                interval=2.0,
            )
            image = wait_for(_sprite_shown, DEFAULT_TIMEOUT, "资料页上的宝可梦")
    return None


def _sprite_shown(screen: ImageChecker) -> bool:
    """资料页右边的宝可梦画出来了：区域里 Canny 边缘的占比超过 0.002。

    宝可梦没出来时是白色圆和浅青色渐变，边缘是 0（真机实测）；画出来之后 0.01 左右。
    不要按颜色判断：白色的宝可梦（托戈德玛尔）会被当成空白，等 10 秒超时。
    """
    return screen.edge_ratio(SUMMARY_SPRITE_RECT) > 0.002


def _preview_shown(screen: ImageChecker) -> bool:
    """带走列表左边的宝可梦预览画出来了：不是粉色背景的像素占比超过 0.02。

    真机上空背景是纯粉色渐变（0），宝可梦画出来是 0.07 到 0.19。
    """
    background = screen.color_ratio(RESULT_PREVIEW_RECT, (140, 80, 0), (180, 255, 255))
    return 1 - background > 0.02


def _is_shiny(name: str) -> bool:
    """资料页上的闪光标志：照搬上游，闪光框里高饱和像素的占比（0 到 255）超过 10。

    沿用旧项目的两条保护：连看几帧，任何一帧是闪光就算（漏掉闪光无法挽回，误报只是停下来）；
    占比超过 100 说明画面根本不是资料页（真闪光约 27），这一帧不算。
    name 是资料页上的名字，和看到的最高占比一起记进这一局，写战报用。
    """
    # 连看几帧
    frames = 3

    peak = 0.0
    shiny = False
    for _ in range(frames):
        value = capture().color_ratio(SHINY_RECT, (0, 100, 20), (180, 255, 255)) * 255
        log(f"闪光框的占比 {value:.1f}", "DEBUG")
        peak = max(peak, value)
        if SHINY_MIN < value <= SHINY_MAX:
            shiny = True
            break
    run.get().shiny_peaks.append((name, peak))
    return shiny


def _take(index: int) -> None:
    """带走第 index 只：资料页按 B 回到列表，A 弹出菜单，在「选择」上按 A，把确认的对话推进完。

    照上游：资料页上按一次截图键，回到列表后再按一次，两张都存进 Switch 自己的相册
    （上游 auto_max_lair.py 的 push_buttons((p, 1), (b, 3), (p, 1))，p 就是截图键）。
    待实测：还没遇到过闪光，带走的对话怎么走没见过。
    """
    current = run.get()
    sw = switch.get()
    # 资料页和列表都要等宝可梦画出来再存图、按 Switch 的截图键
    image = wait_for(_sprite_shown, DEFAULT_TIMEOUT, "资料页上的宝可梦")
    _save_screenshot(image, "shiny-summary")
    sw.click("CAPTURE", 0)
    log("闪光的资料页存进了 Switch 相册")
    sw.click("B", 0)
    image = wait_for(
        lambda screen: (
            screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT)
            and screen.selected(list(RESULT_ROW_RECTS[: current.num_caught])) == index
            and _preview_shown(screen)
        ),
        DEFAULT_TIMEOUT,
        "回到列表，光标在要带走的那只上",
    )
    _save_screenshot(image, "shiny-list")
    sw.click("CAPTURE", 0)
    log("带走列表存进了 Switch 相册")
    sw.click("A", 0)
    wait_for(lambda screen: _menu_selected(screen) == 0, DEFAULT_TIMEOUT, "光标在「选择」上")
    # 选择之后上游连按了 4 次 A，中间应该还有确认，确认默认在「是」上；所以一直按 A 到列表消失
    press_until(lambda screen: not screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT), "带走界面消失")
    name_id = current.caught[index]
    pokemon = data.boss_pokemon().get(name_id) or data.rental_pokemon().get(name_id)
    log(f"带走了 {name_id}")
    send(
        f"闪光！第 {current.round} 轮带走了 {pokemon.name() if pokemon else name_id}"
        f"（第 {index + 1} 只）"
    )


def _leave() -> None:
    """不带走：资料页按 B 回到列表，列表上按 B 会问「不带宝可梦回去了，你确定吗？」，
    确认光标在「是」上再按 A（真机实测）。

    列表刚出来时会吞按键（真机上按一次 B 没反应，等 10 秒超时），所以每步都按到画面变化为止。
    """
    sw = switch.get()
    act_until(
        lambda: sw.click("B", 0),
        lambda screen: (
            not screen.has_text(SUMMARY_NAME_LABEL_RECT, "名字")
            and screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT)
        ),
        "回到列表",
    )
    image = act_until(
        lambda: sw.click("B", 0),
        lambda screen: (
            screen.has_text(DIALOG_RECT, LEAVE_TEXT) and screen.selected(list(YES_NO_RECTS)) >= 0
        ),
        "不带走的确认",
    )
    if image.selected(list(YES_NO_RECTS)) != 0:
        raise RuntimeError("不带走的确认上光标不在「是」上")
    # 确认之后列表还会留一会儿，结算对话接着出现，所以等的是确认的问话消失
    act_until(
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(DIALOG_RECT, LEAVE_TEXT),
        "不带走的确认消失",
    )
    log("一只都不带走")


def _back_to_scientist() -> bool:
    """带走或不带走之后，按 A 推进结算的对话，直到对话结束、回到科学家面前。

    对话顺序（真机实测）：「把捉到的宝可梦和之前租用的宝可梦」→「……都交给了研究员！」
    → 结算画面「下一步」→「辛苦了。」→ 打赢时科学家还会问
    「您需要我为您保留×××所在位置的记录吗？」，再按一次 A 才弹出「是 / 否」。
    要不要保留按 RECORD_LOCATION：True 选「是」；False 停在这一步，返回 False，等人决定。
    """
    # 结算画面「下一步」和「辛苦了。」之间有一段转场，对话框是空的（真机上遇到过），
    # 所以先推进到「辛苦了。」，之后对话框空了才是真的说完了
    advance_until(
        lambda screen: screen.has_text(DIALOG_RECT, THANKS_TEXT),
        "「辛苦了。」",
        max_presses=30,
        timeout=LOAD_TIMEOUT,
    )
    image = advance_until(
        lambda screen: _record_question_shown(screen) or not screen.read_text(DIALOG_RECT),
        "结算对话结束，或者问要不要保留位置记录",
    )
    if not _record_question_shown(image):
        return True
    if not RECORD_LOCATION:
        log("科学家问要不要保留位置记录，配置是不自动选，停下来等人决定", "WARNING")
        return False
    if image.selected(list(YES_NO_RECTS)) != 0:
        raise RuntimeError("保留位置记录的菜单上光标不在「是」上")
    switch.get().click("A", 0)
    # 问话还在时就推进，会在它上面再按一次 A
    wait_for(
        lambda screen: not screen.has_text(DIALOG_RECT, RECORD_TEXT), DEFAULT_TIMEOUT, "问话消失"
    )
    advance_until(lambda screen: not screen.read_text(DIALOG_RECT), "对话结束", max_presses=10)
    log("保留了位置记录")
    return True


def _record_question_shown(screen: ImageChecker) -> bool:
    """科学家问要不要保留位置记录，并且「是 / 否」已经弹出来了。"""
    return screen.has_text(DIALOG_RECT, RECORD_TEXT) and screen.selected(list(YES_NO_RECTS)) >= 0


def _update_keep_path() -> bool:
    """查完闪光、没有可带走的之后，决定下一局要不要 keep path，记到这一局里，返回决定。

    锁定的图：只看向这张图的胜负统计，见 _should_unlock；赢了的局不管用了多久、倒下几次都保持。
    没锁定的图：打赢、倒下不超过 LOCK_MAX_FAINTS 次、用时不超过 LOCK_MAX_MINUTES 分钟，就锁定这张图。
    """
    current = run.get()
    won = current.num_caught == 4
    faints = 4 - current.lives
    minutes = (time.time() - current.started) / 60
    if current.plan is not None:
        current.lock_results.append(won)
        current.keep_path = not _should_unlock()
        recent = current.lock_results[-LOCK_WINDOW_ROUNDS:]
        rate = recent.count(True) / len(recent) * 100
        log(
            f"这一局 {current.path_name()}：{'赢' if won else '输'}，倒下 {faints} 次，"
            f"用时 {minutes:.1f} 分钟，这张图打了 {len(current.lock_results)} 局，"
            f"最近 {len(recent)} 局胜率 {rate:.0f}%，"
            f"{'解锁' if not current.keep_path else '继续锁定'}"
        )
        return current.keep_path
    current.keep_path = won and faints <= LOCK_MAX_FAINTS and minutes <= LOCK_MAX_MINUTES
    if current.keep_path:
        # 锁定这一局算这张图的第 1 局，是按打赢锁的
        current.lock_results = [True]
    log(
        f"这一局 {current.path_name()}：{'赢' if won else '输'}，倒下 {faints} 次，"
        f"用时 {minutes:.1f} 分钟，{'锁定这张图' if current.keep_path else '不锁定'}"
    )
    return current.keep_path


def _should_unlock() -> bool:
    """这张锁定的图是不是该扔了。

    打满 LOCK_WINDOW_ROUNDS 局之前只看失败次数，失败 LOCK_EARLY_FAILS 次就扔；
    打满之后看最近 LOCK_WINDOW_ROUNDS 局的胜率，低于 LOCK_MIN_WIN_RATE 就扔。
    """
    current = run.get()
    results = current.lock_results
    if len(results) < LOCK_WINDOW_ROUNDS:
        return results.count(False) >= LOCK_EARLY_FAILS
    window = results[-LOCK_WINDOW_ROUNDS:]
    return window.count(True) / len(window) < LOCK_MIN_WIN_RATE


def _restart_same_seed() -> None:
    """keep path：把这一局写进状态文件（下一局沿用），然后重启游戏，回到存档里同一张路线图。"""
    run.save()
    log("keep path，重启游戏回到同一张路线图")
    restart()


def _menu_selected(screen: ImageChecker) -> int:
    """「选择 / 查看能力 / 取消」菜单上光标在第几项（从 0 开始），菜单不在返回 -1。

    菜单跟着列表上选中的那一行出现，位置不固定，所以先在列表区域里找到这三项的文字，再比亮度。
    """
    lines = {text: rect for text, rect in text_lines(screen, RESULT_MENU_RECT)}
    if not all(item in lines for item in ("选择", "查看能力", "取消")):
        return -1
    return screen.selected([lines["选择"], lines["查看能力"], lines["取消"]])


def _save_screenshot(image: ImageChecker, kind: str) -> None:
    """把战果截图存进 CATCH_DIR，文件名带时间。只留最新的一些，旧的删掉。"""
    # 最多留几张
    keep = 200

    CATCH_DIR.mkdir(parents=True, exist_ok=True)
    path = CATCH_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}.jpg"
    save(image, str(path))
    for old in sorted(CATCH_DIR.glob("*.jpg"))[:-keep]:
        old.unlink()
    run.get().screenshots.append(str(path))
    log(f"战果截图: {path}", "DEBUG")
