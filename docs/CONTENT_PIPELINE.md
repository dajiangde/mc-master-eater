# 添加吃法到完整 Skill 安装包

两种入口使用同一套投稿结构和 `content_pipeline.py add`。正式真源位于 `skills/mcd-hidden-explorer/content/catalog.json`；旧 schema 1 文字 catalog、本地研究表与 SQLite 都不是这份真源。SQLite 和展示 catalog 从正式收录数据生成，不再分别手工维护。

## 普通用户提 Issue

1. 在 `dajiangde/mc-master-eater` 的 Issues 选择「补充隐藏吃法」，填写餐品、做法、出处及图片依据。未知项如实写未知。
2. 机器人将表单转换成与本地添加相同的投稿 JSON，并更新一条缺项说明。普通用户无需填 SKU、写脚本或启动服务。
3. 维护者加 `intake:prepare` 标签，生成包含 `submissions/issue-N.json` 的草稿 PR。也可在 Actions 的 `Hidden recipe intake` 输入 Issue 编号，保持 `import_ready=false`。
4. 维护者核对资料，并补齐 `products`、`configuration`、`sources`、`menu_scope`、`image` 和精简的 `display`。完整字段见 `references/submission-template.json`。
5. 在本地补齐 PR 中的 JSON，走下一节的共用收录器；或在 Issue 的「维护者配置」补齐这些 JSON 字段，加 `intake:approve` 标签（或手动运行并勾选 `import_ready`），在临时 runner 制卡并正式收录。审批以触发人的仓库写权限为准，投稿正文不能自行授权。
6. 新 PR 或仅有机器人待审提交的原 PR 会包含正式资料、主卡与缩图。含人工修改的分支不会被自动覆盖；此时使用本地收录器完成原 PR。重复运行不会另开相同投稿 PR。

标签需要在仓库创建，或直接使用手动触发入口。编辑 Issue 不会继承此前审批；重新审批须移除再添加标签或手动触发。正文里的命令、路径和配置只作数据，不执行。

公开 Issue 的附件本身是公开投稿：只上传本人拥有或已获准公开的配图，不上传现有研究库私有原图。照片仅在临时 runner 制卡，提交和安装包都只带加工图。权利未知时保留待审，不下载入库。本机研究原图继续走本地路线。

机器人 PR 的 CI 可能显示 `Approve workflows to run`；维护者需要点击后才能得到安装包检查结果。PR 已创建不代表测试通过。

## 你自己添加（也用于完成投稿 PR）

本节是开发维护流程，普通安装用户不需要执行。开发环境需要 `requirements-content.txt` 中的 Pillow 和中文字体；运行时不依赖 Pillow。

1. 从 `skills/mcd-hidden-explorer/references/submission-template.json` 复制 JSON 到本地待审文件；也可直接使用机器人 PR 的 `submissions/issue-N.json`。
2. 核对配方和图片依据，填好商品与门店参考上下文。`key` 是永久投稿身份，使用唯一英文短名或沿用 `issue-N`。`published_at` 未知可为 `null`，采集日期须明确。
3. `products` 每项须有 `name`、`code`、`time`、`evidence`；口味选项另填父商品。`configuration.purchase_quantities` 以商品编码为键，逐项给 `quantity`、`status`（`source_reported` 或 `purchase_suggestion`）、`basis`。口味组须有默认选项，并属于同一父商品。`display` 只放卡面简写，完整步骤保留在 `steps`。
4. 用共用收录器制卡与入库，原图可以位于忽略的研究区：

```sh
python3 skills/mcd-hidden-explorer/scripts/content_pipeline.py check-submission --submission <投稿JSON>
python3 skills/mcd-hidden-explorer/scripts/content_pipeline.py add \
  --submission <投稿JSON> --photo <本地原图> --reviewer <复核人> \
  --font <中文字体文件>
```

macOS 的 PingFang、Linux 的 Noto Sans CJK 可自动发现；`--font` 可省略。编号由当前主库自动分配。失败不会留下半套新图；重复 key 拒绝另发编号。`--card` 和 `--thumbnail` 可用于已按分配编号制好的加工图，必须分别为 1080×1440 和 360×480，维护者须核对图上的编号。

5. 将生成的 `content/catalog.json`、`content/cards/Uxx.png`、`content/thumbnails/Uxx.png` 放进同一个 PR。不提交原图、环境配置或采集历史。新图不含未经核对的热量角标，购买清单的热量始终读取官方营养表。

## 构建和验收

```sh
python3 skills/mcd-hidden-explorer/scripts/content_pipeline.py validate
python3 skills/mcd-hidden-explorer/scripts/content_pipeline.py build \
  --output <新的目录>/mc-master-eater --zip <新的目录>/mc-master-eater.zip
python3 -m zipfile -e <新的目录>/mc-master-eater.zip <新的验收目录>
python3 <新的验收目录>/mc-master-eater/scripts/content_pipeline.py verify \
  --bundle <新的验收目录>/mc-master-eater
python3 <新的验收目录>/mc-master-eater/scripts/bundle_smoke.py \
  --bundle <新的验收目录>/mc-master-eater
```

`Content and installable Skill` 在 PR、main 更新和手动触发时执行：

- 运行现有运行时测试与收录端到端测试。
- 对照主分支，拒绝删除／重排既有身份、复用停用号或抢占已分配编号。多个 PR 同时新增时，后合并者须基于最新主分支重建编号和卡片。仓库应将 `validate-and-build` 设为必过检查，并要求合并前分支保持最新；拥有绕过权限的手动合并不属于此保证。
- 检查 PNG 数据、尺寸、哈希、编号和未登记文件；从干净数据重新生成 SQLite。
- 构建 ZIP，解压到新目录，从安装副本加载模块，逐项运行随机池覆盖、按餐品找、适用优惠推荐、选号、当前清单、购买清单、父商品核价结构和缺失营养处理。
- 输出完整 ZIP 到该次 Actions 的 Artifacts。安装包无需本机原图、`work/` 或源码路径。

首次收录目录为空是有意保留的有效状态：当前 22 张本地卡未被自动转成公开授权素材。CI 仍用明确标注的合成图片跑通完整链路，但不发布合成样本，不生成空安装包。此状态不会覆盖现有本地含图安装；已有素材按独立审核流程迁移。

## 版本发布与安装

合并生成可下载的构建产物。需要发版时，维护者手动运行 `Release reviewed Skill`，输入 `vX.Y.Z`。它针对精确提交重建和检查 ZIP，创建包含 ZIP、manifest 的草稿 Release，检查后再手动发布。不会自动发布每次投稿，不调用 MCP、不领券、不下单。

用户下载完整 ZIP 后通过 WorkBuddy 安装入口导入或更新，不能仅复制仓库源码目录。ZIP 根目录与 Skill 标识一致，当前为 `mc-master-eater`。旧安装不会因 GitHub 更新自动刷新。手机、Windows、云端和真实门店查询仍须独立验收；CI 只证明包和离线软件链路。

启用时还需在仓库设置确认 Actions 允许创建 PR，并配置上述必过检查。代码入仓、真实 Issue 触发、真实 runner 成功、正式发布、宿主验收分别记录在 `STATUS.md`。
