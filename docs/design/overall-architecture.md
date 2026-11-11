# Waycast 总体设计：微服务化的模块网络协议

> 本文汇总 grill-with-docs 各轮已定决策，作为实现蓝图。术语见 [GLOSSARY.md](../../GLOSSARY.md)，
> 关键决策见 [ADR-0008](../adr/0008-module-network-protocol.md)。状态：设计确认。

## 目标

- `src/` 只保留本体：协议、Agent、Service(hub)、WebSocket 模块端点。不存在 HTTP 输入路径。
- 生产代码中不存在任何 mock / 占位 / 内置示例模块。
- 输入/输出模块是独立微服务，通过网络与 Agent 通信，可任意接入、灵活替换。

## 架构总览

```
                    ┌────────────────────────────┐
                    │        Agent (hub)          │
                    │  · Wire protocol / WS 端点  │
                    │  · capability bridge MW     │
                    │  · capability catalog       │
                    │  · create_agent 本体        │
                    │  · bounded queue / worker   │
                    └───▲──────────────▲──────────┘
              WS 连接    │ (multiplexed │  WS 连接
              (ability)  │  + 状态查询)  │ (ability)
        ┌───────────────┴────┐   ┌────┴─────────────────┐
        │ input module svc   │   │ output module svc    │
        │ (也可同时为 output) │   │ (也可同时为 input)    │
        └────────────────────┘   └──────────────────────┘
```

- **多路复用连接**：一个模块一条 WebSocket 连接，全双工，所有帧类型（capability / input /
  output_unit / result / status_query / status_result）以 `type` 字段区分。一个模块可同时充当
  输入与输出。
- **Agent 即 hub**：模块主动连接 Agent 暴露的 `/ws/modules`（配置 hub 地址），Agent 被动接受。
- **能力宣告**：连接后第一帧是 `capability`，携带模块名称、自然语言描述、JSON Schema、语义描述、
  可选状态查询声明；描述并入系统提示词。

## 已定决策（按轮）

### R1：基础方向

1. 协议 = 薄的 JSON 信封 + 现成 `UnifiedInput` / `OutputUnit` / `OutputResult` 作载荷。
2. 模块主动连接 Agent；Agent 即 hub，无独立 broker。
3. 一条多路复用全双工连接承载全部帧类型（Q3→Q25 修订：从"每能力一条"改回多路复用）。
4. Agent 暴露单一 WebSocket 端点，模块经配置地址连接。
5. 协议 v1 落文档（ADR-0008）。

### R2：细节增强

6. 协议与传输解耦（默认 WebSocket，未来可换）。
7. 模块名称作连接身份；重连幂等（同名新连接替换旧连接）。
8. **连接 token 校验**（`WAYCAST_HUB_TOKEN`，握手或 capability 帧携带，不匹配即关连接）。
9. capability 帧携带 JSON Schema + 语义描述；Agent 侧保留 schema 校验。
10. 所有输入（模块 `input` 帧经 WS 汇入）进同一有界队列 + 单消费者 worker，背压全局一致；无 HTTP 输入。
11. OutputResult 经同一连接回传，Agent 累积进 `OutputResultState`（ADR-0002）。
12. 示例模块放 `examples/`，独立可运行，兼作测试与开发者参考。

### R3：能力桥与工具边界

13. 能力桥 `AgentMiddleware`：动态工具 + 动态系统提示词片段；模块增减无需重建 graph。
14. 保持"结构化输出 units 派发"与"工具"两轨不合并。
15. 状态查询经能力桥暴露为每模块 `status_<module>` 工具（语义模块自定），不强制 MCP；真正第三方 MCP 工具可选接入。
16. 删除同进程 mock 与注册路径；网络能力桥成为唯一路径。
17. 模块侧配置 hub 地址；Agent 被动接受、不持有模块清单。
18. 派发失败统一 `result` 帧；输入背压保持在队列层。

### R4：接线细节

19. 状态查询工具按模块生成（`status_<module>`），可选、不强制。
20. 每次 invocation 起始由能力桥重拼系统提示词：`[用户自定义] + [当前 capability catalog] + [默认规则]`。
21. 断开即从 catalog 摘除，掉线事实进入下一轮提示词；重连重新加入。
22. Agent 按 JSON Schema 校验，失败不派发（转 error result 帧）。
23. `WAYCAST_HUB_TOKEN` 共享密钥，握手或 capability 帧携带。
24. `examples/waycast_examples/` 提供独立可运行参考模块（cron_source 输入、log_sink 输出、echo_bell 输入+输出）。

### R5：收尾

25. 最小帧集合：capability / input / output_unit / result / status_query / status_result，带 `protocol_version`。
26. 默认规则（空 units、单目标模块、不发明模块/字段）保留为固定基底。
27. `waycast serve` 仅启动 Agent hub，不内置模块。
28. README 改为 hub/协议导向，内置 mock 章节移除，新增 Wire protocol 说明。
29. 测试改为 localhost 端到端（示例模块连 hub）+ 协议/校验单元测试，删除 mock 内存断言。
30. 无其它占位；重构即清理。

## Wire protocol v1（初稿）

JSON 文本帧，统一信封：

```json
{
  "protocol_version": 1,
  "type": "capability | input | output_unit | result | status_query | status_result",
  "module": "<name>",
  "payload": { ... }
}
```

- `capability`：`{name, kind: input|output|both, description?, schema?(JSON Schema), semantic?, status?: bool}`
- `input`：`payload = UnifiedInput`
- `output_unit`：`payload = OutputUnit`（Agent → 模块）
- `result`：`payload = OutputResult`（模块 → Agent）
- `status_query` / `status_result`：状态查询往返，语义模块自定

## 实现顺序（建议）

1. Wire protocol + 帧模型（`waycast/protocols.py` 扩展或独立模块）。
2. WebSocket hub 端点（FastAPI + WS 接受、token 校验、capability 处理）。
3. 能力桥 middleware（动态工具 + 系统提示词重拼）。
4. Agent/Service 接线：输入队列统一、派发走连接、结果回传累积。
5. `examples/` 参考模块。
6. 测试改造（端到端 + 单元）。
7. README / GLOSSARY / ADR 同步，原子提交。

## 未决 / 后续

- 更强安全（mTLS / PKI）留后续。
- MCP Server 工具作为独立可选接入，不属于本协议。
- 连接保活与重连（已定）：保活走 WebSocket 协议层 ping/pong，两端使用
  websockets / uvicorn 的默认参数（20 秒间隔、20 秒超时，不显式配置）；
  模块侧断线重连统一为指数退避——首次 1 秒、每失败一次翻倍、封顶 30 秒、
  ±20% 随机抖动，成功入连后复位（loom / aria / lumen 各自实现同一天平）。
