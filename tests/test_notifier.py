"""control_switch.notifier：Discord 通知，用假的 urlopen 和 sleep，不发真实请求。"""

import json
import logging
import threading
import time
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest

from control_switch.notifier import Notifier

WEBHOOK = "http://example.invalid/webhook"

Outcome = BaseException | None


class FakeResponse:
    """能用在 with 里的响应。"""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class FakeNetwork:
    """按顺序成功（None）或抛异常，记下每次请求和每次 sleep 的秒数。超出顺序的调用都成功。"""

    def __init__(self, outcomes: list[Outcome]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[urllib.request.Request] = []
        self.sleeps: list[float] = []

    def urlopen(
        self, request: urllib.request.Request, timeout: float | None = None
    ) -> FakeResponse:
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if outcome is not None:
            raise outcome
        return FakeResponse()

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def install(monkeypatch: pytest.MonkeyPatch, outcomes: list[Outcome] | None = None) -> FakeNetwork:
    network = FakeNetwork(outcomes or [])
    monkeypatch.setattr(urllib.request, "urlopen", network.urlopen)
    monkeypatch.setattr(time, "sleep", network.sleep)
    return network


def make_notifier(url: str | None = WEBHOOK) -> Notifier:
    if url is None:
        return Notifier()
    return Notifier(webhook_url=url)


def body_of(request: urllib.request.Request) -> bytes:
    assert isinstance(request.data, bytes)
    return request.data


def make_files(directory: Path, count: int) -> list[Path]:
    paths = [directory / f"img{i}.png" for i in range(count)]
    for path in paths:
        path.write_bytes(b"PNGDATA")
    return paths


def test_send_without_webhook_sends_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有配置地址：不发请求。"""
    network = install(monkeypatch)

    make_notifier(None)._send("hi", None)

    assert network.requests == []


def test_send_without_webhook_warns_only_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """没有配置地址：连着调两次，只记一条警告。"""
    install(monkeypatch)
    notifier = make_notifier(None)

    with caplog.at_level(logging.WARNING):
        notifier._send("a", None)
        notifier._send("b", None)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "DISCORD_WEBHOOK_URL" in warnings[0].getMessage()


def test_send_truncates_text_over_2000_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    """正文超过 2000 字：发出去的正文正好 2000 字，结尾是「…（已截断）」。"""
    network = install(monkeypatch)

    make_notifier()._send("a" * 2500, None)

    content = json.loads(body_of(network.requests[0]))["content"]
    assert len(content) == 2000
    assert content.endswith("…（已截断）")


def test_send_text_of_exactly_2000_chars_is_not_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    """正文正好 2000 字：原样发出，不截断。"""
    network = install(monkeypatch)

    make_notifier()._send("a" * 2000, None)

    assert json.loads(body_of(network.requests[0]))["content"] == "a" * 2000


def test_send_without_files_posts_json_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有附件：Content-Type 是 application/json，内容是 {"content": 正文}，发往配置的地址。"""
    network = install(monkeypatch)

    make_notifier()._send("你好", None)

    request = network.requests[0]
    assert request.full_url == WEBHOOK
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(body_of(request)) == {"content": "你好"}


def test_send_with_files_posts_multipart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """有附件：Content-Type 是 multipart/form-data，里面有 payload_json 和 files[0]、files[1]。"""
    network = install(monkeypatch)
    files = make_files(tmp_path, 2)

    make_notifier()._send("pic", files)

    request = network.requests[0]
    content_type = request.get_header("Content-type")
    assert content_type is not None
    assert content_type.startswith("multipart/form-data; boundary=")
    body = body_of(request)
    assert b'name="payload_json"' in body
    assert b'name="files[0]"' in body
    assert b'name="files[1]"' in body
    assert b'name="files[2]"' not in body
    assert b'{"content": "pic"}' in body
    assert b'filename="img0.png"' in body
    assert b"Content-Type: image/png" in body
    assert b"PNGDATA" in body


def test_send_with_files_drops_nonexistent_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """不存在的文件被丢掉，只带存在的那个。"""
    network = install(monkeypatch)
    existing = make_files(tmp_path, 1)[0]

    make_notifier()._send("pic", [tmp_path / "missing.png", existing])

    body = body_of(network.requests[0])
    assert b'name="files[0]"; filename="img0.png"' in body
    assert b'name="files[1]"' not in body
    assert b"missing.png" not in body


def test_send_with_only_nonexistent_files_posts_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """附件全都不存在：改发只有文字的请求。"""
    network = install(monkeypatch)

    make_notifier()._send("pic", [tmp_path / "missing.png"])

    assert network.requests[0].get_header("Content-type") == "application/json"


def test_send_with_more_than_10_files_keeps_first_10(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """附件超过 10 个：只带前 10 个。"""
    network = install(monkeypatch)
    files = make_files(tmp_path, 12)

    make_notifier()._send("pic", files)

    body = body_of(network.requests[0])
    assert b'name="files[9]"; filename="img9.png"' in body
    assert b'name="files[10]"' not in body
    assert b"img10.png" not in body


def test_send_falls_back_to_text_only_when_reading_file_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """读附件时出 OSError：改发只有文字的请求。"""
    network = install(monkeypatch)
    files = make_files(tmp_path, 1)

    def broken_read_bytes(self: Path) -> bytes:
        raise OSError("disk error")

    monkeypatch.setattr(Path, "read_bytes", broken_read_bytes)

    make_notifier()._send("pic", files)

    request = network.requests[0]
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(body_of(request)) == {"content": "pic"}


def test_send_retries_10_times_when_always_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    """urlopen 一直抛异常：一共调 10 次，sleep 调 9 次、每次 30 秒，不往外抛异常。"""
    network = install(monkeypatch, [OSError("down") for _ in range(10)])

    make_notifier()._send("hi", None)

    assert len(network.requests) == 10
    assert network.sleeps == [30] * 9


def test_send_stops_retrying_after_success_on_third_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第 3 次成功：只调 3 次 urlopen，sleep 2 次。"""
    network = install(monkeypatch, [OSError("a"), OSError("b"), None])

    make_notifier()._send("hi", None)

    assert len(network.requests) == 3
    assert network.sleeps == [30, 30]


def test_send_everyone_prefixes_text_with_at_everyone(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_everyone("x")：等 notifier 线程结束后，发出去的正文是 "@everyone x"。"""
    network = install(monkeypatch)

    make_notifier().send_everyone("x")
    for thread in threading.enumerate():
        if thread.name == "notifier":
            thread.join(timeout=5)

    assert len(network.requests) == 1
    assert json.loads(body_of(network.requests[0])) == {"content": "@everyone x"}


def test_send_runs_in_background_thread_named_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """send 在名字是 notifier 的后台线程里发消息。"""
    network = install(monkeypatch)

    make_notifier().send("x")
    for thread in threading.enumerate():
        if thread.name == "notifier":
            thread.join(timeout=5)

    assert json.loads(body_of(network.requests[0])) == {"content": "x"}
