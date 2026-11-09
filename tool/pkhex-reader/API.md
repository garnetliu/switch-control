# PKHeX.Core HTTP API

这个服务让调用方提交 C# 脚本，脚本直接引用容器中的 `PKHeX.Core` 公共类和方法。它不是只解析 PK8 的固定命令行程序。

## 启动

在仓库根目录运行：

```sh
docker compose -f tool/pkhex-reader/compose.yaml up -d --build
```

服务只监听本机 `127.0.0.1:8787`。检查状态：

```sh
curl http://127.0.0.1:8787/health
```

`autostep/join.py` 从 Switch 读取租借候选时会调用此接口解析 PK8。开始自动冒险前，请确保 `switch-pkhex-api` 容器已启动；也可以用环境变量 `PKHEX_API_URL` 指定接口地址。

## 接口

- `GET /health`：服务状态及 PKHeX.Core 版本。
- `GET /api/v1/capabilities`：C# 脚本的引用、导入命名空间和输入变量。
- `POST /api/v1/execute`：在容器内执行 C# 脚本。脚本可调用 PKHeX.Core 的公共功能。

请求字段：

```json
{
  "code": "var pk = AsPK8(); return new { pk.Species, pk.ChecksumValid };",
  "dataHex": "可选的十六进制原始字节",
  "dataBase64": "可选的 Base64 原始字节",
  "input": { "可选": "任意 JSON 输入" }
}
```

脚本可直接使用 `PKHeX.Core` 命名空间，并可读取 `Input`、`Data`，或调用 `AsPK8()`。例如分析 PK8 合法性：

```csharp
var pk = AsPK8();
var legality = new LegalityAnalysis(pk);
return new { pk.Species, pk.ChecksumValid, legality.Parsed, legality.Valid };
```

响应中的对象会递归转换为 JSON。请求最大 64 MiB，脚本执行时间限制 60 秒。执行环境位于容器内，没有挂载宿主目录或 Docker socket。

## 容器管理

```sh
docker compose -f tool/pkhex-reader/compose.yaml ps
docker compose -f tool/pkhex-reader/compose.yaml logs -f
docker compose -f tool/pkhex-reader/compose.yaml down
```
