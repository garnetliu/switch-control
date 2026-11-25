#!/usr/bin/env python3
"""TP-LINK 商用(SLP)路由器登录 + 只读查询工具。

适配 TL-R5009PE-AC v1.0 这类用 get_encrypt_info 的 SLP 固件。
凭据从项目 .env 读（ROUTER_URL / ROUTER_USER / ROUTER_PASSWORD）。

登录原理（固件 encrypt_type 返回 "-3"）：
  1. POST / {"method":"do","user_management":{"get_encrypt_info":null}} 拿 nonce
  2. 口令 = securityEncode(密码, "RDpbLfCPsJZ7fiv", 固定字典)
  3. POST / {"method":"do","login":{"username":..,"password":口令}} 拿 stok
  4. 之后查询 POST 到 /stok=<stok>/ds，body 形如 {"模块":{"name":"表"},"method":"get"}

用法：
  python3 scripts/router.py                      # 打印一组常用状态（WAN/LAN/型号）
  python3 scripts/router.py '{"network":{"name":"wan_status"},"method":"get"}'
  python3 scripts/router.py --stok               # 只登录，打印 stok
"""

import json
import os
import sys
import urllib.request

DICT = (
    "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4rBL3cD02KZciXTys"
    "VXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro510qXeU07kV57fQMc8L6aLgMLwygtc0F"
    "10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZLEal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW"
)
KEY = "RDpbLfCPsJZ7fiv"


def load_env():
    env = {}
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


def security_encode(e, t, o):
    r = len(o)
    out = []
    for c in range(max(len(e), len(t))):
        u = d = 187
        if c >= len(e):
            d = ord(t[c])
        elif c >= len(t):
            u = ord(e[c])
        else:
            u, d = ord(e[c]), ord(t[c])
        out.append(o[(u ^ d) % r])
    return "".join(out)


def post(base, path, obj, timeout=10):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json", "Referer": base + "/"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def login(base, user, pwd):
    post(base, "/", {"method": "do", "user_management": {"get_encrypt_info": None}})
    enc = security_encode(pwd, KEY, DICT)
    res = post(base, "/", {"method": "do", "login": {"username": user, "password": enc}})
    stok = res.get("stok")
    if not stok:
        raise SystemExit(f"登录失败: {json.dumps(res, ensure_ascii=False)}")
    return stok


def query(base, stok, body):
    return post(base, f"/stok={stok}/ds", body)


def main():
    # 绕开代理，直连路由器
    for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ.pop(k, None)
    env = load_env()
    base = os.environ.get("ROUTER_URL", env.get("ROUTER_URL", "http://192.168.0.1")).rstrip("/")
    user = os.environ.get("ROUTER_USER", env.get("ROUTER_USER", "admin"))
    pwd = os.environ.get("ROUTER_PASSWORD", env.get("ROUTER_PASSWORD"))
    if not pwd:
        raise SystemExit("缺少 ROUTER_PASSWORD（.env 或环境变量）")

    stok = login(base, user, pwd)

    args = [a for a in sys.argv[1:]]
    if "--stok" in args:
        print(stok)
        return
    if args:
        print(json.dumps(query(base, stok, json.loads(args[0])), ensure_ascii=False, indent=2))
        return

    # 默认：打印一组常用只读状态
    for label, body in (
        ("型号", {"device_info": {"name": "info"}, "method": "get"}),
        ("WAN", {"network": {"name": "wan_status"}, "method": "get"}),
        ("LAN口通断", {"network": {"name": "lan_status"}, "method": "get"}),
        ("接口模式", {"network": {"name": "if_mode"}, "method": "get"}),
    ):
        try:
            print(f"== {label} ==")
            print(json.dumps(query(base, stok, body), ensure_ascii=False))
        except Exception as ex:
            print("  查询失败:", ex)


if __name__ == "__main__":
    main()
