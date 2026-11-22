"""通知：把消息发到 Discord 频道。只用标准库。

Webhook 地址写在 .env 的 DISCORD_WEBHOOK_URL。没有配置或者发送失败都只记日志，
不影响刷闪流程。
"""

import json
import logging
import mimetypes
import os
import threading
import time
import urllib.request
from collections.abc import Sequence
from pathlib import Path


class Notifier:
    """往 Discord 发消息，可以带图片附件。"""

    # Discord 单条消息最多 2000 个字符，一条消息最多 10 个附件
    MAX_LENGTH = 2000
    MAX_FILES = 10
    TRUNCATED = "…（已截断）"
    # 发不出去时最多发几次，每两次之间等几秒
    RETRIES = 10
    RETRY_WAIT = 30
    # 发文字、发图片的网络请求最多等几秒
    TEXT_TIMEOUT = 5
    FILE_TIMEOUT = 20

    def __init__(self):
        # Discord 频道的 Webhook 地址，没配置是 None
        self._url = os.environ.get("DISCORD_WEBHOOK_URL")
        # 没配置 Webhook 时只提醒一次，免得每局都记一条
        self._warned_missing = False

    def send(self, text: str, files: Sequence[str | Path] | None = None) -> None:
        """在后台线程里发一条消息，不等发完就返回。files 里的图片作为附件一起发。

        发不出去会重试，最多发 RETRIES 次，每两次之间等 RETRY_WAIT 秒。
        线程不是守护线程：程序要退出时会等它发完或者重试完。
        """
        threading.Thread(target=self._send, args=(text, files), name="notifier").start()

    def send_everyone(self, text: str, files: Sequence[str | Path] | None = None) -> None:
        """发一条 @全体 的消息：正文前面加上 @everyone，其它和 send 一样。"""
        self.send(f"@everyone {text}", files)

    def _send(self, text: str, files: Sequence[str | Path] | None) -> None:
        """发一条消息，任何失败只记日志，不抛出。"""
        url = self._url
        if not url:
            if not self._warned_missing:
                logging.warning("没有配置 DISCORD_WEBHOOK_URL，跳过通知")
                self._warned_missing = True
            return
        if len(text) > self.MAX_LENGTH:
            text = text[: self.MAX_LENGTH - len(self.TRUNCATED)] + self.TRUNCATED
        paths = [Path(path) for path in (files or [])]
        paths = [path for path in paths if path.is_file()][: self.MAX_FILES]
        # 请求只组一次：图片现在就读进来，重试时图片文件可能已经被下一局的初始化删掉了
        request, timeout = self._json_request(url, text), self.TEXT_TIMEOUT
        if paths:
            try:
                request, timeout = self._files_request(url, text, paths), self.FILE_TIMEOUT
            except OSError as error:
                logging.warning(f"读不到通知的图片，改发文字: {error}")
        for attempt in range(1, self.RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout):
                    return
            except Exception as error:  # 通知失败不能影响主流程
                logging.warning(f"发送通知失败（第 {attempt} 次）: {error}")
            if attempt < self.RETRIES:
                time.sleep(self.RETRY_WAIT)
        logging.warning(f"通知发了 {self.RETRIES} 次都没发出去，放弃")

    @staticmethod
    def _headers(content_type: str) -> dict[str, str]:
        return {"Content-Type": content_type, "User-Agent": "control-switch/0.1"}

    def _json_request(self, url: str, text: str) -> urllib.request.Request:
        """只有文字的请求。"""
        body = json.dumps({"content": text}).encode()
        return urllib.request.Request(url, data=body, headers=self._headers("application/json"))

    def _files_request(self, url: str, text: str, paths: list[Path]) -> urllib.request.Request:
        """文字和图片放在同一个请求里（multipart/form-data），Discord 上是一条消息。

        附件字段名是 files[0]、files[1]……
        """
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
        return urllib.request.Request(
            url,
            data=b"".join(chunks),
            headers=self._headers(f"multipart/form-data; boundary={boundary}"),
        )
