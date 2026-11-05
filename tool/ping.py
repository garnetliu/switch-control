from __future__ import annotations

import re
import subprocess

from lib.log import log


def ping(ip: str, count: int = 4, timeout_ms: int = 1000) -> float | None:
    """ping 一个地址，返回平均延迟（毫秒）。一个包都没收到返回 None。

    调用系统的 ping 命令，解析的是 macOS 输出的汇总行。
    没收到包时，把 ping 命令的原始输出记成一条 WARNING，方便查原因。
    tool/find_switch.py 会导入这个文件，它要用系统 Python 3.9 运行，所以只能用标准库。

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
        log(
            f"ping {ip} 没有收到回复，返回码 {result.returncode}，"
            f"输出 {result.stdout!r}，错误 {result.stderr!r}",
            "WARNING",
        )
        return None
    return float(match.group(1))
