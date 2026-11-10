"""通知：把消息发到 Discord 频道。只用标准库。

Webhook 地址写在 .env 的 DISCORD_WEBHOOK_URL。没有配置或者发送失败都只记日志，
不影响刷闪流程。
"""

import json
import logging
import mimetypes
import os
import urllib.request
from collections.abc import Sequence
from pathlib import Path


class Notifier:
    """往 Discord 发消息，可以带图片附件。"""

    # Discord 单条消息最多 2000 个字符，一条消息最多 10 个附件
    MAX_LENGTH = 2000
    MAX_FILES = 10
    TRUNCATED = "…（已截断）"
    # 发文字、发图片的网络请求最多等几秒
    TEXT_TIMEOUT = 5
    FILE_TIMEOUT = 20

    def __init__(self):
        # Discord 频道的 Webhook 地址，没配置是 None
        self._url = os.environ.get("DISCORD_WEBHOOK_URL")
        # 没配置 Webhook 时只提醒一次，免得每局都记一条
        self._warned_missing = False

    def send(self, text: str, files: Sequence[str | Path] | None = None) -> None:
        """发一条消息，files 里的图片作为附件一起发。任何失败只记日志，不抛出。"""
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
        try:
            if paths:
                try:
                    self._post_files(url, text, paths)
                except Exception as error:  # 图片发不出去就退化成纯文字
                    logging.warning(f"发送通知的图片失败，改发文字: {error}")
                else:
                    return
            self._post_json(url, text)
        except Exception as error:  # 通知失败不能影响主流程
            logging.warning(f"发送通知失败: {error}")

    @staticmethod
    def _headers(content_type: str) -> dict[str, str]:
        return {"Content-Type": content_type, "User-Agent": "control-switch/0.1"}

    def _post_json(self, url: str, text: str) -> None:
        body = json.dumps({"content": text}).encode()
        request = urllib.request.Request(url, data=body, headers=self._headers("application/json"))
        with urllib.request.urlopen(request, timeout=self.TEXT_TIMEOUT):
            pass

    def _post_files(self, url: str, text: str, paths: list[Path]) -> None:
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
            headers=self._headers(f"multipart/form-data; boundary={boundary}"),
        )
        with urllib.request.urlopen(request, timeout=self.FILE_TIMEOUT):
            pass
