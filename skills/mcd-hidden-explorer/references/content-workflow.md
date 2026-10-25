# 统一收录与构建

仅维护者添加资料时读取。普通用户从完整 ZIP 安装后直接探索，不运行维护脚本。

- 正式收录真源是 `content/catalog.json`。Issue 生成的 `submissions/issue-N.json` 与本地 JSON 都用 `submission-template.json` 的结构，经同一个 `content_pipeline.py add` 收录。
- 待审、来源未知、图片使用依据未知的资料不能进推荐池。`step_basis=source_reported` 表示来源描述；`project_suggestion` 表示整理建议。`tested_by_project=false` 不得表述为试吃通过。
- 图片元数据须含作者、地区、日期、来源、实拍依据和允许加工及随包分发的依据；图片可访问不自动满足准入。已有本地研究素材不因本流程自动转成公开素材。
- `products[].code` 是有查询上下文的历史参考编码；口味选项同时给 `parent_code`、`parent_name`。`configuration` 管理可选项、口味组、默认口味以及逐项购买份数和依据。实时核价仍重新查询官方详情。
- 固定编号由收录器分配。历史 1～23 号保留，12 号停用；已收录条目只能保留原 ID 或停用，不删除重用。并发 PR 必须基于最新主分支重新检查。
- 本地原图只用于制卡，收录目录仅保存加工卡、缩图及经筛选的资料。制卡不复制原图、EXIF 或签名链接。
- 使用 `content_pipeline.py build` 生成完整安装包，不能只复制源码目录。包内包含脚本、规范、编号库、加工卡、缩图和哈希清单；`references/public-bundle.json` 使普通推荐自动使用随包数据。ZIP 根目录使用 SKILL.md 的 `name`，当前为 `mc-master-eater`。
- `build_local_bundle.py` 仍用于旧资料的授权本地测试，不通过改标识来冒充公开发布。两种资料经各自编译路径处理，不能直接覆盖旧 `references/catalog.json`。

维护命令与 GitHub 操作见仓库 `docs/CONTENT_PIPELINE.md`。构建、可分发、线上发布和宿主显示分别记录。
