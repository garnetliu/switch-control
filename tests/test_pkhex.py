"""control_switch.pkhex：PKHeX API 客户端，用假的 urlopen 和 sleep，不发真实请求。"""

import email.message
import io
import json
import time
import urllib.error
import urllib.request
from types import TracebackType
from typing import Any, Self

import pytest

from control_switch.pkhex import Pkhex

API_URL = "http://example.invalid/api"

Outcome = dict[str, Any] | BaseException


class FakeResponse:
    """能用在 with 里、能给 json.load 读的响应。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = io.BytesIO(json.dumps(payload).encode())

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

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
    """按顺序返回响应或抛异常，并记下每次的请求。"""

    def __init__(self, outcomes: list[Outcome]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[urllib.request.Request] = []
        self.sleeps: list[float] = []

    def urlopen(
        self, request: urllib.request.Request, timeout: float | None = None
    ) -> FakeResponse:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(outcome)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def install(monkeypatch: pytest.MonkeyPatch, outcomes: list[Outcome]) -> FakeNetwork:
    network = FakeNetwork(outcomes)
    monkeypatch.setattr(urllib.request, "urlopen", network.urlopen)
    monkeypatch.setattr(time, "sleep", network.sleep)
    return network


def test_execute_returns_result_and_posts_code_and_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应是 {"result": 1}：返回 1，请求是发往 api_url 的 POST，内容里有 code 和 input。"""
    network = install(monkeypatch, [{"result": 1}])

    result = Pkhex(API_URL).execute("return 1;", {"a": 2})

    assert result == 1
    assert len(network.requests) == 1
    request = network.requests[0]
    assert request.get_method() == "POST"
    assert request.full_url == API_URL
    assert isinstance(request.data, bytes)
    assert json.loads(request.data) == {"code": "return 1;", "input": {"a": 2}}


def test_execute_missing_result_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应里既没有 error 也没有 result：返回 None。"""
    install(monkeypatch, [{}])

    assert Pkhex(API_URL).execute("code", {}) is None


def test_execute_error_payload_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应是 {"error": "x"}：抛 RuntimeError，报错里有 x。"""
    install(monkeypatch, [{"error": "x"}])

    with pytest.raises(RuntimeError, match="x"):
        Pkhex(API_URL).execute("code", {})


def test_execute_http_error_does_not_retry_and_includes_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """服务返回 HTTPError：只调一次 urlopen，抛 RuntimeError，报错里有响应内容。"""
    error = urllib.error.HTTPError(
        API_URL, 400, "Bad Request", email.message.Message(), io.BytesIO(b"compile failed: CS1002")
    )
    network = install(monkeypatch, [error])

    with pytest.raises(RuntimeError, match="compile failed: CS1002"):
        Pkhex(API_URL).execute("code", {})

    assert len(network.requests) == 1
    assert network.sleeps == []


def test_execute_url_error_always_retries_five_times_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一直抛 URLError：调 5 次 urlopen，sleep 依次 1、2、4、8，最后抛 RuntimeError，报错里有地址。"""
    network = install(monkeypatch, [urllib.error.URLError("refused") for _ in range(5)])

    with pytest.raises(RuntimeError, match=API_URL):
        Pkhex(API_URL).execute("code", {})

    assert len(network.requests) == 5
    assert network.sleeps == [1, 2, 4, 8]


def test_execute_succeeds_after_two_url_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """前两次 URLError、第 3 次正常：返回结果，sleep 是 1、2。"""
    network = install(
        monkeypatch,
        [urllib.error.URLError("a"), urllib.error.URLError("b"), {"result": "ok"}],
    )

    assert Pkhex(API_URL).execute("code", {}) == "ok"
    assert len(network.requests) == 3
    assert network.sleeps == [1, 2]


def test_api_url_from_env_when_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    """不传 api_url 且设置了 PKHEX_API_URL：用环境变量里的地址。"""
    monkeypatch.setenv("PKHEX_API_URL", "http://env.invalid/x")
    network = install(monkeypatch, [{"result": 1}])

    Pkhex().execute("code", {})

    assert network.requests[0].full_url == "http://env.invalid/x"


def test_api_url_defaults_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """不传 api_url、也没有 PKHEX_API_URL：用 DEFAULT_API_URL。"""
    monkeypatch.delenv("PKHEX_API_URL", raising=False)
    network = install(monkeypatch, [{"result": 1}])

    Pkhex().execute("code", {})

    assert network.requests[0].full_url == Pkhex.DEFAULT_API_URL


def test_api_url_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """PKHEX_API_URL 设成空值（.env 里写 `PKHEX_API_URL=`）时当作没配置，用 DEFAULT_API_URL。

    防的是：空值被当成地址，构造请求时抛 `ValueError: unknown url type: ''`，报错里不提
    PKHEX_API_URL。同一个 .env.example 里 `DISCORD_WEBHOOK_URL=` 就是用空值表示不配置，
    Notifier 也把空值当成没配。原来就有的问题。
    """
    monkeypatch.setenv("PKHEX_API_URL", "")
    network = install(monkeypatch, [{"result": 1}])

    Pkhex().execute("code", {})

    assert network.requests[0].full_url == Pkhex.DEFAULT_API_URL
