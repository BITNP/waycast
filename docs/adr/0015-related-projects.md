# 树莓娘关联项目命名：道枢 / 云和 / 机杼 / 显影

## Status

accepted

## Context

树莓娘体系原先以 `raspberrygirl-*` 前缀命名模块仓库，功能直白但无意象；核心 waycast 一名本身是「way + cast」的双关（沿路投送、播音、铸模），模块名与之风格断裂。用户决定为核心取中文名、为三个模块仓库取有诗意与隐喻的中英文新名，并要求命名融合中国传统文化、网协与树莓娘吉祥物、科技与极客（Linux / AI / LLM）元素。命名来历的完整阐述在各仓库 README 末尾「命名来历」。

## Decision

自 2026-11-10 起，树莓娘体系使用下列关联项目（multirepo 微服务，英文小写词为仓库 / 包 / CLI / wire 标识符，中文名为正式称呼）：

| 角色 | 中文名 | 英文名 | 旧名 |
| --- | --- | --- | --- |
| 核心（本仓库） | **道枢** | waycast（不变） | — |
| 语音输入模块 | **云和** | **aria** | raspberrygirl-voice-input |
| 文本输入模块 | **机杼** | **loom** | raspberrygirl-text-input |
| 聚合输出模块 | **显影** | **lumen** | raspberrygirl-presenter |

- waycast 英文名与全部 `WAYCAST_*` 环境变量不变；「道枢」是其中文名（出处与阐述见本仓库 README「命名来历」）。
- 模块英文名贯通所有标识符层：仓库目录、pyproject 项目名、Python 包名、CLI 命令、wire 模块名（capability `name` 与帧 `module`/`source`）、环境变量前缀（`ARIA_` / `LOOM_` / `LUMEN_`）。逐仓库映射表见各模块仓库的更名 ADR（aria ADR-0013、loom ADR-0001、lumen ADR-0009）。
- 旧标识符不再用于新设计；本 ADR 之前的历史文档（各仓库旧 ADR、开发日志、git 历史，含本仓库 ADR-0009/0010/0013/0014 中的示例与本仓库测试夹具中的旧模块名）保持原文，按映射表读解。

## Consequences

- 术语唯一性由本仓库 GLOSSARY「道枢」「关联项目」词条承载；跨仓库文档引用一律改用新名。
- hub 侧无按模块名绑定的令牌，wire 模块名更改不需要核心代码改动；核心全局记忆与能力目录自模块重连起自然显示新名。
- GitHub 远端仓库改名是网页端手工操作，克隆 URL 与工作区各指向旧路径的引用需相应更新（工作区根 AGENTS.md / CONTEXT.md 已随本次改名更新）。
