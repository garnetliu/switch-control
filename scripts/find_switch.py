"""在局域网里按 MAC 地址找 Switch，把找到的 ip 打印到标准输出。

由 control-switch find <机器> 调用：它从 runs/switches.toml 读这台的 mac 传进来，再把打印出的 ip 写回去。
macOS 27 起，第三方程序（包括 uv 装的 Python）读到的 ARP 表是空的，只有系统自带的
/usr/bin/python3 读得到。所以这个文件要用系统 Python 运行，只能用 Python 3.9 支持的语法和标准库。
不要从 control_switch 包里导入模块，那些依赖装在 uv 的环境里。
"""

from __future__ import annotations

import logging
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _local_prefix() -> str:
    """默认路由所在网卡的 /24 网段前三段，例如 192.168.1。

    不用"连一个外部地址再读本机 IP"的办法，开了代理的虚拟网卡（utun）会让它读到
    198.18.x.x 之类的假地址。
    """
    route = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True).stdout
    match = re.search(r"interface: (\S+)", route)
    if match is None:
        raise RuntimeError("找不到默认路由，没有连上网络")
    iface = match.group(1)
    ip = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True)
    return ip.stdout.strip().rsplit(".", 1)[0]


def _normalize_mac(mac: str) -> str:
    """统一成小写、两位一组的格式，macOS 的 arp 会省略前导 0（4:3:d6 代表 04:03:d6）。"""
    return ":".join(x.zfill(2) for x in re.split(r"[:-]", mac.lower()))


def find_switch(switch_mac: str, rounds: int = 3) -> str | None:
    """在本机所在的 /24 网段里，按 MAC 地址查找 Switch，返回它的 ip，找不到返回 None。

    做法：给网段里每个地址发一个 UDP 包，让系统通过 ARP 解析出对方的 MAC，
    再读 ARP 表按 MAC 匹配。不会连接 Switch 的 6000 端口。
    Switch 的 WiFi 省电时回 ARP 很慢，一轮里可能漏掉，所以没找到就再扫，最多 rounds 轮。
    """
    mac = _normalize_mac(switch_mac)
    prefix = _local_prefix()

    for _ in range(rounds):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            for i in range(1, 255):
                try:
                    s.sendto(b"", (f"{prefix}.{i}", 9))
                except OSError:
                    pass
        time.sleep(1.5)

        out = subprocess.run(["arp", "-an"], capture_output=True, text=True).stdout
        for ip, found in re.findall(r"\(([\d.]+)\) at ([0-9a-f:]+)", out, re.I):
            if ip.startswith(prefix + ".") and _normalize_mac(found) == mac:
                return ip
    return None


def ping(ip: str, count: int = 4, timeout_ms: int = 1000) -> float | None:
    """ping 一个地址，返回平均延迟（毫秒）。一个包都没收到返回 None。

    调用系统的 ping 命令，解析的是 macOS 输出的汇总行。
    没收到包时，把 ping 命令的原始输出记成一条 WARNING，方便查原因。

    count: 发几个包。
    timeout_ms: 每个包等多久，单位毫秒（macOS 的 -W 参数以毫秒为单位）。
    """
    result = subprocess.run(
        ["ping", "-c", str(count), "-W", str(timeout_ms), ip],
        check=False,
        capture_output=True,
        text=True,
    )
    match = re.search(r"= [\d.]+/([\d.]+)/", result.stdout)
    if match is None:
        logging.warning(
            f"ping {ip} 没有收到回复，返回码 {result.returncode}，"
            f"输出 {result.stdout!r}，错误 {result.stderr!r}"
        )
        return None
    return float(match.group(1))


def _init_log() -> None:
    """日志写到终端（标准错误）和 runs/logs/find/ 下带时间戳的文件，标准输出只留给 ip。"""
    directory = ROOT / "runs" / "logs" / "find"
    directory.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s: %(message)s", "%H:%M:%S")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in (
        logging.StreamHandler(),
        logging.FileHandler(directory / f"{time.strftime('%Y%m%d-%H%M%S')}.log", encoding="utf-8"),
    ):
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def main(argv: list[str] | None = None) -> None:
    """用系统自带的 Python 运行：/usr/bin/python3 scripts/find_switch.py aa:bb:cc:dd:ee:ff

    找到后把 ip 打印到标准输出，再 ping 一下这个 ip 并记录延迟。
    ping 不通或延迟超过 150 ms 只记一条警告。MAC 不对或找不到 Switch 时以非 0 状态退出。
    """
    # ping 平均延迟超过这个值（毫秒）就提示网络太差
    max_ping_ms = 150

    args = sys.argv[1:] if argv is None else argv
    _init_log()
    if len(args) != 1:
        logging.error("要传 Switch 的 MAC 地址：find_switch.py aa:bb:cc:dd:ee:ff")
        sys.exit(1)
    switch_mac = args[0]
    if not re.fullmatch(r"[0-9a-fA-F]{1,2}([:-][0-9a-fA-F]{1,2}){5}", switch_mac):
        logging.error(
            f"mac 格式不对：{switch_mac!r}，应该是 aa:bb:cc:dd:ee:ff 这样的 6 段十六进制"
        )
        sys.exit(1)
    logging.info(f"正在查找 MAC 为 {switch_mac} 的 Switch ...")
    ip = find_switch(switch_mac)
    if ip is None:
        logging.error("找不到 Switch")
        sys.exit(1)
    logging.info(f"找到 Switch: {ip}")

    delay = ping(ip)
    if delay is None:
        logging.warning("ping 不通：确认 Switch 没休眠、和这台电脑在同一个局域网")
    elif delay > max_ping_ms:
        logging.warning(
            f"ping 平均 {delay:.0f} ms，超过 {max_ping_ms} ms，网络太差，流程会频繁超时"
        )
    else:
        logging.info(f"ping 平均 {delay:.0f} ms")
    print(ip)


if __name__ == "__main__":
    main()
