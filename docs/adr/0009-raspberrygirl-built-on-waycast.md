# 树莓娘以 Waycast 为核心重构：waycast 核心保持通用不大改

树莓娘（Raspberry Girl）项目抛弃全部旧实现（旧仓库与旧代码只读保留，不修改、不删除、不搬迁），以本仓库 waycast 为唯一核心重写整个系统。输入来源（语音、IM、弹幕等）作为 waycast 输入模块接入；表现输出（语音合成与播放、Godot 前端字幕/表情/动作、PPT 显示与翻页）作为 waycast 输出或双向模块接入。waycast 的现有功能与契约保持固定，不做为适配树莓娘而修改核心语义的大改。

## Status

Accepted

## Context

树莓娘原本是一个多仓库的独立 Agent 体系（bitnp-raspberrygirl-vtuber-core / -mic / -comments / -frontend / -sound / -orchestrator），拥有自己的架构文档（根目录 architecture.md）、独立话权控制器、按 session 隔离的记忆等。这套体系与 waycast 的目标形态（一个通用 Agent 服务：统一输入 → 一次 Invocation → 输出单元列表 → 派发输出模块）高度重叠，但实现与 waycast 平行、互不共享。用户决定：不再平行维护，而是抛弃旧实现，让 waycast 成为整个项目围绕的核心。

waycast 已具备的契约（ADR-0001 至 ADR-0008）——Agent-as-hub、统一 JSON Wire 协议、模块 capability 声明（input/output/both）、背压、全局单线程记忆、LangChain v1 create_agent、MCP 工具——全部保留。树莓娘不是要"改造 waycast"，而是要"按 waycast 的契约重新表达自己"。

## Decision

- **waycast 是唯一核心**：hub、Agent、协议、服务都在 waycast 仓库，不再存在第二个核心仓库。
- **旧实现只读**：bitnp-raspberrygirl-vtuber-* 各仓库及其代码仅作参考，不修改、不删除、不搬迁；不作为新实现的部分复用来源，不承担兼容义务。
- **模块化适配**：所有输入源作为 waycast 输入模块（发送 input 帧）；所有表现输出作为 waycast 输出或双向模块（接收 output_unit 帧并回 result 帧）。模块可独立部署、独立仓库。
- **一切产品语义下沉模块或交给 Agent**：话权、打断、Partial/最终文本等交互语义不再由核心独立实现，而是由核心 Agent 依据输入内容自行决定，或由输入/输出模块在自身侧处理。
- **核心功能可以增强，但契约保持固定**：waycast 现有功能与对外契约（wire 协议、模块帧、背压、记忆、工具）保持固定，不等于冻结功能。对智能体有意义但**不属于输入/输出模块能力**的功能（例如知识检索 RAG、记忆策略、提示词装配、Agent 角色行为）可以直接在 waycast 核心内实现/配置，作为核心增强；这类增强遵守 ADR-0002 的闭环（输出结果进入下一轮）等既有契约。
- **AGENTS.md / GLOSSARY.md / ADR 以 waycast 仓库为准**：领域术语、架构决策与工作规则的唯一维护位置在 waycast 仓库；工作区根目录的共享资料（AGENTS.md / CONTEXT.md）降级为指向 waycast 的指针，architecture.md 删除。

## Consequences

- 新系统的模块清单与各自职责见 ADR-0010（聚合输出模块）；话权/打断的 Agent 决策语义见 ADR-0011（如适用）。
- 删除根目录 architecture.md、降级根 CONTEXT.md：树莓娘的产品语义分散到模块 README、waycast GLOSSARY 与各 ADR，不再有单一"树莓娘架构文档"。
- waycast 核心的通用性是硬边界：任何"只有树莓娘需要、且无法表达为输入/输出模块能力"的需求，要么落为核心增强（RAG 等），要么回炉与用户重新确认，不通过给 waycast 打产品补丁解决。
- 旧 vtuber-* 仓库的运维/部署资料保留但不再更新，作为历史存档。

