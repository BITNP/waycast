# Waycast

一个基于 LangChain v1 的可插拔 Agent 服务：任意输入模块产生统一输入，每一条输入触发一次 Agent 调用；Agent 通过与真实 LLM 的多轮工具调用，产出一个 JSON 对象——它是任意输出模块可接受内容的组合（也可以为空，表示什么都不做）；输出模块收到后立即返回一个结果（fire-and-forget），该结果会随下一轮输入一起进入下一轮调用。

## 它解决什么问题

Waycast 把“输入”和“输出”都做成可插拔模块，统一走一套协议：

- **输入模块**（Input module）把外部信号转成统一的 `UnifiedInput` 结构（`content` + `source` + `metadata`），每次输入固定触发一次调用（Invocation）。
- **Agent** 拿到输入后，可以多轮调用工具（内置 demo 工具，也可接入 MCP 工具），最终输出一个 JSON 对象：`{ "units": [ { "module": "...", "payload": {...} }, ... ] }`。`units` 可以同时包含任意输出模块的组合，也可以为空。
- **输出模块**（Output module）向 Agent 注册时声明自己接受的 JSON schema。Agent 严格按 schema 校验后再派发（fire-and-forget），模块立刻返回 `OutputResult`（成功/失败或文字信息）。
- **闭环**：每次派发产生的 `OutputResult` 会作为系统消息随下一轮输入重新进入 Agent 的记忆，Agent 可以看到自己上一次派发的结局并作出反应。

全局只有一份记忆（Global memory）：所有输入累积到同一条对话历史，由单个消费者逐条处理，没有会话隔离（文档见 [ADR-0005](docs/adr/0005-global-memory-single-thread.md)）。

## 快速开始

### 安装

依赖用 [uv](https://docs.astral.sh/uv/) 管理，Python ≥ 3.12：

```bash
uv sync
```

### 配置真实模型

Waycast 使用 **OpenAI Chat Completions** API（经 base URL 指向任意 OpenAI 兼容端点），凭据通过环境变量或项目根目录的 `.env` 文件提供：

```bash
export WAYCAST_BASE_URL="https://your-provider.example.com/v1"   # 或 OPENAI_BASE_URL
export WAYCAST_API_KEY="sk-..."                                  # 或 OPENAI_API_KEY
export WAYCAST_MODEL="gpt-4o-mini"                               # 可选，默认 gpt-4o-mini
```

其他可选变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WAYCAST_QUEUE_SIZE` | `100` | 输入队列容量（背压上限） |
| `WAYCAST_HOST` | `0.0.0.0` | 监听地址 |
| `WAYCAST_PORT` | `8000` | 监听端口 |
| `WAYCAST_THREAD_ID` | `waycast-global` | 全局记忆的 thread_id |

### 启动服务

```bash
uv run waycast serve
```

启动后：

- `POST /input` —— 提交一条统一输入。请求体为 `{ "content": "...", "source": "http", "metadata": {...} }`（后两个可选）。入队成功立即返回 `200`；队列满时生产者阻塞，这就是背压（Backpressure）契约。
- `GET /health` —— 健康检查，返回 `queue_size`。
- `GET /results` —— 最近一次调用的完整结果（分发的 units、每个派发的 OutputResult）以及全部待反馈的 `pending_output_results`。

### 一个最小演示

```bash
curl -s http://127.0.0.1:8000/input \\
  -H 'Content-Type: application/json' \\
  -d '{"content": "上海的天气怎么样？顺便通知我一下秋裤指数。"}'
```

Agent 会多轮调用工具（查天气、记日志、发通知），然后把 units 派发给已注册的输出模块。用 `curl -s http://127.0.0.1:8000/results` 查看 `units` 与各模块返回的 `results`；来自 `notify` 模块的结果会在下一次输入时作为系统消息重新进入 Agent。

## 架构

```
输入模块 ──> UnifiedInput ──> [ 有界队列（背压）] ──> 单个消费者 worker
                                                          |
                                                          v
                                               Agent（LangChain v1 create_agent）
                                               · 多轮工具调用（函数工具 / MCP 工具）
                                               · 结构化输出 response_format=AgentOutput
                                                          |
                                units: [ {module, payload}, ... ]（可为空）
                                                          v
                       输出模块 A ──> OutputResult A ─┐
                       输出模块 B ──> OutputResult B ──┼──> 该结果作为消息进入下一轮
                       输出模块 C ──> OutputResult C ─┘
```

关键设计点：

- **JSON 输出优先，否则自动回退**：把 Pydantic schema 直接传给 `create_agent` 的 `response_format`，LangChain v1 的 `AutoStrategy` 会自动探测——provider 原生支持结构化输出就走 `ProviderStrategy`（JSON mode），否则回退到 `ToolStrategy`（把 schema 当工具让模型填充）。
- **统一的派发协议**：所有跨模块边界的对象都是可 JSON 序列化的 `dict`，所以任意传输层（HTTP、队列、回调）都能承载。
- **失败降级**：遇到未注册的输出模块、schema 校验失败或 `accept` 抛异常时，该 unit 被丢弃，但会产生一个 `error` 状态的 `OutputResult` 记入待反馈，让 Agent 下一轮知道并尝试修复。
- **背压**：有界的 `asyncio.Queue` + 单消费者 worker。队列满时生产者阻塞，而不是拒绝或限流（[ADR-0006](docs/adr/0006-fastapi-bounded-blocking-queue.md)）。
- **全局记忆**：固定 `thread_id` + `InMemorySaver` 检查点，所有输入累积在同一条对话历史上（[ADR-0005](docs/adr/0005-global-memory-single-thread.md)）。

## 编写自己的模块

模块与 Agent 之间的协议定义在 [src/waycast/protocols.py](src/waycast/protocols.py)，所有类型都是运行时可见的 `Protocol`。

### 输入模块

实现 `InputModule` 协议，`emit` 返回 `UnifiedInput`：

```python
from waycast.protocols import InputModule, UnifiedInput

class MyInput(InputModule):
    @property
    def name(self) -> str:
        return "my_input"

    def emit(self, **kwargs) -> UnifiedInput:
        return UnifiedInput(
            content=str(kwargs["text"]),
            source=self.name,
            metadata={"extra": kwargs.get("extra")},
        )
```

内置的 [HttpInputModule](src/waycast/modules.py) 就是最小范例。注意：输入由服务调用 `emit` 后进队列，每条输入恰好触发一次调用。

### 输出模块

实现 `OutputModule` 协议：声明 `name`、接受的 Pydantic `output_schema`、同步 `accept`（返回 `OutputResult`）和 `describe`（会注入系统提示词供 LLM 决策）：

```python
from pydantic import BaseModel, Field
from waycast.protocols import OutputModule
from waycast.state import OutputResult

class AlertSchema(BaseModel):
    message: str = Field(description="告警文本")
    severity: str = Field(default="info", description="info | warning | error")
    to: str = Field(description="接收人")

class AlertOutput(OutputModule):
    @property
    def name(self) -> str:
        return "alert"

    @property
    def output_schema(self):
        return AlertSchema

    def accept(self, payload: dict) -> OutputResult:
        data = AlertSchema.model_validate(payload)   # 派发前 Agent 已校验，这里再兜底
        # ... 真实派发逻辑（HTTP、队列、回调等）
        return OutputResult(module=self.name, status="ok", detail=f"已发送给 {data.to}")

    def describe(self) -> str:
        return "向指定接收人发送告警（message + severity + to）。"
```

注册并装配（参见 [src/waycast/demo.py](src/waycast/demo.py)）：

```python
from waycast.agent import Agent
from waycast.config import WaycastConfig, make_model
from waycast.demo import build_service
from waycast.protocols import ModuleRegistry

reg = ModuleRegistry()
reg.register_input(MyInput())
reg.register_output(AlertOutput())
# ... 还可以注册更多输入/输出模块

config = WaycastConfig.from_env()
agent = Agent(registry=reg, model=make_model(config))
service = build_service(reg, agent, config)
```

注册了你的模块后，`describe_output_modules()` 生成的目录（含每个模块的 JSON schema）会自动注入系统提示词，Agent 就会在多轮工具调用后给出对应的 `units`。

## 内置 demo 模块与工具

- **输出模块**：`notify`（发通知，schema 为 `message` + `level`）、`memory_log`（写结构化日志，schema 为 `text` + `tags`）。
- **输入模块**：`http`（把 `POST /input` 的请求体转成 `UnifiedInput`）。
- **工具**：[src/waycast/tools.py](src/waycast/tools.py) 内置 `get_time`、`echo`、`look_up_weather`、`store_blob`、`notify`、`emit_seen_url`，用于演示多轮工具调用；MCP 工具接入通过 `Agent(tools=[...])` 参数传入（见 [ADR-0004](docs/adr/0004-mcp-ships-in-langchain-core.mcp.md)）。

## 测试

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

测试不依赖网络：`tests/conftest.py` 提供一个同时实现 `_generate` 与 `_agenerate` 的假模型，覆盖注册去重、schema 注入提示词、多单元分发、空列表、未知模块/坏 schema 降级、异步调用与结果累积，以及服务的 worker 消费与队列背压。

## 项目结构

```
src/waycast/
  agent.py         Agent：create_agent + 结构化输出 + 单元派发 + 结果记忆
  blocks.py        消息构建块（把待反馈结果转成 SystemMessage）
  cli.py           waycast serve 入口
  config.py        环境变量 / .env 配置，构建 ChatOpenAI
  demo.py          demo 装配：registry + 模块 + 模型 + Agent + Service
  modules.py       内置输入/输出模块
  protocols.py     统一协议：UnifiedInput / OutputModule / InputModule / ModuleRegistry
  registry.py      ModuleRegistry 再导出
  service.py       FastAPI + 有界背压队列 + 单消费者 worker
  state.py         OutputResult / OutputResultState / 全局记忆状态
  tools.py         内置 demo 工具
docs/adr/          全部架构决策（0001-0007）
GLOSSARY.md        术语表
```

