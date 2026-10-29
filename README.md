# Waycast

一个基于 LangChain v1 的微服务化 Agent：输入/输出模块是独立服务，通过 WebSocket 连接到 Agent（枢纽），以统一 JSON Wire 协议交换帧。每条输入触发一次 Agent 调用（Invocation）；Agent 通过多轮真实模型工具调用产出 JSON 输出单元列表（可为空），派发给已连接的输出模块连接（fire-and-forget）；每个派发立刻返回输出结果，该结果随下一轮输入一起进入下一轮调用（ADR-0002）。

## 架构

Waycast 的核心（`src/`）只含本体：协议、Agent、hub、service、wire 帧模型。模块一律作为网络客户端运行在进程外（ADR-0008），`src/` 中不存在任何 mock 或占位。

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  输入模块     │    │  Agent/Hub  │    │  输出模块     │
│ (独立服务)    │───▶│  (Waycast)  │───▶│ (独立服务)    │
└─────────────┘    │  /ws/modules │    └─────────────┘
                   └─────────────┘
  所有帧走同一条多路复用 WebSocket 连接（A25）
  capability / input / output_unit / result / status_query / status_result
```

### 核心概念

- **Input module**：把外部信号转成统一 `UnifiedInput`（`content` + `source` + `metadata`）的独立服务，经 WebSocket 发送 `input` 帧；每条输入恰好触发一次 Invocation。
- **Agent**：对每条输入运行一次多轮工具调用（内置真实工具 + 可接入 MCP 工具），产出结构化 JSON：`{ "units": [ { "module": "...", "payload": {...} }, ... ] }`，`units` 可为空。
- **Output module**：连接时声明自己接受的 JSON Schema 与语义描述；收到 `output_unit` 帧后立即返回 `result` 帧（成功/失败）。Agent 在派发前按 schema 校验（ADR-0008）。
- **闭环**：模块返回的 `result` 帧累积进全局记忆，随下一轮输入作为消息重新进入 Agent（ADR-0002）。
- **Global memory**：所有输入累积到同一条对话历史（固定 `thread_id` + `InMemorySaver`），单消费者逐条处理，无会话隔离（ADR-0005）。

### 关键设计点

- **单一的 WebSocket 通道**：一条 `/ws/modules` 连接，首帧必须是 capability advertisement；同一连接可同时作为输入、输出或两者（A25）。模块名是连接身份，重连幂等替换旧连接；断开时从 capability catalog 移除。
- **能力注册**：capability 帧声明模块的唯一名、自然语言描述（输入）或 JSON Schema + 语义描述（输出），以及可选的 status 查询通道（A19）。这些描述自动成为 Agent 系统提示词的一部分。
- **状态查询可选**：模块只有宣告 `status.enabled` 才获得 `status_<module>` 工具（经 capability-bridge middleware 暴露，非 MCP server）；无状态可查的模块不宣告，也不生成工具。
- **JSON 输出优先，否则自动回退**：Pydantic schema 直接传给 `create_agent` 的 `response_format`，LangChain v1 的 `AutoStrategy` 自动探测——provider 原生支持结构化输出走 `ProviderStrategy`，否则回退 `ToolStrategy`（ADR-0003）。
- **背压**：所有输入（无论来自哪个模块）进入同一个有界 `asyncio.Queue`，单消费者 worker 逐条处理；队列满时生产者阻塞（ADR-0006）。
- **无输出模块时不空转**：worker 每次取输入前先看 capability catalog —— 没有已连接的输出模块时，直接丢弃该条输入（在 `/results` 记录 `last_skipped`），不调用真实模型；有输出模块后才执行 Invocation。
- **连接 token**：`WAYCAST_HUB_TOKEN` 共享密钥，模块在 WebSocket 握手（query 参数）时提交，校验通过才受理（A8）。token 为空时关闭鉴权。

## 快速开始

### 安装

依赖用 [uv](https://docs.astral.sh/uv/) 管理，Python ≥ 3.12：

```bash
uv sync
```

### 配置

复制 `.env.example` 为 `.env` 并填入真实凭据（`.env` 已被 `.gitignore` 忽略）：

```bash
export WAYCAST_BASE_URL="https://your-provider.example.com/v1"   # 或 OPENAI_BASE_URL
export WAYCAST_API_KEY="sk-..."                                  # 或 OPENAI_API_KEY
export WAYCAST_MODEL="deepseek-v4-flash"                          # 可选，默认 gpt-4o-mini
export WAYCAST_HUB_TOKEN=""                                       # 可选，模块连接 token（空则关闭鉴权）
```

其他可选变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WAYCAST_QUEUE_SIZE` | `100` | 输入队列容量（背压上限） |
| `WAYCAST_HOST` | `0.0.0.0` | 监听地址 |
| `WAYCAST_PORT` | `8000` | 监听端口 |
| `WAYCAST_THREAD_ID` | `waycast-global` | 全局记忆的 thread_id |
| `WAYCAST_AGENT_CONFIG` | `waycast.prompt.txt` | 用户系统提示词文件路径（纯文本） |

### 自定义 Agent 系统提示词

你可以直接写 **一整段纯文本** 作为 Agent 系统提示词的用户部分。默认读取项目根目录的 `waycast.prompt.txt`（可用环境变量 `WAYCAST_AGENT_CONFIG` 指定路径），文件内容原样读入，无需 TOML、转义或字段结构：

```text
你是一位天气预报助手。

使用场景：每天早晨推送天气与穿衣建议。

注意：
1. 务必先调用天气工具再回复；
2. 回复要简洁，避免啰嗦。
```

文件内容拼在自动生成的 capability catalog（每个连接模块的 `describe` 与 JSON Schema）之前，构成最终系统提示词：

```
[固定 base prompt] + [你的纯文本提示词] + [自动生成的模块目录 + schema + 状态工具] + [默认规则]
```

协议规范始终保留在提示词里；你只写角色、场景与行为要求。文件缺失或为空时，系统提示词保持默认不变。

### 启动服务

```bash
uv run waycast serve
```

服务提供：

- `WS /ws/modules` —— 模块连接唯一入口（所有输入经模块 `input` 帧进入）。
- `GET /health` —— 健康检查，返回 `queue_size`。
- `GET /results` —— 最近一次调用的完整结果（units、各派发的 OutputResult）、`pending_output_results`、已连接模块与队列大小；无输出模块时被跳过的输入记录在 `last_skipped`。

### 运行参考模块

启动 hub 后，在另一个终端用示例模块连接它（`--hub` 指向 hub 地址、`--token` 与 `WAYCAST_HUB_TOKEN` 一致）：

```bash
# 输入模块：每 60 秒推送一条当前 UTC 时间
PYTHONPATH=src:examples .venv/bin/python -m waycast_examples.cron_source --hub ws://127.0.0.1:8000 --interval 60
# 输出模块：接收 units 写日志
PYTHONPATH=src:examples .venv/bin/python -m waycast_examples.log_sink --hub ws://127.0.0.1:8000
# 输入+输出、带状态查询的演示模块（stdin 输入、stdout 回声）
PYTHONPATH=src:examples .venv/bin/python -m waycast_examples.echo_bell --hub ws://127.0.0.1:8000
```

hub 端口不是 8000 时用 `--hub ws://127.0.0.1:<port>` 指定；配了 `WAYCAST_HUB_TOKEN` 时每个模块都带上同样的 `--token`。

## 编写自己的模块

模块是独立的 WebSocket 客户端。协议由两部分组成：`waycast.wire`（帧信封）与 `waycast.protocols`（载荷模型）。参考实现见 [examples/waycast_examples/](examples/waycast_examples/)（`client.py` 提供 `connect_module` 上下文管理器，处理连接、token、capability 握手与确认）。

```python
from waycast_examples.client import connect_module
from waycast.wire import make_frame, parse_frame

CAPABILITY = {
    "name": "alert",
    "kind": "output",
    "output": {
        "schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}, "severity": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
        "description": "向指定接收人发送告警（message + severity）",
    },
}

async with connect_module(hub_url="ws://127.0.0.1:8000", token="your-hub-token", capability=CAPABILITY) as ws:
    async for raw in ws:
        frame = parse_frame(raw)
        if frame.type == "output_unit":
            # 真实派发逻辑（HTTP、队列、回调等）
            await ws.send(make_frame("result", "alert", {"module": "alert", "status": "ok", "detail": "sent"}).model_dump_json())
```

关键点：

- **首帧必须是 capability**，否则连接被拒绝（`4400`）。
- **kind**：`input` / `output` / `both`，同一连接可同时承担输入与输出（A25）。
- **status 可选**：模块宣告 `status.enabled: true` 后，Agent 的模型会获得 `status_<module>` 工具；收到 `status_query` 帧时返回 `status_result` 帧（`request_id` 回填）。
- **重连幂等**：同名模块重连会替换旧连接；断开即从目录移除，Agent 提示词与派发路由立即反映（A20）。

## 内置真实工具与测试化占位

- **工具**：[src/waycast/tools.py](src/waycast/tools.py) 只内置真实工具 `get_time`；演示/测试用的占位工具（`echo`、`look_up_weather`、`store_blob`、`notify`、`emit_seen_url`，含 mock 天气与进程内副作用）在 [tests/demo_tools.py](tests/demo_tools.py)，仅用于测试，不进入生产包（AGENTS.md）。
- **MCP 工具接入**：通过 `Agent(tools=[...])` 参数注入（ADR-0004）。

## 测试

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

路由层测试（wire 帧、capability 目录、hub 帧路由、prompt 拼接）离线全绿，不触网。涉及真实模型行为的测试标记 `real_model`，默认跳过，需要网络与 `.env` 凭据时显式运行：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_agent_real.py -q --run-real-model
```

真实模型测试覆盖结构化输出（units 可为空）、多轮工具调用（模型必须调用真实 `get_time`）、可选状态工具往返、输出结果进入下一轮（ADR-0002）。

## 项目结构

```
src/waycast/
  agent.py         Agent：create_agent + 结构化输出 + 单元派发 + 结果记忆
  bridge.py        CapabilityBridge middleware：系统提示词装配 + 状态工具 + 单元路由
  capabilities.py  CapabilityCatalog：已连接模块的能力目录
  cli.py           waycast serve 入口
  config.py        环境变量 / .env 配置，构建 ChatOpenAI
  hub.py           WebSocket Hub：模块连接、帧路由、状态往返
  wire.py          Wire 协议：JSON 帧信封 + capability 校验
  protocols.py     载荷模型：UnifiedInput / OutputUnit
  service.py       FastAPI + 有界背压队列 + 单消费者 worker
  prompt_config.py 读取纯文本用户提示词，与模块目录拼接
  tools.py         内置真实工具（get_time）
examples/
  waycast_examples/ 参考模块客户端（cron_source / echo_bell / log_sink）+ connect_module
tests/
  demo_tools.py    演示/测试占位工具（不进入生产包）
  test_*_real.py   真实模型冒烟测试（--run-real-model）
docs/adr/          全部架构决策（0001-0008）
GLOSSARY.md        术语表
```
