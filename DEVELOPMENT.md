# Waycast 开发者文档

本文面向**开发与扩展 Waycast 的人**：关键设计点、Wire 协议与模块编写、工具、测试与代码结构。日常安装、配置与运行服务请看用户文档 [README.md](README.md)；术语见 [GLOSSARY.md](GLOSSARY.md)，架构决策见 [docs/adr/](docs/adr/)（设计蓝图见 [docs/design/overall-architecture.md](docs/design/overall-architecture.md)）。在本仓库开发前另须遵守 [AGENTS.md](AGENTS.md)。

## 架构与关键设计点

### 关键设计点

- **单一的 WebSocket 通道**：一条 `/ws/modules` 连接，首帧必须是 capability advertisement；同一连接可同时作为输入、输出或两者（A25）。模块名是连接身份，重连幂等替换旧连接；断开时从 capability catalog 移除。
- **能力注册**：capability 帧声明模块的唯一名、自然语言描述（输入）或 JSON Schema + 语义描述（输出），以及可选的 status 查询通道（A19）。这些描述自动成为 Agent 系统提示词的一部分。
- **状态查询可选**：模块只有宣告 `status.enabled` 才获得 `status_<module>` 工具（经 capability-bridge middleware 暴露，非 MCP server）；无状态可查的模块不宣告，也不生成工具。
- **JSON 输出优先，否则自动回退**：Pydantic schema 直接传给 `create_agent` 的 `response_format`，LangChain v1 的 `AutoStrategy` 自动探测——provider 原生支持结构化输出走 `ProviderStrategy`，否则回退 `ToolStrategy`（ADR-0003）。
- **背压**：所有输入（无论来自哪个模块）进入同一个有界 `asyncio.Queue`，单消费者 worker 逐条处理；队列满时生产者阻塞（ADR-0006）。
- **无输出模块时不空转**：worker 每次取输入前先看 capability catalog —— 没有已连接的输出模块时，直接丢弃该条输入（在 `/results` 记录 `last_skipped`），不调用真实模型；有输出模块后才执行 Invocation。
- **输出结果一次性注入**：Invocation 开始前 drain 待送达的 Output result，由 capability-bridge 渲染进动态系统提示词（catalog/status 之后、rules 之前），恰好吃掉一次、不进对话历史；连续相同结果聚合计数（ADR-0002 / ADR-0013）。
- **历史由内置摘要管理**：全局单线程历史逼近 `("tokens", 60000)` 或 `("messages", 240)` 时，LangChain 内置 `SummarizationMiddleware`（主模型）自动摘要压缩、保留最近 40 条（ADR-0005 / ADR-0013）；Unified input 以 human 消息进入历史。
- **连接 token**：`WAYCAST_HUB_TOKEN` 共享密钥，模块在 WebSocket 握手（query 参数）时提交，校验通过才受理（A8）。token 为空时关闭鉴权。

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

真实模型测试覆盖结构化输出（units 可为空）、多轮工具调用（模型必须调用真实 `get_time`）、可选状态工具往返、输出结果一次性进入下一轮（ADR-0002 / ADR-0013）。

## 项目结构

```
src/waycast/
  agent.py         Agent：create_agent + 结构化输出 + 单元派发 + 开轮 drain feed + 内置摘要
  bridge.py        CapabilityBridge middleware：系统提示词装配（含feed临时注入） + 状态工具 + 单元路由
  capabilities.py  CapabilityCatalog：已连接模块的能力目录
  cli.py           waycast serve 入口
  config.py        环境变量 / .env 配置，构建 ChatOpenAI
  hub.py           WebSocket Hub：模块连接、帧路由、状态往返
  wire.py          Wire 协议：JSON 帧信封 + capability 校验
  protocols.py     载荷模型：UnifiedInput / OutputUnit
  service.py       FastAPI + 有界背压队列 + 单消费者 worker
  state.py         OutputResult / 一次性feed / results_as_text 聚合渲染
  prompt_config.py 读取纯文本用户提示词，与模块目录、feed、规则拼接
  tools.py         内置真实工具（get_time）
examples/
  waycast_examples/ 参考模块客户端（cron_source / echo_bell / log_sink）+ connect_module
tests/
  demo_tools.py    演示/测试占位工具（不进入生产包）
  test_*_real.py   真实模型冒烟测试（--run-real-model）
docs/adr/          全部架构决策（0001-0013）
docs/design/       设计蓝图（overall-architecture.md）
GLOSSARY.md        术语表
DEVELOPMENT.md     本文（开发者文档）
```
