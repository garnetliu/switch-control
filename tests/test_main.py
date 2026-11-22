"""control_switch.__main__：命令行入口 run、restart。

不连 Switch：load_script 换成返回假脚本的函数，init_log 换成什么都不做的函数，
load_dotenv 换掉，不读仓库里真实的 .env。假连接用 tests/conftest.py 的 make_switch，
再加上记下 send 调用的假 notifier 和记下调用次数的 close()。
"""

import runpy
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from control_switch.__main__ import main
from control_switch.flow import capture

IMAGE = Path(__file__).resolve().parent / "images" / "路线上的界面-要走哪条路.jpg"

SwitchFactory = Callable[..., Any]


class RecordingNotifier:
    """记下每次 send 的文字和附件。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[Path]]] = []

    def send(self, text: str, files: list[Path] | None = None) -> None:
        """记下调用，不发消息。"""
        self.sent.append((text, list(files or [])))


class Calls:
    """一次测试里各个被换掉的函数收到的调用。"""

    def __init__(self) -> None:
        self.load_script: list[str] = []
        self.init_log: list[str | None] = []
        self.restart: list[Any] = []
        self.close = 0


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_dotenv 换成什么都不读，这个文件里的测试都不读仓库里真实的 .env。"""
    monkeypatch.setattr("control_switch.__main__.load_dotenv", lambda *args, **kwargs: False)


@pytest.fixture
def calls() -> Calls:
    """记录各个假函数收到的调用。"""
    return Calls()


@pytest.fixture
def connection(make_switch: SwitchFactory, calls: Calls) -> Any:
    """假连接：有一张可截的图、记下 send 的 notifier、记下调用次数的 close()。"""
    sw = make_switch([IMAGE.read_bytes()])
    sw.notifier = RecordingNotifier()

    def close() -> None:
        calls.close += 1

    sw.close = close
    return sw


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch, calls: Calls, connection: Any) -> Callable[..., None]:
    """返回一个函数：传入 STEPS 和 START，把 load_script 换成返回这个假脚本的函数，init_log 换成不做事。"""

    def setup(steps: dict[str, Callable[[Any], str]], start: str) -> None:
        script = SimpleNamespace(STEPS=steps, START=start, connect=lambda: connection)

        def fake_load_script(name: str) -> SimpleNamespace:
            calls.load_script.append(name)
            return script

        def fake_init_log(sw: Any, name: str | None = None) -> None:
            calls.init_log.append(name)

        monkeypatch.setattr("control_switch.__main__.load_script", fake_load_script)
        monkeypatch.setattr("control_switch.__main__.init_log", fake_init_log)

    return setup


@pytest.fixture
def forbid_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_script 换成一调用就失败的函数：用来确认这条命令根本不会去找脚本、连接 Switch。"""

    def fail(name: str) -> None:
        raise AssertionError(f"不该去加载脚本：{name}")

    monkeypatch.setattr("control_switch.__main__.load_script", fail)


def failed_files(connection: Any) -> list[Path]:
    """failed_dir 下写出的所有截图。"""
    return sorted(connection.config.failed_dir.rglob("*.jpg"))


def test_run_with_unknown_script_exits() -> None:
    """main(["run", "没有/这个"])：抛 SystemExit，报错里有可以用的名字，不连接 Switch。"""
    with pytest.raises(SystemExit) as error:
        main(["run", "没有/这个"])
    assert "swsh/lair" in str(error.value)


def test_unknown_command_exits(forbid_connect: None) -> None:
    """main(["不认识的命令"])：抛 SystemExit，不去加载脚本。"""
    with pytest.raises(SystemExit):
        main(["不认识的命令"])


def test_no_command_prints_usage_and_exits_nonzero(
    forbid_connect: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """main([])：打印用法，抛 SystemExit，退出码不是 0，不去加载脚本。"""
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code not in (0, None)
    assert capsys.readouterr().out != ""


def test_run_without_script_name_defaults_to_swsh_lair(
    install: Callable[..., None], calls: Calls
) -> None:
    """main(["run"])：load_script 收到的名字是 swsh/lair。"""
    install({}, "start")
    main(["run"])
    assert calls.load_script == ["swsh/lair"]


def test_run_passes_script_name_to_load_script(install: Callable[..., None], calls: Calls) -> None:
    """main(["run", "sv/outbreak"])：load_script 收到的名字就是命令行里写的。"""
    install({}, "start")
    main(["run", "sv/outbreak"])
    assert calls.load_script == ["sv/outbreak"]


def test_run_uses_command_line_arguments_when_argv_is_none(
    install: Callable[..., None], calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() 不传 argv：用 sys.argv[1:]，这里是 run sv/outbreak。"""
    install({}, "start")
    monkeypatch.setattr(sys, "argv", ["control-switch", "run", "sv/outbreak"])
    main()
    assert calls.load_script == ["sv/outbreak"]


def test_run_initializes_log_in_start_directory(install: Callable[..., None], calls: Calls) -> None:
    """run：日志目录的名字是 "start"。"""
    install({}, "start")
    main(["run"])
    assert calls.init_log == ["start"]


def test_run_runs_steps_in_order_until_name_not_in_steps(
    install: Callable[..., None], calls: Calls
) -> None:
    """假脚本两步：第一步返回第二步的名字，第二步返回不在 STEPS 里的名字，各被调一次，main 正常返回。"""
    order: list[tuple[str, str]] = []

    def first(sw: Any) -> str:
        order.append(("first", sw.step))
        return "second"

    def second(sw: Any) -> str:
        order.append(("second", sw.step))
        return "finished"

    install({"first": first, "second": second}, "first")
    assert main(["run"]) is None
    assert order == [("first", "first"), ("second", "second")]


def test_run_sets_sw_step_before_each_step_is_called(
    install: Callable[..., None], connection: Any
) -> None:
    """run：每一步被调时 sw.step 已经是这一步的名字（截图时会带上）。"""
    seen: list[str] = []

    def first(sw: Any) -> str:
        seen.append(sw.step)
        return "second"

    def second(sw: Any) -> str:
        seen.append(sw.step)
        return ""

    install({"first": first, "second": second}, "first")
    main(["run"])
    assert seen == ["first", "second"]
    assert connection.step == "second"


def test_run_starts_from_script_start_step(install: Callable[..., None]) -> None:
    """run：从 START 指定的那一步开始，不是 STEPS 里的第一步。"""
    order: list[str] = []

    def a(sw: Any) -> str:
        order.append("a")
        return ""

    def b(sw: Any) -> str:
        order.append("b")
        return ""

    install({"a": a, "b": b}, "b")
    main(["run"])
    assert order == ["b"]


def test_run_error_reraises_saves_screenshot_and_notifies(
    install: Callable[..., None], connection: Any
) -> None:
    """某一步先 capture 两张图再抛 RuntimeError：main 抛出同一个异常；failed_dir 下写出两张截图；
    notifier.send 被调一次，文字里有出错的步骤名和错误，files 只有最后一张截图。
    """
    error = RuntimeError("出错了")

    def first(sw: Any) -> str:
        capture(sw, "第一张")
        capture(sw, "第二张")
        raise error

    install({"first": first}, "first")
    with pytest.raises(RuntimeError) as raised:
        main(["run"])
    assert raised.value is error

    files = failed_files(connection)
    assert len(files) == 2
    assert files[-1].name.endswith("-first-第二张.jpg")
    sent = connection.notifier.sent
    assert len(sent) == 1
    text, attached = sent[0]
    assert "first" in text
    assert "RuntimeError" in text
    assert "出错了" in text
    assert attached == [files[-1]]


def test_run_error_in_later_step_reports_that_step(
    install: Callable[..., None], connection: Any
) -> None:
    """第一步正常、第二步抛错：通知里写的是第二步的名字。"""

    def first(sw: Any) -> str:
        return "second"

    def second(sw: Any) -> str:
        capture(sw, "看图")
        raise RuntimeError("坏了")

    install({"first": first, "second": second}, "first")
    with pytest.raises(RuntimeError):
        main(["run"])
    text = connection.notifier.sent[0][0]
    assert "步骤：second" in text


def test_run_system_exit_passes_through_without_screenshot_or_notification(
    install: Callable[..., None], connection: Any
) -> None:
    """某一步抛 SystemExit：原样抛出，failed_dir 下没有截图，notifier.send 没被调。"""
    exit_request = SystemExit(3)

    def first(sw: Any) -> str:
        capture(sw, "有一张图")
        raise exit_request

    install({"first": first}, "first")
    with pytest.raises(SystemExit) as raised:
        main(["run"])
    assert raised.value is exit_request
    assert failed_files(connection) == []
    assert connection.notifier.sent == []


def test_restart_without_script_name_calls_restart_and_closes(
    install: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
    calls: Calls,
    connection: Any,
) -> None:
    """main(["restart"])：默认脚本 swsh/lair，restart 收到这条连接，正常返回时 close() 被调一次。"""
    install({}, "start")
    monkeypatch.setattr("control_switch.__main__.restart", calls.restart.append)
    main(["restart"])
    assert calls.load_script == ["swsh/lair"]
    assert calls.restart == [connection]
    assert calls.close == 1


def test_restart_initializes_log_in_restart_directory(
    install: Callable[..., None], monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """restart：日志目录的名字是 "restart"。"""
    install({}, "start")
    monkeypatch.setattr("control_switch.__main__.restart", calls.restart.append)
    main(["restart"])
    assert calls.init_log == ["restart"]


def test_restart_passes_script_name_to_load_script(
    install: Callable[..., None], monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """main(["restart", "sv/outbreak"])：load_script 收到命令行里写的名字。"""
    install({}, "start")
    monkeypatch.setattr("control_switch.__main__.restart", calls.restart.append)
    main(["restart", "sv/outbreak"])
    assert calls.load_script == ["sv/outbreak"]


def test_restart_error_propagates_and_still_closes(
    install: Callable[..., None], monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """restart 抛 RuntimeError：异常抛出来，close() 也被调了一次。"""
    install({}, "start")
    error = RuntimeError("重启失败")

    def failing(sw: Any) -> None:
        raise error

    monkeypatch.setattr("control_switch.__main__.restart", failing)
    with pytest.raises(RuntimeError) as raised:
        main(["restart"])
    assert raised.value is error
    assert calls.close == 1


def test_python_m_control_switch_runs_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """python -m control_switch 走的是 main()：不带命令时打印用法、以非 0 退出。

    防止 __main__.py 末尾的 `if __name__ == "__main__": main()` 被删掉或写错，
    python -m control_switch 什么都不做就正常退出。runpy 重新执行模块，
    所以在 dotenv 模块上换掉 load_dotenv，不读仓库里真实的 .env。
    """
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(sys, "argv", ["python -m control_switch"])
    with warnings.catch_warnings():
        # control_switch.__main__ 已经被这个文件引用过，runpy 再执行一次时会提醒
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as error:
            runpy.run_module("control_switch", run_name="__main__")
    assert error.value.code not in (0, None)
    assert "用法" in capsys.readouterr().out
