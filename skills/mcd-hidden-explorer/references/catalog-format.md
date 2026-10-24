# 公开资料库格式

`catalog.json` 是公开 Skill 的唯一数据源。默认为空，避免把未授权图片或未经核验的网络内容发布到仓库。

## 条目字段

```json
{
  "id": "X01",
  "aliases": [],
  "name": "公开展示名称",
  "recipe_status": "cover_only",
  "source_kind": "user_submitted",
  "source_url": "https://example.com/source",
  "source_title": "来源标题",
  "region": "待核实",
  "observation": "只记录图片或来源明确展示的现象",
  "ingredients": [],
  "steps": [],
  "tags": [],
  "assets": []
}
```

## 证据状态

- `cover_only`：只有封面或图片观察。不得填写配方步骤和数量。
- `reported_recipe`：来源文字明确写出配方或步骤。数量不确定时使用 `null`，不要补估。
- `verified_menu_mapping` 不作为资料状态使用；门店 SKU、价格和供应状态属于一次 MCP 查询结果，不写死在资料库。

## 来源与素材

- 只使用有权公开的文字、链接和图片；无法确认授权时，不提交图片。
- `source_url` 必须是 HTTPS；不要把 Token、Cookie、订单号或个人信息写入条目。
- 外部来源不等于官方来源；“麦当劳”出现在用户名或标题中不构成官方背书。
- 图片如需加入，应记录可公开使用依据，并使用仓库内相对路径；不要使用远程图片自动下载或热链。

## MCP 映射原则

资料库记录“想怎么吃”，MCP 返回“这家门店现在有什么”。映射时逐项保存：原料、实际 SKU、规格、数量、可用修改项、时段、查询时间和价格证据。无法匹配的原料必须显示为未找到或外部食材，不能静默替换。