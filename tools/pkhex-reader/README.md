# PKHeX 候选数据读取器

该容器使用 PKHeX.Core 的 `PK8` 解析器处理采样 JSON 中的 344 字节候选数据，并输出物种编号、校验和、加密常量及闪光状态。

在仓库根目录构建镜像：

```sh
docker build -t switch-pkhex-reader tools/pkhex-reader
```

运行时把采样文件挂载到容器：

```sh
docker run --rm \
  -v "/private/tmp/claude-503/-Users-garnet-projects-control-switch/0b278e1b-ea93-4ba0-9ec3-b36176ea8d10/scratchpad/memtest.json:/input/memtest.json:ro" \
  switch-pkhex-reader /input/memtest.json
```

镜像构建时从 PKHeX 官方仓库检出固定提交 `0660d1e1f4924b8478daec73281bb8071a82ad19`。

要重新采集一局租借阶段数据，可在 USB botbase 已连接时运行：

```sh
.venv/bin/python tools/pkhex-reader/capture_lair.py
```

脚本会重启游戏并开始一局极巨大冒险；冒险途中重启会产生游戏内罚款。采样结束后，使用上面的 `docker run` 命令解析 `/private/tmp/switch-lair-pkhex.json`。
