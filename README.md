# 道枢（Waycast）· 树莓娘唯一核心

> 命名族：[云和（Aria）](https://github.com/BITNP/aria) · [机杼（Loom）](https://github.com/BITNP/loom) · [显影（Lumen）](https://github.com/BITNP/lumen)

一个基于 LangChain v1 的微服务化 Agent：输入/输出模块是独立服务，通过 WebSocket 连接到 Agent（枢纽），以统一 JSON Wire 协议交换帧。每条输入触发一次 Agent 调用（Invocation）；Agent 通过多轮真实模型工具调用产出 JSON 输出单元列表（可为空），派发给已连接的输出模块连接（fire-and-forget）；每个派发立刻返回输出结果，该结果搭载在下一轮调用的输入消息开头、一次性进入对话历史（ADR-0002 / ADR-0014）。

本文是**用户文档**：如何安装、配置并运行 Waycast 服务。架构细节、Wire 协议与模块编写、测试与代码结构见**开发者文档** [DEVELOPMENT.md](DEVELOPMENT.md)；术语见 [GLOSSARY.md](GLOSSARY.md)，架构决策见 [docs/adr/](docs/adr/)。

## Waycast 是什么

Waycast 的核心（`src/`）只含本体：协议、Agent、hub、service、wire 帧模型。模块一律作为网络客户端运行在进程外（ADR-0008），`src/` 中不存在任何 mock 或占位。

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  输入模块     │    │  Agent/Hub  │    │  输出模块     │
│ (独立服务)    │───▶│  (Waycast)  │───▶│ (独立服务)    │
└─────────────┘    │  /ws/modules │    └─────────────┘
                   └─────────────┘
   所有帧走同一条多路复用 WebSocket 连接（A25）
```

### 核心概念

- **Input module**：把外部信号转成统一 `UnifiedInput`（`content` + `source` + `metadata`）的独立服务，经 WebSocket 发送 `input` 帧；每条输入恰好触发一次 Invocation。
- **Agent**：对每条输入运行一次多轮工具调用（内置真实工具 + 可接入 MCP 工具），产出结构化 JSON：`{ "units": [ { "module": "...", "payload": {...} }, ... ] }`，`units` 可为空。
- **Output module**：连接时声明自己接受的 JSON Schema 与语义描述；收到 `output_unit` 帧后立即返回 `result` 帧（成功/失败）。Agent 在派发前按 schema 校验（ADR-0008）。
- **闭环**：模块返回的 `result` 帧进入待送达 feed，恰好在下一轮 Invocation 开始时被一次性取出，搭载在该轮输入 human 消息的开头进入对话历史（每条结果只出现一次，随摘要老化）（ADR-0002 / ADR-0014）。
- **Global memory**：所有输入以 human 消息累积到同一条对话历史（固定 `thread_id` + `InMemorySaver`），单消费者逐条处理，无会话隔离（ADR-0005）；历史逼近阈值时由内置 `SummarizationMiddleware` 自动摘要压缩（ADR-0013）。

## 快速开始

### 安装

依赖用 [uv](https://docs.astral.sh/uv/) 管理，Python ≥ 3.12：

```bash
uv sync --locked
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
| `WAYCAST_LOG_LEVEL` | `INFO` | 本服务日志级别（`DEBUG` 输出输入帧、LLM 请求/响应、单元派发与 result 帧等调试信息） |
| `WAYCAST_DEPS_LOG_LEVEL` | `WARNING` | 第三方依赖日志级别（httpx/openai/websockets 等；uvicorn 访问日志仅在放开到 `INFO`/`DEBUG` 时才输出） |
| `WAYCAST_LLM_LOG_MESSAGES` | `incremental` | LLM 请求消息的记录方式：`incremental` 只打相对上次请求新增的消息，`full` 每次全量打印（历史前缀变化时自动回退全量） |

### 自定义 Agent 系统提示词

你可以直接写 **一整段纯文本** 作为 Agent 系统提示词的用户部分。默认读取项目根目录的 `waycast.prompt.txt`（可用环境变量 `WAYCAST_AGENT_CONFIG` 指定路径），文件内容原样读入，无需 TOML、转义或字段结构：

```text
你是一个调度助手。

使用场景：接收输入，把结论交付给已连接的输出模块。

注意：
1. 涉及时间时先调用 get_time 工具；
2. 回复要简洁，避免啰嗦。
```

文件内容拼在自动生成的 capability catalog（每个连接模块的 `describe` 与 JSON Schema）之前，构成最终系统提示词：

```
[固定 base prompt] + [你的纯文本提示词] + [自动生成的模块目录 + schema + 状态工具] + [默认规则]
```

协议规范始终保留在提示词里；你只写角色、场景与行为要求。文件缺失或为空时，系统提示词保持默认不变。

### 启动服务

```bash
uv run --locked waycast serve
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

## 下一步

- 想**编写自己的输入/输出模块**（wire 协议、capability 握手、status 查询）：见 [DEVELOPMENT.md](DEVELOPMENT.md#编写自己的模块)。
- 想理解**关键设计点**（单通道多路复用、背压、结构化输出回退等）：见 [DEVELOPMENT.md](DEVELOPMENT.md#关键设计点) 与 [docs/adr/](docs/adr/)。
- 术语的唯一称呼见 [GLOSSARY.md](GLOSSARY.md)。

## 命名来历

**waycast（道枢）**——waycast 一名有两层来历。

**其一是字面的双关**：way（路、道）× cast——投送、播送（broadcast 的词根）、铸模、群戏卡司。输入沿路而来，被核心铸成一次次的表现。

**其二是向 Wayland 协议致敬**（ADR-0015 记录）。Wayland 是 Linux 桌面的显示协议，其核心洞见在官方文档里写得很干净：应用（client）自己渲染自己的 surface，「所需要的只是把画好的 surface 呈现出来、并在多个客户端之间接收与仲裁输入的一层」——这一层叫 **compositor**（Wayland Book, Introduction；wayland.freedesktop.org，二者查阅于 2026-11-10）。waycast 是同构的镜像：各模块像 Wayland 客户端一样只广告自己的 capability、只与中枢收发帧，从不直接对话；hub 像 compositor 一样只做两件事——**接收并在所有输入之间仲裁**（每个输入帧恰好一次 Invocation，话权归 Agent，ADR-0011），以及**把输出组成后呈现出去**。连命名形态都同构：Way+land 是「道之所栖」，Way+cast 是「道之所投」。

**中文名「道枢」**出自《庄子·齐物论》：「彼是莫得其偶，谓之道枢。枢始得其环中，以应无穷。」——枢，门轴也，是 hub 的中文本字；「环中」是圆环的空心处，立于其中便可应对外界的无穷变化。这恰好是三件事的合一：hub 立于输入与输出的环心，应答无穷的请求；圆环是 **π**——树莓娘的「树莓」兼指树莓派 Raspberry Pi，无限不循环恰似一场不会自我重复的对话；而「道枢」二字逐字对译 waycast：道＝way，枢＝hub。

命名族全谱（waycast 道枢 / aria 云和 / loom 机杼 / lumen 显影）见 [ADR-0015](docs/adr/0015-raspberrygirl-naming-family.md) 与 [GLOSSARY](GLOSSARY.md)「命名族」。

## 许可证

Copyright © 2026 北京理工大学网络开拓者协会（BITNP）。本仓库以 **AGPL-3.0-or-later** 发布（全文见 [LICENSE](LICENSE)：[SPDX](https://spdx.org/licenses/AGPL-3.0-or-later.html)）：可自由使用、修改、分发；但修改版以分发或网络服务方式对外提供时，必须以同许可整体开源（AGPL 的网络条款）。

树莓娘（Raspberry Girl）名称、形象与相关美术资产为网协专有，**不适用本许可证**。
