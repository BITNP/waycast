# AGENTS.md

Waycast 是一个长期运行的 Agent 服务：输入模块产生统一输入，每个输入触发一次 Agent 调用（Invocation），Agent 以多轮工具调用产出 JSON 输出单元列表（可为空），派发给任意输出模块组合（fire-and-forget），每个派发立刻返回输出结果，该结果随下一轮输入一起进入下一轮调用。

在 Waycast 仓库里开发、修改时，先读 [README.md](README.md)（用法）、[GLOSSARY.md](GLOSSARY.md)（术语）、[docs/adr/](docs/adr/)（决策），再动手。

## 原则

**文档优先。** 行为与决策以仓库文档和最新官方文档为准，不凭记忆或过时经验猜测。动手前先读相关文档；代码与文档冲突时，先查证哪一方过时，不凭印象站队。

**同步文档。** 写代码的同时写注释/文档，不留到以后补。代码改动牵动的 README、GLOSSARY、ADR、输出模块的 `describe` 与 schema 描述等文档，随改动同步更新，保持单一事实源一致。

**术语一致。** 术语遵循 GLOSSARY：Agent、Input module、Unified input、Invocation、Output module、Output unit、Output result、Tool、Backpressure、Global memory、Response format 是唯一称呼；不使用 bot、chat endpoint、trigger、adapter、sink、subscriber、session 等替代表述。

**ADR 是决策的单一事实源。** 改动涉及既有决策（全局记忆 ADR-0005、背压 ADR-0006、输出结果进入下一轮 ADR-0002、JSON 输出优先与工具调用回退 ADR-0007 等）时先读对应 ADR；决策变化以新增 ADR 记录，不改写旧 ADR。代码行为与 ADR 不符时，修复代码，不修改文档掩盖。

**原子提交。** 每完成一个独立改动，就创建一次原子提交：一个提交只包含一个逻辑变更，信息清晰、可独立理解、可独立回退；不把无关改动混进同一提交，也不攒批一次性提交。

**模块自检。** 新增或修改输入/输出模块时：实现对应 Protocol（输入模块 `emit` 返回 `UnifiedInput`；输出模块声明 `name` / `output_schema` / `accept` / `describe`），在 [waycast/demo.py](src/waycast/demo.py) 注册并端到端装配，在测试里覆盖注册去重、派发成功、失败降级。跨模块协议以 `waycast.protocols` 为唯一权威，不重复实现。输出模块的 `accept` 不得自行修改共享记忆，记忆只能由 Agent 通过 `OutputResult` 累积（ADR-0002）。

**验证。** 依赖由 uv 管理在 `.venv`，测试不依赖网络。跑 `PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`，测试必须全绿；新增功能补对应测试。涉及网络或 localhost 的命令超出沙箱时，显式说明理由申请审批，不绕过。

**先查自己。** 行为不符合预期（异步挂起、结果丢失、结构化输出不对）时，先查本仓库代码与测试，以代码和运行结果为事实依据；确认是自己的问题再谈外部原因。外部依赖（LangChain、LangGraph、MCP）的版本与用法按最新发布在线核对，引用时给出证据。

**不确定时询问。** 需求、范围或做法不确定时，不要自作主张，停下询问用户；在得到答复前，不推进依赖该决定的改动。

## 工作流

1. 读相关 GLOSSARY 与 ADR，确认术语与决策一致。
2. 按最小改动修改；跨模块协议变更先动 `waycast.protocols`，再同步实现、文档与测试。
3. 跑测试必须全绿；涉及真实模型行为时，用真实模型冒烟验证闭环。
4. 每步独立改动创建原子提交。

