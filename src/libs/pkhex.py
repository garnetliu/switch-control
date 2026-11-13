"""调用本机的 PKHeX.Core API：把一段 C# 脚本和输入发过去执行，拿回结果。"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class Pkhex:
    """PKHeX.Core API 的客户端。服务用 docker/pkhex-reader 启动。"""

    DEFAULT_API_URL = "http://127.0.0.1:8787/api/v1/execute"
    RETRY_DELAYS = (1, 2, 4, 8)

    def __init__(self, api_url: str | None = None):
        self._api_url = api_url or os.environ.get("PKHEX_API_URL", self.DEFAULT_API_URL)

    def execute(self, code: str, data: dict[str, Any]) -> Any:
        """执行一段 C# 脚本，data 在脚本里是 Input，返回脚本 return 的值。

        连不上会重试几次，还是不行或者脚本报错抛 RuntimeError。
        """
        body = json.dumps({"code": code, "input": data}).encode()
        request = urllib.request.Request(
            self._api_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            for attempt in range(len(self.RETRY_DELAYS) + 1):
                try:
                    with urllib.request.urlopen(request, timeout=15) as response:
                        payload = json.load(response)
                    break
                except urllib.error.HTTPError as error:
                    # 服务有回应，是脚本本身不对（比如编译不过），重试没有用
                    detail = error.read().decode(errors="replace")
                    raise RuntimeError(f"PKHeX API 执行脚本失败：{detail}") from error
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    ConnectionError,
                    json.JSONDecodeError,
                ):
                    if attempt == len(self.RETRY_DELAYS):
                        raise
                    time.sleep(self.RETRY_DELAYS[attempt])
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(
                f"无法调用 PKHeX API（{self._api_url}），请确认 switch-pkhex-api 容器正在运行"
            ) from exc
        if "error" in payload:
            raise RuntimeError(f"PKHeX API 解析失败：{payload['error']}")
        return payload.get("result")
