# 麦麦隐藏吃法探索器 · mcd-hidden-explorer

> 发现民间隐藏吃法，再用麦当劳中国 MCP 核实所需餐品。

面向想试点不一样的麦当劳吃法、但不知道如何把攻略变成实际餐品清单的用户。用户持续收集来源资料，Skill 负责发现、解释、拆解与门店菜单核实。民间组合不是官方隐藏商品。

## 当前状态：可运行的基础仓库

- 已提供 Skill 编排、公开资料格式、稳定编号查询、资料校验和离线页面生成脚本。
- **公开资料库当前为 0 条**，等待录入有来源、可公开的吃法；没有用虚构内容填充，也没有发布授权未确认的第三方图片。
- 当前为文字发现页面；图片图库与正式配方库待素材授权确认后接入。
- MCP 实测目前仅完成只读时间查询；门店→菜单→详情→价格的完整配置流程尚未完成端到端实测。
- 不自动创建订单、支付、领券或写购物车。

## 体验流程

发现吃法 → 选择稳定编号 → 判断配方证据 → 用户要求配置 → 核实门店和用餐方式 → 查询实际菜单及详情 → 映射原料与 SKU → 价格核实 → 输出可执行清单、替代方案和未决事项。

只有封面时不推断完整配方；数量缺失时保留未知；不能匹配的外部食材或时段限制必须明示。

## 安装

Python 3.9+，无第三方 Python 依赖。克隆后，只复制 Skill 子目录；不要将整个仓库复制到自身子目录。

```bash
git clone https://github.com/dajiangde/mcd-hidden-explorer.git
cd mcd-hidden-explorer
mkdir -p "$HOME/.workbuddy-ai/skills"
# 如目标目录已存在，先备份并人工合并，不直接覆盖。
cp -R skills/mcd-hidden-explorer "$HOME/.workbuddy-ai/skills/"
```

项目级安装可使用 `.workbuddy-ai/skills/`，目标目录同样不得已有同名版本。现有本地探索包不应被此公开空库覆盖。

在 WorkBuddy 中启用已配置的麦当劳中国连接器。配置与核实边界见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。不配置 MCP 也可运行资料查询和页面生成。

## 本地命令

```bash
python3 skills/mcd-hidden-explorer/scripts/explore.py validate
python3 skills/mcd-hidden-explorer/scripts/explore.py list
# 先录入 X01 后才可查询；空库查询会明确报未知编号。
python3 skills/mcd-hidden-explorer/scripts/explore.py lookup X01
# 输出需不存在，且父目录必须存在。
python3 skills/mcd-hidden-explorer/scripts/explore.py build --output /tmp/mcd-hidden.html
python3 -m unittest discover -s tests -v
```

## 持续收集吃法

按 [录入格式](skills/mcd-hidden-explorer/references/catalog-format.md) 编辑 `skills/mcd-hidden-explorer/references/catalog.json`，然后运行 `validate`。先录入文字和来源链接，授权未确认的图片留在本地，不公开提交。私有研究目录 `mcd-hidden-explorer/`、工作日志及环境记录均由 `.gitignore` 排除。

## 对话示例（非已收录内容承诺）

- “看看有哪些隐藏吃法。”
- “我选 X01，先解释它的资料状态。”
- “我把这条吃法的来源和步骤发给你，帮我整理入库。”
- “帮我按这家门店现在可买的餐品配置，缺什么就告诉我。”

## 仓库结构

```text
README.md
CONTEST_DECLARATION.md
MCP_INTEGRATION.md
workbuddy.md
skills/mcd-hidden-explorer/
  SKILL.md
  references/catalog.json
  references/catalog-format.md
  scripts/explore.py
tests/test_explore.py
```

## 比赛与公开边界

[官方活动仓库](https://github.com/M-China/mcd-developer-innovation-challenge)要求 README、原样参赛声明、MCP 集成说明及可运行内容。本文档及源码组成基础提交材料，不代表已报名成功。

`workbuddy.md` 当前仅为真实开发摘要，**不是完整对话导出**；申请 WorkBuddy 专项奖励时需补充真实导出并脱敏。还需录入正式吃法、完成实时配置验证，再提交报名 Issue。本仓库不会自动代替用户提交报名声明。

本项目为独立开发的非官方参赛作品，无麦当劳官方背书。品牌及相关商标归权利人所有。内容不构成营养、医疗等专业建议；餐品、价格和供应以官方渠道实时结果为准。禁止提交凭据、个人信息或未获授权素材。
