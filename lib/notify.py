"""通知：把消息发到 Discord 频道。只用标准库。

Webhook 地址写在 .env 的 DISCORD_WEBHOOK_URL。没有配置或者发送失败都只记日志，
不影响刷闪流程。另外提供看门狗：长时间没有日志时提醒可能卡住。
"""

import json
import mimetypes
import os
import threading
import time
import urllib.request
from pathlib import Path

from lib.log import last_log, log

_ENV_KEY = "DISCORD_WEBHOOK_URL"
# Discord 单条消息最多 2000 个字符
MAX_LENGTH = 2000
_TRUNCATED = "…（已截断）"
# 一条消息最多带多少个附件
MAX_FILES = 10
# 没配置 Webhook 时只提醒一次，免得每局战报都记一条
_warned_missing = False
_watchdog_started = False


def send(text: str, files: list[str | Path] | None = None) -> None:
    """发一条消息到 Discord，files 里的图片作为附件一起发。任何失败只记日志，不抛出。"""
    global _warned_missing
    url = os.environ.get(_ENV_KEY)
    if not url:
        if not _warned_missing:
            log(f"没有配置 {_ENV_KEY}，跳过通知", "WARNING")
            _warned_missing = True
        return
    if len(text) > MAX_LENGTH:
        text = text[: MAX_LENGTH - len(_TRUNCATED)] + _TRUNCATED
    paths = [Path(path) for path in (files or [])]
    paths = [path for path in paths if path.is_file()][:MAX_FILES]
    try:
        if paths:
            try:
                _post_files(url, text, paths)
            except Exception as error:  # noqa: BLE001 图片发不出去就退化成纯文字
                log(f"发送通知的图片失败，改发文字: {error}", "WARNING")
            else:
                return
        _post_json(url, text)
    except Exception as error:  # noqa: BLE001 通知失败不能影响主流程
        log(f"发送通知失败: {error}", "WARNING")


def _headers(content_type: str) -> dict[str, str]:
    return {"Content-Type": content_type, "User-Agent": "control-switch/0.1"}


def _post_json(url: str, text: str) -> None:
    body = json.dumps({"content": text}).encode()
    request = urllib.request.Request(url, data=body, headers=_headers("application/json"))
    with urllib.request.urlopen(request, timeout=5):
        pass


def _post_files(url: str, text: str, paths: list[Path]) -> None:
    """用 multipart/form-data 发文字和附件，附件字段名是 files[0]、files[1]……"""
    boundary = f"----control-switch-{os.urandom(8).hex()}"
    chunks: list[bytes] = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="payload_json"\r\n',
        b"Content-Type: application/json\r\n\r\n",
        json.dumps({"content": text}).encode(),
        b"\r\n",
    ]
    for index, path in enumerate(paths):
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="files[{index}]"; '
                    f'filename="{path.name}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        url,
        data=b"".join(chunks),
        headers=_headers(f"multipart/form-data; boundary={boundary}"),
    )
    with urllib.request.urlopen(request, timeout=20):
        pass


def start_watchdog(stall_seconds: float, interval: float = 30.0) -> None:
    """起一个后台线程，超过 stall_seconds 没有日志就提醒一次可能卡住。

    提醒之后要等新的日志才复位，同一个卡住状态只发一次。
    """
    global _watchdog_started
    if _watchdog_started:
        return
    _watchdog_started = True

    def watch() -> None:
        alerted = False
        while True:
            time.sleep(interval)
            last_time, last_message = last_log()
            if time.time() - last_time < stall_seconds:
                alerted = False
                continue
            if alerted:
                continue
            minutes = (time.time() - last_time) / 60
            send(f"可能卡住：{minutes:.0f} 分钟没有日志\n最后一条：{last_message[:500]}")
            alerted = True

    threading.Thread(target=watch, name="notify-watchdog", daemon=True).start()
