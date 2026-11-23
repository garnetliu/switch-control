"""control_switch.__main__：命令行入口 run、restart。

不连 Switch：load_script 换成返回假脚本的函数，init_log、init_console 换成不做事（或只记下调用）的函数，
check_controller_reaches_screen 换成什么都不做的函数，
load_dotenv 换掉，不读仓库里真实的 .env，Settings 读的环境变量清掉。create_devices 换成不连接、
直接返回一个假 Devices 的函数，这个假 Devices 先交给 check_devices 检查（假 Screen 给的是真机截图，
假 Memory 的 title_id 和假脚本的 TITLE_IDS 对得上），再传给假脚本的 SESSION，不会放进 Session。
假脚本的 SESSION 接收 (settings, devices)，不管传进来什么，
都返回用 tests/conftest.py 的假设备建的 Session，Session 的 notifier 换成记下 send 调用的假对象；
close() 有没有被调，看建 Session 用的三个假设备各自的 close_calls。
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
from control_switch.device import DeviceCheckError, Devices
from control_switch.device import create_devices as real_create_devices
from control_switch.flow import capture

IMAGE = Path(__file__).resolve().parent / "images" / "路线上的界面-要走哪条路.jpg"

TITLE_ID = "0100ABF008968000"
OTHER_TITLE_ID = "0100000000000000"
REQUIRES = frozenset({"screen", "controller", "memory"})

SessionFactory = Callable[..., Any]
MemoryFactory = Callable[..., Any]


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
        # create_devices 被调了几次
        self.create_devices = 0
        # init_console 被调了几次
        self.init_console = 0


SETTINGS_ENV_NAMES = (
    "SCREEN",
    "CONTROLLER",
    "MEMORY",
    "SWITCH_CONNECTION",
    "SWITCH_IP",
    "SWITCH_PORT",
    "PKHEX_API_URL",
    "DISCORD_WEBHOOK_URL",
    "KEEP_PATH",
    "SERIAL_PORT",
    "SERIAL_BAUD",
)


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_dotenv 换成什么都不读，Settings 读的 11 个环境变量都清掉：
    这个文件里的测试不读仓库里真实的 .env，也不受终端里设过的环境变量影响。
    """
    monkeypatch.setattr("control_switch.settings.load_dotenv", lambda *args, **kwargs: False)
    for name in SETTINGS_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def calls() -> Calls:
    """记录各个假函数收到的调用。"""
    return Calls()


@pytest.fixture(autouse=True)
def fake_devices(
    monkeypatch: pytest.MonkeyPatch,
    calls: Calls,
    make_screen: Callable[..., Any],
    controller: Any,
    make_memory: MemoryFactory,
) -> Devices:
    """create_devices 换成不连接、直接返回一个假 Devices 的函数，并记下调用次数。

    这个假 Devices 要过 check_devices：假 Screen 的图是真机截图，假 Memory 的 title_id 是剑的。
    它传给 SESSION，不会放进 Session。
    """
    devices = Devices(make_screen([IMAGE.read_bytes()]), controller, make_memory(TITLE_ID))

    def create_devices(settings: Any) -> Devices:
        calls.create_devices += 1
        return devices

    monkeypatch.setattr("control_switch.__main__.create_devices", create_devices)
    return devices


@pytest.fixture(autouse=True)
def fake_init_console(monkeypatch: pytest.MonkeyPatch, calls: Calls) -> None:
    """init_console 换成只记次数的函数：真的会给根 logger 加终端输出。"""

    def init_console() -> None:
        calls.init_console += 1

    monkeypatch.setattr("control_switch.__main__.init_console", init_console)


@pytest.fixture
def connection(make_session: SessionFactory, monkeypatch: pytest.MonkeyPatch) -> Any:
    """用假设备建的 Session：有一张可截的图、notifier 是记下 send 的假对象。"""
    sw = make_session([IMAGE.read_bytes()])
    monkeypatch.setattr(sw, "notifier", RecordingNotifier())
    return sw


@pytest.fixture
def install(
    monkeypatch: pytest.MonkeyPatch, calls: Calls, connection: Any
) -> Callable[..., SimpleNamespace]:
    """返回一个函数：传入 STEPS 和 START，把 load_script 换成返回这个假脚本的函数，init_log 换成不做事，
    check_controller_reaches_screen 换成什么都不做；返回这个假脚本。

    假脚本有 REQUIRES（三样都要）和 TITLE_IDS（和假 Memory 的 title_id 对得上），
    SESSION 接收 (settings, devices)，返回 connection 这个 Session。
    """

    def session(settings: Any, devices: Any) -> Any:
        return connection

    def setup(steps: dict[str, Callable[[Any], str]], start: str) -> SimpleNamespace:
        script = SimpleNamespace(
            STEPS=steps,
            START=start,
            SESSION=session,
            REQUIRES=REQUIRES,
            TITLE_IDS=(TITLE_ID,),
        )

        def fake_load_script(name: str) -> SimpleNamespace:
            calls.load_script.append(name)
            return script

        def fake_init_log(sw: Any, name: str | None = None) -> None:
            calls.init_log.append(name)

        monkeypatch.setattr("control_switch.__main__.load_script", fake_load_script)
        monkeypatch.setattr("control_switch.__main__.init_log", fake_init_log)
        monkeypatch.setattr(
            "control_switch.__main__.check_controller_reaches_screen", lambda sw: None
        )
        return script

    return setup


@pytest.fixture
def forbid_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_script 换成一调用就失败的函数：用来确认这条命令根本不会去找脚本、连接 Switch。"""

    def fail(name: str) -> None:
        raise AssertionError(f"不该去加载脚本：{name}")

    monkeypatch.setattr("control_switch.__main__.load_script", fail)


def assert_each_device_closed_once(connection: Any) -> None:
    """建 Session 用的三个假设备：每个各被关了一次（create_devices 返回的那个不看）。"""
    assert connection.screen.close_calls == 1
    assert connection.controller.close_calls == 1
    assert connection.memory.close_calls == 1


def failed_files(connection: Any) -> list[Path]:
    """failed_dir 下写出的所有截图。"""
    return sorted(connection.config.failed_dir.rglob("*.jpg"))


def test_run_with_unknown_script_exits() -> None:
    """main(["run", "没有/这个"])：抛 SystemExit，报错里有可以用的名字，不连接 Switch。"""
    with pytest.raises(SystemExit) as error:
        main(["run", "没有/这个"])
    assert "swsh/lair" in str(error.value)


def test_run_with_unknown_script_does_not_call_create_devices(calls: Calls) -> None:
    """main(["run", "没有/这个"])：抛 SystemExit，create_devices 一次都没被调用。"""
    with pytest.raises(SystemExit):
        main(["run", "没有/这个"])
    assert calls.create_devices == 0


def test_restart_with_unknown_script_does_not_call_create_devices(calls: Calls) -> None:
    """main(["restart", "没有/这个"])：抛 SystemExit，create_devices 一次都没被调用。"""
    with pytest.raises(SystemExit):
        main(["restart", "没有/这个"])
    assert calls.create_devices == 0


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
    install: Callable[..., SimpleNamespace], calls: Calls
) -> None:
    """main(["run"])：load_script 收到的名字是 swsh/lair。"""
    install({}, "start")
    main(["run"])
    assert calls.load_script == ["swsh/lair"]


def test_run_passes_script_name_to_load_script(
    install: Callable[..., SimpleNamespace], calls: Calls
) -> None:
    """main(["run", "sv/outbreak"])：load_script 收到的名字就是命令行里写的。"""
    install({}, "start")
    main(["run", "sv/outbreak"])
    assert calls.load_script == ["sv/outbreak"]


def test_run_uses_command_line_arguments_when_argv_is_none(
    install: Callable[..., SimpleNamespace], calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() 不传 argv：用 sys.argv[1:]，这里是 run sv/outbreak。"""
    install({}, "start")
    monkeypatch.setattr(sys, "argv", ["control-switch", "run", "sv/outbreak"])
    main()
    assert calls.load_script == ["sv/outbreak"]


def test_run_initializes_log_in_start_directory(
    install: Callable[..., SimpleNamespace], calls: Calls
) -> None:
    """run：日志目录的名字是 "start"。"""
    install({}, "start")
    main(["run"])
    assert calls.init_log == ["start"]


def test_run_runs_steps_in_order_until_name_not_in_steps(
    install: Callable[..., SimpleNamespace], calls: Calls
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
    install: Callable[..., SimpleNamespace], connection: Any
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


def test_run_starts_from_script_start_step(install: Callable[..., SimpleNamespace]) -> None:
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
    install: Callable[..., SimpleNamespace], connection: Any
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
    install: Callable[..., SimpleNamespace], connection: Any
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
    install: Callable[..., SimpleNamespace], connection: Any
) -> None:
    """某一步抛 SystemExit(3)：这一步被调了，原样抛出（退出码 3，说明退出的是这一步不是启动检查），failed_dir 下没有截图，notifier.send 没被调。"""
    exit_request = SystemExit(3)
    called: list[str] = []

    def first(sw: Any) -> str:
        called.append("first")
        capture(sw, "有一张图")
        raise exit_request

    install({"first": first}, "first")
    with pytest.raises(SystemExit) as raised:
        main(["run"])
    assert called == ["first"]
    assert raised.value.code == 3
    assert raised.value is exit_request
    assert failed_files(connection) == []
    assert connection.notifier.sent == []


def test_restart_without_script_name_calls_restart_and_closes(
    install: Callable[..., SimpleNamespace],
    monkeypatch: pytest.MonkeyPatch,
    calls: Calls,
    connection: Any,
) -> None:
    """main(["restart"])：默认脚本 swsh/lair，restart 收到这个 Session，正常返回时建 Session 用的三个设备各被关了一次。"""
    install({}, "start")
    monkeypatch.setattr("control_switch.__main__.restart", calls.restart.append)
    main(["restart"])
    assert calls.load_script == ["swsh/lair"]
    assert calls.restart == [connection]
    assert_each_device_closed_once(connection)


def test_restart_initializes_log_in_restart_directory(
    install: Callable[..., SimpleNamespace], monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """restart：日志目录的名字是 "restart"。"""
    install({}, "start")
    monkeypatch.setattr("control_switch.__main__.restart", calls.restart.append)
    main(["restart"])
    assert calls.init_log == ["restart"]


def test_restart_passes_script_name_to_load_script(
    install: Callable[..., SimpleNamespace], monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """main(["restart", "sv/outbreak"])：load_script 收到命令行里写的名字。"""
    install({}, "start")
    monkeypatch.setattr("control_switch.__main__.restart", calls.restart.append)
    main(["restart", "sv/outbreak"])
    assert calls.load_script == ["sv/outbreak"]


def test_restart_error_propagates_and_still_closes(
    install: Callable[..., SimpleNamespace], monkeypatch: pytest.MonkeyPatch, connection: Any
) -> None:
    """restart 抛 RuntimeError：异常抛出来，建 Session 用的三个设备也各被关了一次。"""
    install({}, "start")
    error = RuntimeError("重启失败")

    def failing(sw: Any) -> None:
        raise error

    monkeypatch.setattr("control_switch.__main__.restart", failing)
    with pytest.raises(RuntimeError) as raised:
        main(["restart"])
    assert raised.value is error
    assert_each_device_closed_once(connection)


def fail_session(settings: Any, devices: Any) -> Any:
    """SESSION 换成一调用就失败的函数：确认没有走到创建 Session 那一步。"""
    raise AssertionError("不该创建 Session")


def test_run_exits_nonzero_without_creating_session_when_game_is_wrong(
    install: Callable[..., SimpleNamespace],
    monkeypatch: pytest.MonkeyPatch,
    fake_devices: Devices,
) -> None:
    """run：假 Memory 的 title_id 是别的游戏：main 以非 0 退出，没有创建 SESSION。"""
    script = install({}, "start")
    monkeypatch.setattr(script, "SESSION", fail_session)
    memory: Any = fake_devices.memory
    monkeypatch.setattr(memory, "title", OTHER_TITLE_ID)
    with pytest.raises(SystemExit) as error:
        main(["run"])
    assert error.value.code not in (0, None)


def test_run_calls_init_console_before_create_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run swsh/lair：init_console 和 create_devices 记到同一个列表里，create_devices 抛 DeviceCheckError：
    main 以非 0 退出，init_console 在 create_devices 之前被调了。
    """
    events: list[str] = []

    def init_console() -> None:
        events.append("init_console")

    def create_devices(settings: Any) -> Devices:
        events.append("create_devices")
        raise DeviceCheckError("取图：不行")

    monkeypatch.setattr("control_switch.__main__.init_console", init_console)
    monkeypatch.setattr("control_switch.__main__.create_devices", create_devices)
    with pytest.raises(SystemExit) as error:
        main(["run", "swsh/lair"])
    assert error.value.code not in (0, None)
    assert events == ["init_console", "create_devices"]


def test_run_with_memory_none_exits_before_create_devices_for_script_needing_memory(
    monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """run sv/outbreak，MEMORY=none：main 以非 0 退出，报错里有 MEMORY，create_devices 没有被调。"""
    monkeypatch.setenv("MEMORY", "none")
    with pytest.raises(SystemExit) as error:
        main(["run", "sv/outbreak"])
    assert error.value.code not in (0, None)
    assert "MEMORY" in str(error.value.code)
    assert calls.create_devices == 0


def test_run_exits_nonzero_when_create_devices_raises_device_check_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run：create_devices 抛 DeviceCheckError：main 以非 0 退出（SystemExit）。"""

    def create_devices(settings: Any) -> Devices:
        raise DeviceCheckError("取图、按键、内存：botbase（USB）连接失败")

    monkeypatch.setattr("control_switch.__main__.create_devices", create_devices)
    with pytest.raises(SystemExit) as error:
        main(["run", "swsh/lair"])
    assert error.value.code not in (0, None)


def test_run_exits_with_message_and_no_value_error_when_setting_is_unknown(
    monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """run：SCREEN=hdmi（不认识的值）：main 抛 SystemExit（不是 ValueError），退出码不是 0，
    create_devices 没有被调。
    """
    monkeypatch.setenv("SCREEN", "hdmi")
    with pytest.raises(SystemExit) as error:
        main(["run", "swsh/lair"])
    assert error.value.code not in (0, None)
    assert calls.create_devices == 0


@pytest.mark.parametrize("raised", [ValueError("缺 ip"), NotImplementedError("还没实现")])
def test_run_exits_nonzero_when_create_devices_raises_value_or_not_implemented_error(
    monkeypatch: pytest.MonkeyPatch, raised: Exception
) -> None:
    """run：create_devices 抛 ValueError 或 NotImplementedError：main 抛 SystemExit，退出码不是 0。"""

    def create_devices(settings: Any) -> Devices:
        raise raised

    monkeypatch.setattr("control_switch.__main__.create_devices", create_devices)
    with pytest.raises(SystemExit) as error:
        main(["run", "swsh/lair"])
    assert error.value.code not in (0, None)


def test_restart_does_not_exit_when_game_is_wrong(
    install: Callable[..., SimpleNamespace],
    monkeypatch: pytest.MonkeyPatch,
    calls: Calls,
    connection: Any,
    fake_devices: Devices,
) -> None:
    """restart：假 Memory 的 title_id 是别的游戏：不因为游戏不对而退出，restart 被调了一次，main 没有抛 SystemExit。"""
    install({}, "start")
    monkeypatch.setattr("control_switch.__main__.restart", calls.restart.append)
    memory: Any = fake_devices.memory
    monkeypatch.setattr(memory, "title", OTHER_TITLE_ID)
    main(["restart"])
    assert calls.restart == [connection]


def test_python_m_control_switch_runs_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """python -m control_switch 走的是 main()：不带命令时打印用法、以非 0 退出。

    防止 __main__.py 末尾的 `if __name__ == "__main__": main()` 被删掉或写错，
    python -m control_switch 什么都不做就正常退出。runpy 重新执行模块，
    __main__ 不再引用 load_dotenv，.env 和环境变量的处理由这个文件的 autouse fixture 负责。
    """
    monkeypatch.setattr(sys, "argv", ["python -m control_switch"])
    with warnings.catch_warnings():
        # control_switch.__main__ 已经被这个文件引用过，runpy 再执行一次时会提醒
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as error:
            runpy.run_module("control_switch", run_name="__main__")
    assert error.value.code not in (0, None)
    assert "用法" in capsys.readouterr().out


def test_run_with_controller_serial_and_no_serial_port_exits_without_connecting_botbase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CONTROLLER=serial、SERIAL_PORT 没写，用真的 create_devices：
    main(["run", "swsh/lair"]) 抛 SystemExit，退出码不是 0，报错里有 SERIAL_PORT，没有连 botbase。
    """
    botbase_connects: list[object] = []

    def connect_botbase(settings: object) -> None:
        botbase_connects.append(settings)
        raise AssertionError("不该连 botbase")

    monkeypatch.setattr("control_switch.__main__.create_devices", real_create_devices)
    monkeypatch.setattr("control_switch.device.factory.connect_botbase", connect_botbase)
    monkeypatch.setenv("CONTROLLER", "serial")
    with pytest.raises(SystemExit) as error:
        main(["run", "swsh/lair"])
    assert error.value.code not in (0, None)
    assert "SERIAL_PORT" in str(error.value.code)
    assert botbase_connects == []
