# 画龙点睛 · dianjing

一句话选题 → 10 条可独立传播的爆款标题（公众号 / 知乎 / 小红书 / B 站推文）。

## 结构

- `SKILL.md` — 主指令：触发条件、平台适配、5 类公式定位、自检与发布后回填
- `references/title_formulas.md` — 5 类公式 + 高赞 10 式 + 风格 DNA + 样本 + 生成 Prompt
- `references/title_index.md` — 610 条爆款标题纯列表（去重，按原时间倒序）
- `agents/openai.yaml` — UI 元数据（display_name 等，可选）

## 安装

- 克隆/拷贝本仓库到 `~/.codex/skills/dianjing/`（或 `$CODEX_HOME/skills/dianjing/`）
- 需要 `.skill` 分发包时，用 skill-creator 的打包流程手动生成即可（`dist/` 不入库）

调用：把一句话选题发给它即可，可附平台与目标（如"公众号、涨粉"）。机器名 `dianjing`，显示名「画龙点睛·爆款标题生成」。

> 公式模板逆向自某 AIGC 顶流博主 621 篇爆款标题，仅供个人学习与自用。这是风格模板，不是爆款保证——平台权重和账号信任决定传播下限，标题决定上限。
