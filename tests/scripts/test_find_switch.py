"""scripts/find_switch.py：按 MAC 找 Switch、ping、把找到的 ip 打印到标准输出。

脚本不在包里，用文件路径加载。subprocess.run、socket.socket、time.sleep 都换成假的，
不发网络包、不跑 route、arp、ping；ROOT 指到临时目录，不写仓库的 runs/logs/find。
"""

import importlib.util
import logging
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Self

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "find_switch.py"

SWITCH_MAC = "04:03:D6:AA:BB:CC"
SWITCH_ARP_LINE = "? (192.168.1.50) at 4:3:d6:aa:bb:cc on en0 ifscope [ethernet]"
OTHER_ARP_LINE = "? (192.168.1.1) at 11:22:33:44:55:66 on en0 ifscope [ethernet]"
PING_SUMMARY = "round-trip min/avg/max/stddev = 3.100/7.456/12.000/2.100 ms"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("find_switch_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script() -> ModuleType:
    return load_script()


@dataclass
class FakeNetwork:
    """假的网络：每一轮 arp -an 的输出按顺序给，用完后一直给最后一个。"""

    arp_rounds: Sequence[str] = ("",)
    ping_stdout: str = PING_SUMMARY
    default_route: str = "   interface: en0\n"
    commands: list[list[str]] = field(default_factory=list)
    sent: list[tuple[str, int]] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)
    send_error: bool = False

    def arp_count(self) -> int:
        return sum(1 for command in self.commands if command[0] == "arp")

    def run(self, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(args))
        if args[0] == "route":
            return subprocess.CompletedProcess(args, 0, self.default_route, "")
        if args[0] == "ipconfig":
            return subprocess.CompletedProcess(args, 0, "192.168.1.23\n", "")
        if args[0] == "arp":
            index = min(self.arp_count() - 1, len(self.arp_rounds) - 1)
            return subprocess.CompletedProcess(args, 0, self.arp_rounds[index], "")
        if args[0] == "ping":
            return subprocess.CompletedProcess(args, 0, self.ping_stdout, "")
        raise AssertionError(f"不该运行的命令：{args}")


def install_network(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType, network: FakeNetwork
) -> FakeNetwork:
    class FakeSocket:
        def __init__(self, *args: object) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def sendto(self, data: bytes, address: tuple[str, int]) -> int:
            if network.send_error:
                raise OSError("网络不可达")
            network.sent.append(address)
            return len(data)

    monkeypatch.setattr(script.subprocess, "run", network.run)
    monkeypatch.setattr(script.socket, "socket", FakeSocket)
    monkeypatch.setattr(script.time, "sleep", network.sleeps.append)
    return network


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4:3:d6:a:b:c", "04:03:d6:0a:0b:0c"),
        ("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"),
        ("AA-BB-CC-DD-EE-FF", "aa:bb:cc:dd:ee:ff"),
        ("4-3-D6-A-B-C", "04:03:d6:0a:0b:0c"),
    ],
    ids=["补前导0", "转小写", "横线转冒号", "横线加补0加小写"],
)
def test_normalize_mac(script: ModuleType, raw: str, expected: str) -> None:
    """_normalize_mac：补前导 0、转成小写、用 - 分隔的转成用 : 分隔。"""
    assert script._normalize_mac(raw) == expected


def test_local_prefix_returns_first_three_parts_of_interface_ip(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """_local_prefix：取默认路由网卡的 ip 的前三段，并用这块网卡名问 ipconfig。"""
    network = install_network(monkeypatch, script, FakeNetwork())
    assert script._local_prefix() == "192.168.1"
    assert ["ipconfig", "getifaddr", "en0"] in network.commands


def test_local_prefix_raises_when_no_default_route(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """_local_prefix：route 的输出里没有 interface 时抛 RuntimeError。"""
    install_network(monkeypatch, script, FakeNetwork(default_route="route: not in table\n"))
    with pytest.raises(RuntimeError, match="找不到默认路由"):
        script._local_prefix()


def test_find_switch_returns_ip_matching_mac_in_arp_output(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """find_switch：在 arp -an 的输出里按 MAC 找到 ip（arp 省略前导 0、大小写不同也对得上）。"""
    install_network(
        monkeypatch, script, FakeNetwork(arp_rounds=[f"{OTHER_ARP_LINE}\n{SWITCH_ARP_LINE}\n"])
    )
    assert script.find_switch(SWITCH_MAC) == "192.168.1.50"


def test_find_switch_sends_udp_packets_to_whole_subnet(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """find_switch 每一轮给本网段的 1 到 254 各发一个 UDP 包到 9 端口，发包失败（OSError）不影响查找。"""
    network = install_network(monkeypatch, script, FakeNetwork(arp_rounds=[SWITCH_ARP_LINE]))
    assert script.find_switch(SWITCH_MAC) == "192.168.1.50"
    assert network.sent == [(f"192.168.1.{i}", 9) for i in range(1, 255)]

    failing = install_network(
        monkeypatch, script, FakeNetwork(arp_rounds=[SWITCH_ARP_LINE], send_error=True)
    )
    assert script.find_switch(SWITCH_MAC) == "192.168.1.50"
    assert failing.sent == []


def test_find_switch_ignores_ip_outside_local_subnet(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """find_switch：MAC 对但 ip 不在本机网段（例如 10.0.0.5）的不算，找不到返回 None。"""
    outside = "? (10.0.0.5) at 4:3:d6:aa:bb:cc on en1 ifscope [ethernet]"
    install_network(monkeypatch, script, FakeNetwork(arp_rounds=[outside]))
    assert script.find_switch(SWITCH_MAC, rounds=2) is None


def test_find_switch_does_not_match_prefix_of_other_subnet(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """find_switch：192.168.10.x 不算在 192.168.1 这个网段里（前缀要带点）。"""
    other = "? (192.168.10.50) at 4:3:d6:aa:bb:cc on en0 ifscope [ethernet]"
    install_network(monkeypatch, script, FakeNetwork(arp_rounds=[other]))
    assert script.find_switch(SWITCH_MAC, rounds=1) is None


def test_find_switch_returns_none_after_all_rounds_without_match(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """find_switch：几轮都没有这个 MAC 就返回 None，扫了 rounds 轮，每轮等 1.5 秒。"""
    network = install_network(monkeypatch, script, FakeNetwork(arp_rounds=[OTHER_ARP_LINE]))
    assert script.find_switch(SWITCH_MAC, rounds=3) is None
    assert network.arp_count() == 3
    assert network.sleeps == [1.5, 1.5, 1.5]


def test_find_switch_default_is_three_rounds(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """find_switch 不传 rounds 时扫 3 轮。"""
    network = install_network(monkeypatch, script, FakeNetwork(arp_rounds=[""]))
    assert script.find_switch(SWITCH_MAC) is None
    assert network.arp_count() == 3


def test_find_switch_finds_ip_in_a_later_round_and_stops(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """find_switch：第一轮没回 ARP，第二轮才有：返回 ip，不再扫第三轮。"""
    network = install_network(
        monkeypatch, script, FakeNetwork(arp_rounds=["", SWITCH_ARP_LINE, SWITCH_ARP_LINE])
    )
    assert script.find_switch(SWITCH_MAC, rounds=3) == "192.168.1.50"
    assert network.arp_count() == 2


def test_ping_returns_average_delay_from_summary_line(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """ping：从汇总行里解析出平均延迟（毫秒）。"""
    network = install_network(monkeypatch, script, FakeNetwork())
    assert script.ping("192.168.1.50") == pytest.approx(7.456)
    assert network.commands == [["ping", "-c", "4", "-W", "1000", "192.168.1.50"]]


def test_ping_passes_count_and_timeout_to_command(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType
) -> None:
    """ping：count 和 timeout_ms 写进命令的 -c、-W 参数。"""
    network = install_network(monkeypatch, script, FakeNetwork())
    script.ping("192.168.1.50", count=2, timeout_ms=500)
    assert network.commands == [["ping", "-c", "2", "-W", "500", "192.168.1.50"]]


def test_ping_returns_none_and_logs_warning_without_summary_line(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType, caplog: pytest.LogCaptureFixture
) -> None:
    """ping：输出里没有汇总行（一个包都没收到）返回 None，并把原始输出记成一条 WARNING。"""
    lost = "4 packets transmitted, 0 packets received, 100.0% packet loss\n"
    install_network(monkeypatch, script, FakeNetwork(ping_stdout=lost))
    with caplog.at_level(logging.WARNING):
        assert script.ping("192.168.1.50") is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "没有收到回复" in warnings[0].getMessage()
    assert "100.0% packet loss" in warnings[0].getMessage()


@pytest.fixture
def isolated_main(
    monkeypatch: pytest.MonkeyPatch,
    script: ModuleType,
    tmp_path: Path,
    clean_root_logger: logging.Logger,
) -> ModuleType:
    """main 要用的环境：ROOT 在临时目录，根 logger 是干净的。"""
    monkeypatch.setattr(script, "ROOT", tmp_path)
    return script


def read_log(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in (root / "runs" / "logs" / "find").glob("*.log")
    )


def test_main_prints_ip_when_found(
    monkeypatch: pytest.MonkeyPatch,
    isolated_main: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main 找到 Switch：标准输出只有 ip 这一行，并 ping 一下记录延迟，日志写在 runs/logs/find/ 下。"""
    install_network(monkeypatch, isolated_main, FakeNetwork(arp_rounds=[SWITCH_ARP_LINE]))
    isolated_main.main([SWITCH_MAC])
    assert capsys.readouterr().out == "192.168.1.50\n"
    log = read_log(tmp_path)
    assert "找到 Switch: 192.168.1.50" in log
    assert "ping 平均 7 ms" in log


def test_main_exits_with_nonzero_status_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
    isolated_main: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main 找不到 Switch：以非 0 状态退出，标准输出是空的，日志里有错误。"""
    install_network(monkeypatch, isolated_main, FakeNetwork(arp_rounds=[OTHER_ARP_LINE]))
    with pytest.raises(SystemExit) as exit_info:
        isolated_main.main([SWITCH_MAC])
    assert exit_info.value.code not in (0, None)
    assert capsys.readouterr().out == ""
    assert "找不到 Switch" in read_log(tmp_path)


def test_main_warns_when_ping_gets_no_reply(
    monkeypatch: pytest.MonkeyPatch,
    isolated_main: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main：ping 不通只记一条警告，ip 照样打印出来。"""
    install_network(
        monkeypatch,
        isolated_main,
        FakeNetwork(arp_rounds=[SWITCH_ARP_LINE], ping_stdout="100.0% packet loss"),
    )
    isolated_main.main([SWITCH_MAC])
    assert "ping 不通" in read_log(tmp_path)
    assert capsys.readouterr().out == "192.168.1.50\n"


def test_main_warns_when_ping_delay_exceeds_150_ms(
    monkeypatch: pytest.MonkeyPatch, isolated_main: ModuleType, tmp_path: Path
) -> None:
    """main：ping 平均延迟超过 150 ms 记一条「网络太差」的警告。"""
    slow = "round-trip min/avg/max/stddev = 100.0/200.0/300.0/5.0 ms"
    install_network(
        monkeypatch,
        isolated_main,
        FakeNetwork(arp_rounds=[SWITCH_ARP_LINE], ping_stdout=slow),
    )
    isolated_main.main([SWITCH_MAC])
    log = read_log(tmp_path)
    assert "WARNING" in log
    assert "网络太差" in log


def test_main_does_not_warn_when_ping_delay_is_exactly_150_ms(
    monkeypatch: pytest.MonkeyPatch, isolated_main: ModuleType, tmp_path: Path
) -> None:
    """main：平均延迟刚好 150 ms 不算超过，只记普通的「ping 平均」。"""
    edge = "round-trip min/avg/max/stddev = 100.0/150.0/300.0/5.0 ms"
    install_network(
        monkeypatch,
        isolated_main,
        FakeNetwork(arp_rounds=[SWITCH_ARP_LINE], ping_stdout=edge),
    )
    isolated_main.main([SWITCH_MAC])
    log = read_log(tmp_path)
    assert "网络太差" not in log
    assert "ping 平均 150 ms" in log


@pytest.mark.parametrize(
    "args",
    [[], ["zz:zz:zz:zz:zz:zz"], ["04:03:d6:aa:bb"], [SWITCH_MAC, SWITCH_MAC]],
    ids=["没传", "不是十六进制", "少一段", "传了两个"],
)
def test_main_reports_bad_mac_argument_without_scanning(
    monkeypatch: pytest.MonkeyPatch, isolated_main: ModuleType, tmp_path: Path, args: list[str]
) -> None:
    """MAC 没传、格式不对或传多了：一开始就以非 0 退出，日志里写明是 MAC 的问题，不扫网段。"""
    network = install_network(monkeypatch, isolated_main, FakeNetwork(arp_rounds=[SWITCH_ARP_LINE]))
    with pytest.raises(SystemExit) as error:
        isolated_main.main(args)
    assert error.value.code not in (0, None)
    assert network.arp_count() == 0
    log = read_log(tmp_path)
    assert "MAC" in log or "mac" in log
