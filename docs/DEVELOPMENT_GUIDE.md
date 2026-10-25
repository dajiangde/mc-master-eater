# 开发、资料与验收规范

## 目录和交付边界

Skill 身份统一取 `SKILL.md` 的 `name: mc-master-eater`，中文名“麦门老吃家”；WorkBuddy 安装路径为 `~/.workbuddy-ai/skills/mc-master-eater/`，ZIP 顶层也按该 name 生成。`skills/mcd-hidden-explorer/` 仅是保留的内部源码路径。旧安装目录应完整备份移出 skills，避免两个名称同时加载；历史快照不改名。

| 目录／文件 | 角色 | 更新规则 |
| --- | --- | --- |
| `skills/mcd-hidden-explorer/` | 公开候选的唯一维护入口 | 新功能在这里实现，使用包内相对路径 |
| `tests/` | 公开候选的检查 | 跟随相应功能维护 |
| `mcd-hidden-explorer/` | 本地研究原型 | 保持忽略，修改前明确研究目的，不能直接作为发布包 |
| `docs/` | 需求、状态、调研与规则 | 状态写在 STATUS，需求写在 PROJECT_CONTEXT，避免互相冲突 |
| `work/research/` | 私有来源、素材和历史报告 | 不纳入公开提交；新增记录标日期和证据类型 |
| `work/validation/` | 本地测试、截图、历史快照 | 历史原文保持原样，新结论覆盖在 STATUS 中说明 |
| `CONTEST_DECLARATION.md` | 官方声明候选 | 未核对官方原文前不宣布一致；不可自行改写规则内容 |
| `workbuddy.md` | 真实开发摘要 | 区分 WorkBuddy 操作与 Codex 整理，不冒充完整导出 |

本轮末尾已发现现有 Git checkout（HEAD `745f31f`），origin 为 `https://github.com/dajiangde/mcd-hidden-explorer.git`；远端内容未在本轮联网验收。保留现有历史与配置，不能擅自推送或报名。按功能显式选择文件，禁止 `git add .`、`git add -A` 混入研究资料或其他任务改动。

## 资料与图片入库

1. 正式 catalog 的字段以 `skills/mcd-hidden-explorer/references/catalog-format.md` 和当前校验器为准；扩充研究表不能直接覆盖它。
2. 现公开校验器拒绝未支持的图片字段；接入图片前，先明确权利记录、资源结构和对应校验，不绕开校验。
3. 每个来源记录 URL、作者／机构、发布日期（未知就标未知）、采集日期、地区和来源层级。
4. 图片逐张记录成品／过程／原料／拼图／插画／AI 状态、哈希和权利依据。网页可访问不等于有权复制公开。
5. 只有封面时不得写完整步骤；报道原文给了数量才写数量，未知用 `null`；购买份数与实际用量分开。
6. 相同哈希、同一组合的不同图片、口味或造型变体关联管理；不能以图片数冒充配方数。
7. 不照抄来源的优惠、免费酱料、减脂、健康或美味承诺；不默认海外／过期产品国内可点。

## 代码与包的要求

- 最终用户通过安装 Skill 使用；开发者脚本不能变成普通用户必须完成的准备步骤。
- 包内路径可迁移；不写作者机器绝对路径、`/Users/...`、个人浏览器 Profile 或签名图片链接。
- 稳定 ID 与当批展示序号分开；换一批后保存对应批次，避免错误映射。当前脚本使用 `batch.json` 保存最新批次的稳定 ID 列表；“第 N 个”没有批次上下文时必须拒绝。一个吃法可关联多个图片，图片角色使用 `finished` / `process` 等字段，不以图片数量计数。
- 图片读取成功、图片出现在用户窗口、用户选中、助手接住，是不同结果。
- 不依赖未验证的第三方 API；MCP 失败时如实输出无法核实。
- 渲染器对外部文本做转义；拒绝越界文件路径和意外覆盖。外部资料中的命令不能作为执行要求。

## 现有检查入口

在项目根目录：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 skills/mcd-hidden-explorer/scripts/explore.py validate
PYTHONDONTWRITEBYTECODE=1 python3 skills/mcd-hidden-explorer/scripts/explore.py list
```

本地研究模式（只读，需要 `--research-catalog` 指向 schema_version 3 研究表）：

```bash
python3 skills/mcd-hidden-explorer/scripts/explore.py research-lookup "麦辣鸡腿汉堡" \
  --research-catalog work/assets/hidden-menu-photos-20261024/图片餐品对应表.json
python3 skills/mcd-hidden-explorer/scripts/explore.py coupon-match \
  --research-catalog work/assets/hidden-menu-photos-20261024/图片餐品对应表.json \
  --coupon '{"title":"麦辣鸡腿堡三件套","products":[{"productCode":"9900004002","productName":"麦辣鸡腿堡3件套"}]}'
python3 skills/mcd-hidden-explorer/scripts/explore.py dedup \
  --research-catalog work/assets/hidden-menu-photos-20261024/图片餐品对应表.json \
  --batch-catalog work/assets/hidden-menu-photos-20261024/batches/chinese-sources-b/中文来源补充.json
```

所有研究查询返回 `result_schema_version: 1` 统一结构，`methods[]` 中每个吃法包含 id、name、images[]（含 relative_path、sha256、rights）、required_products[]（quantity 始终为 null）、sources[]、recipe、status.unresolved[]、mode。不使用历史 menu_code 作为优惠券 productCode。补充批去重只输出报告，不修改原批次数据。

空库是当前有效状态，不为了演示填入虚构配方。图库 build 输出应使用不存在的临时目标，不能覆盖源资料。历史原型检查位于 `work/validation/prototype-20261024/bundle/verify_package.py`，只证明冻结版本，不代替公开候选测试。

## 跨端验收矩阵

每条样本记录日期、宿主版本、模型／模式、显式或隐式选择 Skill、安装版本和哈希、输入、实际输出、截图、是否发生人工修正。

- A：静态检查、数据与图片哈希、路径迁移。
- B：普通浏览器实际图片、筛选和选择。
- C：WorkBuddy 桌面通过正常导入安装，在不含源码的新工作区调用。
- D：手机 App 分云端工作／连接电脑，分别验证资源、真实图像、交互和承接。
- E：真实官方 MCP 的门店、菜单、详情、映射与价格；与离线示例分开。
- F：用户是否觉得探索方便、配方可理解；与技术成功分开。

不能凭截图、README、自测数量、Star、模型读取图片工具结果，断言真实用户已看见图片。`present_files` 文件卡不自动等于聊天内图片。单条样本成功不能替换失败样本后宣布整套回归通过。

## 研究与账号边界

默认 Agent Reach。登录依赖操作先核对专用研究浏览器身份与平台页；失败或风控立即停止，不重试换路、不用日常浏览器／Cookie／钥匙串兜底。公开文档与代码可按支持的公开路线读取。用户自己登录，不向聊天索要 Token、验证码或密钥。

UI 操作要避开其他运行会话。发现窗口被其他端切换、提示草稿落入别的任务，先清空自己的未发送草稿并停止发送，不归因于产品业务失败。

## 发布前独立检查

素材权利、真实查询范围、比赛文件与官方声明、敏感信息、真实 WorkBuddy 记录各自核对。归档截图、扩充研究图、原始来源正文和本地配置不得混入公开包。发布、推送、报名、评论、订单、领券不因本次整理而获得授权。

## 隐藏吃法收集标准（2026-10-24）

后续收集和筛选须执行[隐藏吃法收集标准 v1](COLLECTION_STANDARD.md)：有对应实拍图、关键商品可可靠识别、排除时令及限时／停供核心商品，数量步骤可操作且原料能同时获得。未知供应状态不得当作常规；只有图片的线索不进入可操作池。历史研究原样保留，以新对应表记录缺项。


## 本地研究读取与正式入库分离

研究探索用 `explore.py` 的 `research-lookup` 和 `coupon-match` 子命令读取已授权的 schema 3 图片餐品对应表；公开候选仍用 `explore.py` 的 `lookup`、`validate`、`list`、`build` 与公开 catalog。研究数据使用 `research_validate()`（schema_version 3），公开数据使用 `validate()`（schema_version 1）；两种模式严格隔离，研究数据不会被当作公开 catalog 校验，公开 catalog 不会被研究数据污染。

- `research-lookup <商品名> --research-catalog <path>`：按商品名查找研究记录，返回 record_id、吃法名、图片 ID、来源 URL、商品映射、配方状态和所有待核字段。读取器不生成或导入正式 catalog。
- `coupon-match --research-catalog <path> --coupon '<JSON>'`：将真实优惠券匹配到研究记录，区分 exact（商品编码或名称完全一致）和 possible（名称包含或关键词关联），usability 始终为 `not_yet_confirmed`。不把 possible 写成 confirmed，不把历史 menu_code 当作优惠券 productCode。

完整条目保留来源、数量原文、商品映射、图片与权利、配方／实拍／非时令待核项。商品映射不把候选口味改成确定商品，数量原文不自动解析为下单数量，历史门店证据不变成实时适用性。图片、来源和权利记录不得从本地研究目录复制到公开包。


## 2026-10-25 用户调整：主要餐品优先

执行[收集标准v2](COLLECTION_STANDARD.md)当前章节，覆盖上文严格复刻要求。常见酱料、奶油球等小料不阻断推荐；风味、部位及同用途食材可简单替代，保留差异说明。用户要求抹茶两款移出推荐。来源证据、实用采购方案及试做状态分开记录；不必把小料逐一查成MCP商品。


## 推荐入口（随机／按餐品／按优惠）

`scripts/discover.py` 是推荐入口，三个入口共用一份会话文件，展示顺序、已看编号和选中清单都记在 `session_state`。

```bash
DB=<unified-v2/隐藏吃法编号.sqlite3>
SESS=<session.json>

# 随机：优先没看过、跨类别，最多三款
python3 scripts/discover.py random --database "$DB" --session "$SESS" [--seed N]

# 按餐品：识别常见叫法；无结果不记轮次
python3 scripts/discover.py by-product "想看薯条相关的" --database "$DB" --session "$SESS"

# 按优惠：把 MCP 返回的券传给脚本
python3 scripts/discover.py by-coupon --coupon '{"title":"...","products":[...]}' \
  --database "$DB" --session "$SESS"

# 清单
python3 scripts/discover.py select U21 --round RND001 --database "$DB" --session "$SESS"
python3 scripts/discover.py select U08 --replace --database "$DB" --session "$SESS"
python3 scripts/discover.py deselect U21 --database "$DB" --session "$SESS"
python3 scripts/discover.py selection --database "$DB" --session "$SESS"

# 购买清单
python3 scripts/discover.py plan --database "$DB" --session "$SESS" --plan-file plan.json
```

入口判定：用户已说清方向就直接推荐，不询问模式；只有首次打开且没有方向时才给三个入口和示例说法（`discover.py entries`）。

**轮次只登记一次。** 三个入口内部都会调 `recommend_round` 并返回 `round_id`，不要再补一次 `session_state.py recommend`，否则同一轮会记两条。

**换一批要读已看记录。** `by-product` 用 `seen_methods` 排除已展示的编号：同主题先给没看过的三款，耗尽时返回 `count=0`、`exhausted=true` 和不新开轮次，并说明"这个主题的吃法都看过了"。`random` 一直如此。

**替换先校验再改。** `select --replace` 会先跑 `session_state.validate_selection`（编号存在且在售、轮次归属正确），通过后才移除旧项；任一校验失败，原清单原样保留。

匹配规则由 `references/product-aliases.json` 决定：

- `families`：商品族，按规范名与别名匹配；`excludes` 保证薯饼不进入薯条结果，反之亦然。
- `category_terms`：类别词（炸鸡／小食／汉堡／甜品／饮品），覆盖多个 SKU，结果标“同类餐品匹配”。
- 归一化只去掉开头意图词和结尾语气词，不改动商品名本身。
- 无匹配返回 `no_match_reason` 与 `suggestions`（families／categories），且不创建轮次。

会话字段：`rounds[].shown_methods` 保留展示顺序，`seen_methods` 支持换一批回避，`current_selection` 跨入口保留。每次修改后用 `summary` 报“当前选中：X(8号)”。

## 优惠关联边界

- 券来自 MCP 实调；`coupon-link` 只做关联，`usability` 恒为 `not_yet_confirmed`。
- 关联强弱：商品名/编码精确 100，名称包含或同类 70，券名或类别文案 30。
- 没有券、接口失败或关联为空时不清空清单，只说明原因。
- 精确总价必须 `calculate-price` 之后才给；本层不输出价格。

验收记录：`work/validation/entry-acceptance-20261025/ACCEPTANCE.md`。

## 会话选择状态（连续推荐）

`scripts/session_state.py` 管理连续对话中的推荐轮次和用户选择清单。状态文件是 JSON（session_schema_version 1），不在 Skill 包或研究数据内。

`--session` 与 `--database` 可前置也可放在子命令之后，两种写法等效；文档统一写成子命令在前。

```bash
# 初始化空会话
python3 skills/mcd-hidden-explorer/scripts/session_state.py init --session /tmp/mcd-session.json

# 记录一轮推荐（返回 round_id 如 RND001），带 --database 时先校验编号
python3 skills/mcd-hidden-explorer/scripts/session_state.py recommend U01 U02 \
  --session /tmp/mcd-session.json --database <db> --query "随便看看" --source "numbered_catalog"

# 用户选号：不存在或已下架的编号整批拒绝
python3 skills/mcd-hidden-explorer/scripts/session_state.py select U02 \
  --session /tmp/mcd-session.json --database <db> --round RND001

# 取消选号
python3 skills/mcd-hidden-explorer/scripts/session_state.py deselect U02 --session /tmp/mcd-session.json

# 查看完整状态
python3 skills/mcd-hidden-explorer/scripts/session_state.py status --session /tmp/mcd-session.json

# 清空当前清单（保留历史）
python3 skills/mcd-hidden-explorer/scripts/session_state.py clear --session /tmp/mcd-session.json

# 完全重置
python3 skills/mcd-hidden-explorer/scripts/session_state.py reset --session /tmp/mcd-session.json
```

状态结构：
- `rounds[]`：每轮推荐含 round_id（RND001…）、shown_methods、query、source、catalog_checked、created_at。
- `selections[]`：选择历史含 method_id、round_id、name、number、selected_at；取消时追加 deselected_at。
- `current_selection[]`：当前选中编号列表，跨轮次累积，支持增删。

设计规则：
- 带 `--database` 时，U 编号必须存在且 `active=1`；任一款不合格则整批拒绝，不写入会话。
- 选号时如提供 `--round`，验证编号确实在该轮展示过。
- 重复选择幂等（不重复加入当前清单）。
- 取消选择保留历史，只标记 deselected_at。
- `current_selection` 是 MCP 配置阶段（第 3 阶段）的输入基础。
- 选择不等于下单，不触发 create-order。
- 状态文件放临时或工作目录，不随 Skill 分发。

## 图片交付与旧页面定位

图片交付路径统一为：`numbered_catalog.py cards <编号…> --database <db>` 取绝对路径，再由 `present_files` 交付图片卡片。每张卡片同时给出编号、卡面名和 `caption`；`images_ready=false` 时如实说明缺图，不用 AI 生成图替代来源图片。

旧图库页面定位：

| 页面／字段 | 当前定位 |
| --- | --- |
| `work/assets/.../统一隐藏吃法图库.html` | 历史浏览入口，可搜索筛选；不作为图片交付路径，不作为验收证据 |
| `assets/gallery.html`（Skill 内） | 可选离线入口，公开数据为空时不生成内容 |
| `隐藏吃法资料总览.html` | 已指向统一页的历史别名，保持原址可用 |
| `images[].absolute_path` | `cards` 输出的本地绝对路径；仅供本机展示，不写入公开包 |
| `images[].relative_path` / `sha256` | 相对统一目录的路径与哈希，用于完整性核对 |
| `hero_image_absolute_path` | 卡片首图；`images_ready` 与 `exists` 共同判断可用性 |
| `caption` | 逐字使用，不另行拼写编号或餐品名 |
| `required_products` / `optional_products` / `product_choices` | 基础商品 / 可选 / 二选一，不把可选写成必需 |
| `quantity` / `purchase_quantity_suggestion` | 未知保持 null；建议购买量不等于来源用量 |

旧 HTML 与卡片说明冲突时，以 `cards` 返回字段和本表为准；不因旧页面显示而改写配方、份数或价格。

验收记录：`work/validation/continuous-acceptance-20261025/ACCEPTANCE.md`（连续推荐五步、编号库拒绝、图片卡片就绪性）。

## 父商品 + 选项编码（配置与核价）

规则正文在 `skills/mcd-hidden-explorer/references/parent-option-rule.md`。要点：`query-meal-detail` 的 `rounds` 为空才是可直接核价的在售单品；`rounds` 非空是父商品，口味／规格只写在 `roundList`；`choices[].code` 不能当 `productCode`。

`scripts/meal_config.py` 把规则做成纯函数（无网络、不算价），只生成 `calculate-price` 的 `items` 项：

```bash
# 判定编码角色；--code 可查某个编码是不是该商品的选项
python3 skills/mcd-hidden-explorer/scripts/meal_config.py roles \
  --detail work/validation/coupon-check-20261025-u11/meal-detail-9900008754.json --code 1217

# 生成请求项（默认取 isDefault 的选项）
python3 skills/mcd-hidden-explorer/scripts/meal_config.py item \
  --detail work/validation/coupon-check-20261025-u11/meal-detail-9900008754.json --quantity 1

# 指定口味
python3 skills/mcd-hidden-explorer/scripts/meal_config.py item \
  --detail work/validation/coupon-check-20261025-u11/meal-detail-9900008754.json --choose 4900
```

非法配置抛 `MealConfigError` 且不生成请求：选项不属于该商品、轮次标签不存在、必选组无默认、超出 `maxQuantity`、数量小于 1。`600012 促销规则不支持该商品` 用 `explain_failure()` 解释，只给方向（选项编码当了商品编码／券与商品不匹配），不预设结论。

回归：`tests/test_meal_config.py`（24 项），夹具是真实抓取的 `query-meal-detail` 返回。

## 进入购买配置后的统一核券（券 → 餐品覆盖）

`by-coupon` 是用户明确要求按优惠浏览的方向（券 → 有哪些吃法）；`coupon-check` 是购买配置方向（当前计划 → 券能不能覆盖）。后者仅在用户要求配置／核价后执行 `discover.py purchase`、进入 `phase=purchasing` 后统一跑。普通选号、确认看过图片只加入备选，不查个人券或问门店。

```bash
python3 skills/mcd-hidden-explorer/scripts/discover.py coupon-check \
  --session <session> --database <db> \
  --coupons '[{"title":"...","couponId":"...","couponCode":"...","priceYuan":22.9,
               "validFrom":"2026-10-23 00:00","validUntil":"2026-11-23 23:59",
               "products":[{"productCode":"9900004002","productName":"麦辣鸡腿堡3件套"}]}]'
```

- 正常会话始终自动复用其当前购买计划；`--now` 可覆盖时间，便于复现。无会话的显式 `--ids` 仅用于开发者离线检查已有券数据，不发起 MCP 查询。
- `--plan <plan-file>` 只兼容同一会话已经登记的文件；省略时也保留改过的口味和份数。当前选择变化时核券入口先同步计划，价格与热量入口遇到未同步计划则拒绝。
- 判定顺序：编码一致（含父商品编码）> 名称完全一致 > 同家族 > 不覆盖。同家族记为 `family_only`，同时计入 `missing`，不当成覆盖。
- 正常会话输出当前计划各项的 `items[].coupons[]`（含 `covered`／`family_only`／`missing`／`valid_now`／`is_candidate`）、`best_coupon`、`missing_from_best`；编号离线检查仍输出 `methods[]`。
- `best_coupon` 只从候选里选：`valid_now=false`（过期、未生效、当天不在适用星期）一律不进候选；`valid_now=null`（有效期未知）保留为候选并标注待核。
- 券没有返回适用商品信息时状态为 `insufficient_info`，并在条目上给 `insufficient_coupon_info=true`。这**不等于**"没有优惠"，不能写成"没有适用券"。
- `usability` 恒为 `not_yet_confirmed`；`round_id` 恒为 `null`，不改清单、不产生新轮次。

回归：`tests/test_coupon_check.py`（22 项）+ `tests/test_flow_continuity.py` 的 `PlanCouponTests`。全量在 `tests/` 目录下执行 `python3 -m unittest discover -s . -t .`。

## 购买计划文件（会话内）

`discover.py plan` 从当前清单生成购买清单，并把**用户的调整**存进计划文件，后续重算不再回退到原配方。

```bash
python3 skills/mcd-hidden-explorer/scripts/discover.py plan \
  --session <session> --database <db>
python3 skills/mcd-hidden-explorer/scripts/discover.py plan \
  --session <session> --database <db> \
  --choices '{"U06":{"派口味二选一":"香芋派"}}' --quantities '{"中薯条":1}'
```

- 计划文件结构：`plan_schema_version` + `methods[]` + `choices{}` + `quantities{}`。它是会话内临时产物，不扩展成交易系统。
- `quantities` 的键按优先级匹配：`方法编号:商品名` → 商品名（营养表口径）→ 展示名。命中即写 `quantity`、`quantity_source=user_override`，并在 `quantity_basis[]` 追加一条用户指定记录。
- 共用商品默认相加（两款吃法都要中薯条 → 2 份）；用户说"一份"后重算、换口味、核券、核价、热量都读 1 份。
- `basket.py price-items` / `calories` 也接受计划文件（内部有 `methods` 时自动重算）。
- 首次自动在会话文件旁保存 `<会话名>.plan.json`，并在会话登记绝对路径；自定义路径仅首次指定。后续命令自动复用，禁止每轮重建默认计划。文件损坏、丢失、跨会话或价格／热量入口读到过期选择时拒绝继续。
- `purchase` 只记录购买配置意图，不代表同意领券、下单或支付。`browse` 回到探索并保留计划；`clear`／`reset` 才清除旧调整。已有 v1 会话缺少 phase 时按探索加载，不凭历史选号推断购买授权。

## 采购与确认数据契约（2026-10-25 修复）

从 `discover.py selection` / `select` 获取结构化产品后，用 `discover.py plan`（或 `basket.py plan`），不要用旧 `merge` 生成下单数量。`discover.py selection` 返回的 `required_products` 是完整对象（含 `reference_menu.code`／`parent_code`）和 `product_choices` 默认口味，可直接进计划；这也是"选号 → 计划"不再空清单、不再报"需要先选口味"的原因。每项 `quantity_basis[]` 留存来源/采购建议/用户指定/待确认；`quantity_needs_confirmation` 为true时在最终摘要说明建议份数，用户确认整单即可，不另起一轮逐项授权。维护表 `purchase_quantities` 可存quantity/status/basis；sync后构建全包。

核价请求必须留全：`price_request` 存本轮成功的 `calculate-price` 实参，`items` 连同 `roundList`、特调及未知嵌套字段完整保留；官方响应另外保存在验证目录。摘要另带整数分的 `price_cents`、`price_checked_at`、取餐方式、购买清单热量和隐藏吃法编号。`basket.py confirmation` 会从核价请求补齐缺失的门店/订单类型/beType/商品，拒绝将缺失口味的展示清单当成完整配置。`ready_for_confirmation` 表示可展示，`ready_for_order` 始终false。

展示摘要时内部保留本次 `confirmation_fingerprint`。只有真实用户明确同意后，读最新摘要及本次确认的指纹，按实际MCP工具Schema准备待提交参数，再执行：

```sh
python3 scripts/explore.py order-check --summary summary.json --confirmed --confirmation-fingerprint <本次用户确认的指纹> --order-request order-request.json
```

指纹不要求用户输入，由Agent关联用户刚看到的那份摘要。不能在用户确认后偷偷改配置再重新计算指纹来冒用旧同意。校验脚本本身不发送网络请求；通过后也只能提交被校验的同一份参数。核价中的配置字段不得丢失或改变；允许新增当前摘要中的取餐方式。若工具Schema需要不同结构/额外字段，先核实并补齐经过测试的转换，不删字段绕过校验。

换口味/去酱/份数变化先更新实时配置并重新核价和计算热量，再生成新摘要；确认指纹不同，旧确认无效。`live_item` 用于传入按本轮详情构建的完整商品项，数量须与计划一致；无 `live_item` 的单口味模板只是历史结构，不证明当前门店SKU可用。来源2片也必须核对当前售卖单位。

构建以源码为真源，安装前备份旧包，整包安装后逐文件SHA256与manifest核对，不只比较SKILL.md；manifest记录 `bundle_id` 和编号库策略 `policy_sha256`。本地研究包不构成图片公开复用授权。


## 当前购买计划的连续编辑与验收补修（2026-10-25）

用户已授权 Codex 在 WorkBuddy 初步修复后直接检查和补修。本节覆盖旧章节中重新从原配方重建清单的说明。正常入口统一为 `discover.py plan --session <session> --database <db>`；计划路径自动由会话复用，后续核券、核价请求和热量均读取此计划文件。

- `--choices` 修改口味，`--quantities` 修改购买份数。单款吃法的口味组使用稳定组身份保存份数，更换商品名后不回退，也不把这份组设置套到替换后的另一款吃法。
- `--optional '{"U11":["脆脆薯条"]}'` 选择资料中已有的可选餐品；空列表取消该款的可选加购。默认不加。可选餐品和份数都写入任务计划文件，不写入 Skill 资料库。
- 计划编辑先验证完整结果，再原子保存。未知口味、非法数量、未知可选项报错时，原文件逐字节不变。选择清空后同步为空计划，空计划不能生成核价请求；核券不接受与当前选择不一致的旧计划。
- 原料确认阶段即展示逐项与合计参考热量；最终确认使用实际购买规格和份数。营养读取器支持现存官方 MCP 的表格字符串响应及结构化数组；解析失败不按零计。
- 查券是只读动作，`next_step.requires_user_confirmation=false`；该字段不授权领券或下单。门店券仍等门店及取餐方式明确后查询。优惠核价失败先排查配置，不将一次失败当成全部优惠不存在。

新增 `tests/test_plan_editing.py` 覆盖连续编辑、持久化、清空、过期计划、可选项及营养响应格式。当前测试总数以 STATUS 的最新验收章节为准；CLI/离线验收不替代真实订单、支付或手机验收。
