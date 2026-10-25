# 原图留本地，运行包只带加工卡片

## 维护与分发分开

- `work/assets/hidden-menu-photos-20261024/` 保存原图、来源、配方、营养快照、渲染模板和历史，整个 `work/` 不进入 Git。
- 当前加工图位于 `base-cards-v1/cards/` 和 `thumbnails/`。原图不删除，便于重做卡片、核对配方及保留归属记录。
- `processed-card-library-v1/` 为本地导出的运行资料包：22张PNG、22张缩图、精简catalog、编号SQLite及文件清单。数据库只保留加工卡路径，不带原图路径、签名图片地址或完整原帖采集记录。
- 原始出处保留在本地研究库；运行数据保留必要的公开来源页面归因链接，去除签名参数和图片CDN地址。
- 正式公开catalog与现有安装版本不因这次整理而自动替换。此处只生成本地资料包，不代表已经公开或完成素材授权核验。

## 打包入口

在项目根目录运行（输出目录和ZIP均须不存在）：

```sh
python3 scripts/package_cards.py \
  --cards work/assets/hidden-menu-photos-20261024/base-cards-v1 \
  --database work/assets/hidden-menu-photos-20261024/unified-v2/隐藏吃法编号.sqlite3 \
  --output <新的加工卡资料目录> --zip <新的资料ZIP>
```

使用白名单，仅加入 `cards/U*.png`、`thumbnails/U*.png`、`catalog.json`、`numbered-catalog.sqlite3`、`manifest.json`、README。不得直接压缩整个研究目录或基础卡维护目录；那些目录包含原图和历史。

SQLite从空白文件建表后写入经过筛选的字段，不复制完整研究数据库再删除字段，避免原始载荷残留在空闲页中。保留停用编号，不复用。原图未放入包；卡片仍包含来源照片的可见部分，不能保证别人无法复制卡片。

## 无原图运行

```sh
python3 skills/mcd-hidden-explorer/scripts/numbered_catalog.py cards 11 23 \
  --database <加工卡资料目录>/numbered-catalog.sqlite3
```

编号查询在数据库同目录发现 `image_policy=processed_cards_only` 的catalog后使用包内加工PNG。随机推荐和按餐品找继续使用现有 `discover.py`，无需开发目录的原图。实际安装和手机端仍独立验收。

## Git防线

- `.gitignore` 排除work、原型、本地安装目录，以及source-images、original-images、raw-images等目录。
- `.gitattributes` 对相应研究目录与原图路径设置export-ignore。
- 已跟踪文件不会因为增加ignore自动取消跟踪。当前本地索引及所有本地Git历史没有图片或ZIP；后续提交前仍须检查暂存文件。没有为本次操作修改历史、提交或推送。
- 加工卡拟放 `assets/cards/` / `assets/thumbnails/`，不被原图排除规则阻断；公开前仍需按项目现有素材依据规则处理。
