# 本地研究模式

## 何时使用

在本项目开发／研究上下文中，用户希望读取已授权的本地图片餐品对应表、查吃法或做商品关键词关联时使用。公开 catalog 为空不代表本地研究资料不存在。

公开使用默认走 `explore.py` 与 `references/catalog.json`。研究模式单独走 `scripts/research.py`，只读 schema 3 的本地对应表，不导出、导入或提升公开 catalog，也不把未通过收集标准的条目当作可操作主库。

源码工作区内，脚本默认读取项目的 `work/assets/hidden-menu-photos-20261024/图片餐品对应表.json`。单独安装的 Skill 不携带研究数据；需要 `--source` 显式指定已授权项目的对应表。找不到就说明研究源缺失，不能静默回退到空公开库，也不搜索个人磁盘。

## 项目根目录中的命令

```bash
python3 skills/mcd-hidden-explorer/scripts/research.py validate
python3 skills/mcd-hidden-explorer/scripts/research.py list
python3 skills/mcd-hidden-explorer/scripts/research.py search "薯条"
python3 skills/mcd-hidden-explorer/scripts/research.py lookup R10
```

从其他工作目录、安装副本或另一份资产集调用时，使用全局 `--source` 参数（在子命令之前），指向对应表 JSON；相对图片路径按该 JSON 所在目录解析，不按当前工作目录猜测。

## 返回内容

- 顶层 `mode: local_research`、研究提示、源文件位置与 SHA-256；不会用公开 schema 冒充正式条目。
- 稳定吃法 ID、`name`、来源原名和大陆商品映射、`associated_meals`、来源列表。
- 图片保留原路径、哈希、图片类型、作者、来源与权利状态；附 `absolute_path` 和真实 MIME 供宿主取图。文件路径返回不等于用户已经看到图片。
- `lookup` 的 `research_evidence` 原样保存该条目的完整记录，包括历史门店查询范围／时间、非时令、配方、实拍、用量与其他待核项。未来新增的记录字段也保留。
- 数量不从名字或图片自动推断；`needed_products_as_reported`、`method_as_reported` 和 `quantity_evidence` 原文保留。`associated_meals` 未提供结构化数量，不等于原来源没有任何数量描述。
- `list`／`search` 返回适合探索的视图；要查看完整核验记录再 `lookup`。

关键词查找按名称、商品大陆名／来源名和图片线索描述做大小写不敏感的子串匹配；多个空格分开的词必须同时命中。不是语义检索，不从优惠文案臆造新原料。结果带关联餐品，供现有优惠推荐逻辑读取；此功能本身不查询优惠接口、不做实时适用性证明。

## 选图与回传

展示时用返回的 `name` 和规范 ID；图片取自同条记录的 `images`。正文只解释当前相关的待核项，用户追问时再展开原始证据，不把所有元数据都倒进回复。

需要支持「第几个」时，在项目根目录先创建当批映射：

```bash
python3 skills/mcd-hidden-explorer/scripts/research.py batch R10 R51 --output work/research-batch.json
python3 skills/mcd-hidden-explorer/scripts/research.py lookup "第2个" --batch work/research-batch.json
```

批次绑定研究模式和源文件内容哈希。源数据变化、混用公开批次、没有当批映射时，拒绝猜序号，重新生成批次。已有批次文件不能覆盖；换批次时使用新文件名。只有实际展示了图片才称为展示批次。

## 证据和发布边界

`reported_recipe` 只表示来源有文字配方；`eligible_for_actionable_pool`、各项缺口和非时令状态来自原表，不由读取器重算。历史门店有匹配不能升级为当前有货／券可用；未知商品不能自动选择候选口味。`cover_only` 不生成原料或做法。

展示后返回 `review_research_evidence`，不自动进入下单、领券、支付或发布。需要实时菜单核验时按用户明确请求另走 Skill 的 MCP 阶段，未通过收集标准不称已可操作。

本地研究数据和图片继续留在忽略的 `work/`，不复制进公开包；图片公开使用权是独立发布条件。此读取接口通过不代表 WorkBuddy 桌面／手机图片显示验收通过。
