# control-switch

通过 WiFi 用电脑控制已装大气层的 Switch（sys-botbase，TCP 6000）。

## 安装

```bash
uv sync
```

复制 `.env.example` 为 `.env`，填上 Switch 的 MAC 地址（`SWITCH_MAC`）。

## 命令

命令都写在 `Makefile` 里。

```bash
make find
```

查找 Switch 的 ip，写入 `.env` 的 `SWITCH_IP`，并 ping 一下检查延迟。

```bash
make start
```

启动程序。
