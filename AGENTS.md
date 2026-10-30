# AGENTS.md

Waycast 是一个长期运行的 Agent 服务：输入模块产生统一输入，每个输入触发一次 Agent 调用（Invocation），Agent 以多轮工具调用产出 JSON 输出单元列表（可为空），派发给任意输出模块组合（fire-and-forget），每个派发立刻返回输出结果，该结果随下一轮输入一起进入下一轮调用。

Waycast 也是树莓娘（Raspberry Girl）项目的唯一核心（ADR-0009）：树莓娘的语音、IM、弹幕输入作为 Waycast 输入模块；表情、动作、语音合成、PPT 显示与翻页由聚合输出模块承担（ADR-0010）；话权与打断由核心 Agent 自行决定（ADR-0011）；RAG 等核心增强在 Waycast 核心内实现（ADR-0012）。业务模块各自放在独立仓库中，本仓库只承载核心；旧 vtuber-* 仓库只读保留，不修改、不删除、不搬迁。

在 Waycast 仓库里开发、修改时，先读 [README.md](README.md)（用法）、[GLOSSARY.md](GLOSSARY.md)（术语，含 Raspberry Girl context 段）、[docs/adr/](docs/adr/)（决策），再动手。

工作区通用原则（文档优先、同步文档、术语一致、ADR 单一事实源、原子提交、真实验证禁止 mock、网络审批、先查自己、不确定时询问、旧实现只读）见根目录 [AGENTS.md](../AGENTS.md)；本仓库只保留 waycast 专属原则。

## 原则

**核心通用，契约固定。** 本仓库是树莓娘的唯一核心，但 Waycast 的通用语义（wire 协议、模块帧、背压、全局记忆、工具）保持稳定，不为树莓娘改核心契约（ADR-0009）。树莓娘需求落为方式：能表达为输入/输出模块能力的做成模块（模块放独立仓库）；属于 Agent 推理本身的能力（RAG、提示词装配、记忆策略等）作为核心增强在本仓库实现（ADR-0012）。判别不清时先与用户确认。

**模块自检。** 新增或修改输入/输出模块（含 [examples/](examples/) 参考模块）时：模块是网络客户端（ADR-0008），连接 `/ws/modules` 后首帧发送 capability advertisement（输入声明 `name` + 自然语言描述；输出声明 `name` + JSON Schema + 语义描述；状态查询可选），用同一条多路复用连接收发 `input` / `output_unit` / `result` / `status_query` / `status_result` 帧。跨模块协议以 `waycast.protocols`（载荷模型）与 `waycast.wire`（帧信封）为唯一权威，不重复实现；在测试里覆盖 capability 去重、派发成功、失败降级。输出模块不得自行修改共享记忆，记忆只能由 Agent 通过 `OutputResult` 累积（ADR-0002）。同时扮演输入与输出的模块用 capability 的 `kind = "both"`（聚合输出模块见 ADR-0010）；业务模块存放在独立仓库，不放进本仓库 `src/`。

**验证。** 依赖由 uv 管理在 `.venv`。单元层（wire 协议、capability 目录、hub 帧路由、prompt 拼接、CLI 装配）可用本地假模块连接离线测试；涉及 Agent 模型行为（结构化输出、多轮工具调用、输出单元派发、结果进入下一轮）必须跑真实模型，测试用真实冒烟覆盖。跑 `PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`，路由层测试必须全绿；真实冒烟用 `.env` 里已配置的 credentials（`WAYCAST_BASE_URL` / `WAYCAST_API_KEY`）执行。

## 工作流

1. 读相关 GLOSSARY 与 ADR，确认术语与决策一致。
2. 按最小改动修改；跨模块协议变更先动 `waycast.protocols` / `waycast.wire`，再同步实现、文档与测试。
3. 涉及真实模型行为时，直接用真实模型验证闭环；禁止用假模型代替。
4. 每步独立改动创建原子提交。

