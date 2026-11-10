# 输出结果搭载在下一轮输入消息的开头；系统提示词完全静态

Output result 的送达通道从 ADR-0013 的"临时注入动态系统提示词"改为**搭载在下一轮 Unified input 的 human 消息开头**：`Agent.ainvoke` 仍在开轮一次性 drain 待送达 feed，但渲染出的文本拼在本轮输入内容之前、作为同一条 human 消息进入对话历史。消费语义不变（恰好吃掉一次）；系统提示词回到纯 `[base] + [user] + [catalog] + [status] + [rules]`，在模块增删之间逐字节静态。

## Status

Accepted

## Context

ADR-0013 把 feed 放进动态系统提示词的中部（catalog/status 之后、rules 之前）。用户裁决其归属错误：**输出结果是上一轮表现产生的会话事件**——与 presenter 的 `queue_finished` 心跳同类，而心跳一直是以 human 消息进入历史的——不是指令，不该占用系统提示词。

KV 前缀缓存也指向同一结论（机制为各家前缀缓存的共性：缓存按最长公共前缀匹配，前缀在偏移 d 处发散则 d 之后全部重新 prefill）。feed 内容逐轮波动（空 ↔ `(x2)` ↔ 错误详情），置于系统提示词中部会把可缓存前缀截断在 rules 与整段对话历史之前；改为搭载在**本就新增**的 human 消息头部，发散点即该新消息自身，可缓存前缀达到最长（base→user→catalog→status→rules→完整历史），且下一轮起整段历史（含该条带 feed 的消息）继续命中。注意：maas 网关是否启用前缀缓存尚待实测，本决策只保证请求形态对缓存最友好。

## Decision

- `Agent.ainvoke` 开轮 `OutputResultState.drain()`（ADR-0002 / ADR-0013 的一次性语义不变），快照传入 `_prepare`，经 `waycast.state.input_content_with_feed(feed, content)` 组装：feed 非空时为 `渲染文本 + 空行 + 输入内容`，为空时原样。
- feed 文本由此进入 checkpoint 历史：每条结果在全部历史中**恰好出现一次**（一次性 drain 保证），随 `SummarizationMiddleware` 摘要老化——不是 ADR-0013 修复的累积全量快照 bug。
- 系统提示词通道删除 feed：移除 `CapabilityBridge.begin_invocation` / `_invocation_results`、`_build_prompt` 的 feed 段、`build_system_prompt_with_user` 的 `feed` 参数。
- Invocation 中途异常时 drain 掉的 feed 不回滚：继承 ADR-0013 的取舍。

## Consequences

- 系统提示词仅在模块增删（A20 目录变化）时变化，其余时刻逐字节静态；前缀缓存形态最优。
- 模型在历史中能看到自己既往表现的送达痕迹（至摘要老化为止），闭环记忆（ADR-0002 / ADR-0005）更自然；与 `queue_finished` 心跳同走 human 通道，事件与指令分离。
- `/results` 的 `pending_output_results` 语义不变：自上次消费以来新到达的结果。
- ADR-0013 的"不进对话历史"表述被本 ADR 取代（一次性送达语义与聚合渲染、摘要中间件仍沿用 0013）。
