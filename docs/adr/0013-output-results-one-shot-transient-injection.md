# 输出结果经动态系统提示词一次性注入；输入走 human 消息；历史交给内置摘要

Output result 的送达机制定为**一次性消费 + 临时注入**：每轮 Invocation 开始前把待处理的结果 feed 整体取出（drain），交给 CapabilityBridge 渲染进本轮的动态系统提示词；结果恰好吃掉一次，绝不进入 checkpoint 的对话历史。Unified input 以 human 消息进入历史。历史长度由 LangChain 内置 `SummarizationMiddleware`（用主模型）管理，不再手工裁剪。本 ADR 固化 ADR-0002（"结果进入下一轮调用"）的实现机制，并补充其"恰下一次"的语义；全局单线程记忆（ADR-0005）与提示词每轮重建（A20）不变。

## Status

Accepted

## Context

旧实现把输出结果feed放在错误的通道上：`Agent._prepare` 每轮把**累积列表的全量快照**包装成新的 SystemMessage 作为 graph input 送进 checkpointer 的全局线程。LangChain 的 `add_messages` reducer 按消息 ID 合并——每轮快照都是新 ID、旧快照永久留存——导致同一次请求里出现多份几乎相同的 "Output module results" 列表、prompt 体积随调用次数平方增长、26 行 `ok queued` 回执噪声永不退出；`WaycastAgentState` 的 `output_results` 状态键写入后无任何代码读取。

对照 LangChain v1 官方文档（docs.langchain.com，langchain 1.4.8，2026-11-10 查阅）：

- Middleware/Custom — *Dynamic prompt*：每轮变化的上下文用 `wrap_model_call` 改 `system_message` 注入，是官方第一用例；`CapabilityBridge` 重建系统提示词（A20）本来就走这条通道。
- Context engineering — Messages 的 NOTE：临时上下文应当 *"make transient updates - modifying what messages are sent to the model for a single call without changing what's saved in state"*；放进持久历史是反模式。
- Middleware/Built-in — *Summarization*：历史逼近上下文窗口时用内置 `SummarizationMiddleware` 自动摘要压缩，无需自研裁剪。

ADR-0002 的原文措辞是结果成为 *"the state of **the next** invocation"*——一次性送达，而非永久累积重放。

## Decision

- **一次性消费**：`Agent.ainvoke` 在运行图之前 `OutputResultState.drain()` 取出全部待处理结果，交给 `CapabilityBridge.begin_invocation()`。本轮新到达的结果（派发同步失败、模块异步 result 帧）留在 feed 里，等下一轮。每个 Output result 恰好送达一次。
- **临时注入**：bridge 在 `wrap_model_call` 重建系统提示词时把本轮feed渲染为一个段落（位于 catalog/status 之后、rules 之前），不进对话历史。连续相同的结果聚合计数为一条（如 `- presenter: ok queued (x26)`），错误 detail 保留全文。
- **输入走 human 消息**：Unified input 以 `HumanMessage` 进入历史（LangChain 对话惯例），不再伪装成 SystemMessage。
- **历史交给内置摘要**：`SummarizationMiddleware(model=主模型, trigger=[("tokens", 60000), ("messages", 240)], keep=("messages", 40))`。token 计数是近似值，故加消息数上限兜底 CJK 场景。
- **删除**：`WaycastAgentState` 自定义状态模式与 `state_schema` 参数、`blocks.results_as_message`、`_prepare` 中的feed注入；渲染逻辑收敛到 `waycast.state.results_as_text`。

## Consequences

- feed 每轮在 prompt 中恰好出现一次、恰好吃掉一次；重复快照与平方增长消失，A20 成为唯一的"每轮动态上下文"通道。
- `/results` 的 `pending_output_results` 语义变为"自上次消费以来新到达的结果"，端点本身不变。
- Invocation 中途异常时本轮drain掉的feed不回滚（已送达"下一轮"这一承诺随该轮作废）：接受该取舍，换取实现最简；结果本就是提示性反馈，非必须送达的指令。
- 长对话历史由摘要压缩，全局记忆（ADR-0005）在长时间运行下不再无界增长；摘要用主模型，无需另配模型。
- 输入角色改变（system → human）影响模型对输入的先验，已由真实模型冒烟（test_agent_real.py）验证行为不变。
