# 固定编号选择与商品映射

用户说“11号”“我要11号、12号”“十一号和十二号”时，读取编号数据库，而不是从上一条回复或照片猜测。卡面 `11号`、规范 ID `U11`、数据库 `number=11` 是同一身份。筛选、换批和排序不改变编号；移除吃法保留停用编号，不复用给其他吃法。

## 开发/研究调用

本项目维护数据库相对项目根目录：
`work/assets/hidden-menu-photos-20261024/unified-v2/隐藏吃法编号.sqlite3`。

先用已明确授权且实际存在的数据库路径调用：

```bash
python3 scripts/numbered_catalog.py select '我要11号、12号' --database <database>
python3 scripts/numbered_catalog.py list --database <database>
python3 scripts/numbered_catalog.py cards 1 8 --database <database>
```

安装副本没有此研究库时应报告缺少资料；不得寻找私人绝对路径，也不把公开空 catalog 当作已有22条。本功能的脚本可以随 Skill 分发，研究数据库和第三方图片不自动进入安装包。

`select` 返回每款的 `id`、`number`、`display_number`、规范名、卡面名、必需商品、可选商品、二选一商品组、来源、图片及整理建议。先复述选中的编号和名称，再展示对应商品。

### 选号前必须查库

加入当前清单前，用 `session_state.py select --database <db>` 校验；`numbered_catalog.py select` 自身也只返回 `active=1` 的编号。

- 编号不存在 → `资料库中不存在：U99`，整批拒绝。
- 编号已停用 → `U12（12号）「麦辣鸡翅去骨吃法」已停用，编号保留不再分配`，整批拒绝；停用编号永久保留，不复用、不前移。`numbered_catalog.py retired` 可列出全部停用编号。
- 一次选多款时，只要有一款不合格，全部不加入；不做部分成功。
- 拒绝时不写入会话，不产生"已加入"的中间状态。

### 图片卡片字段

`cards` 每款返回：

- `id` / `number` / `display_number`：稳定编号与卡面编号，同一身份。
- `name`（规范名）、`card_title`（卡面名）。
- `images[]`：`image_id`、`absolute_path`、`relative_path`、`sha256`、`exists`。
- `hero_image_absolute_path`：交给 `present_files` 的路径；`images_ready` 为 false 表示缺图。
- `caption`：`[图片] U01 · 卡面名｜对应餐品：…`，文字说明逐字使用，不另行拼写。
- `required_products` / `optional_products` / `product_choices`：`required` 是已锁定的固定餐品；`product_choices` 是父商品下的口味/规格选择，某些吃法（如 U06 派拌麦旋风）可以整份都由选择组构成，此时 `required` 为空是正常的。
- `optional_notes`、`suggested_steps`、`tested_by_project`：整理建议与试做状态分开，不写成官方做法。

- `required_products` 是基础商品；`optional_products` 不能自动变成必需。
- `product_choices` 每组只选一项；例如派口味与麦旋风口味分别任选，不要求买齐四种。每组带 `default_code` / `default_name`（默认方案来自资料与图片组合），用户不指定就用默认并说明可改。
- `quantity=null` 保持未知；`purchase_quantity_suggestion` 只是建议，不等于来源实际用量。
- `reference_menu` 仅历史门店菜单记录；用户准备配置时，重新通过当前 MCP 的门店、菜单、详情和价格核实。
- `reference_menu.code` 可能是**父商品下的选项编码**，不一定是可直接下单的商品编码。已核实案例：`1217` 奥利奥麦旋风属于经典麦旋风 `9900008754` 的必选口味组，核价须传父商品并带 `roundList`。使用前先 `query-meal-detail` 展开确认；通用规则与生成请求的脚本见 `parent-option-rule.md`。
- 同时选多款时用 `basket.py plan` 汇总：同一父商品同一口味合并成一行，份数按各款需求累加（`shared=true` 并注明来自哪几款），不重复列同一件商品。
- 基础商品外的奶球、酱料等见 `optional_notes` 和差异说明，不丢弃来源限制。
- 选择编号本身不授权领券、写购物车、创建订单或支付。

未知或停用编号使整次选择报错，不悄悄返回一部分。数量、范围或复杂否定表达交由助手先澄清；不要从“不要12号”提取12。输入“第二个”使用现有 `explore.py lookup --batch` 的当前推荐批次，缺批次就询问，不按固定2号解释。

## 维护

```bash
python3 scripts/numbered_catalog.py sync --source <统一吃法资料.json> \
  --policy <编号商品角色.json> --database <database>
```

只在用户授权维护时执行 sync。SQLite 是本地可重建的关系索引，原始配方/图片和出处仍保留在来源 JSON；角色规则将可选商品、口味组与卡面别名显式映射。同步以事务执行，编号冲突拒绝提交。新吃法分配未使用的 U 编号后再同步；不得重新排序分号。数据库无需独立服务，查询只读，无网络操作。


## 统一PNG与本地含图包

`cards`的`images[]`及`hero_image_absolute_path`现在只对应按稳定编号生成的PNG卡片。`source_images[]`保留原照片证据，不能当作推荐图。卡片由与编号库相邻的`base-cards-v1/catalog.json`按ID关联；显式`--card-catalog`可用于开发测试。缺图返回`images_ready=false`，缺图原因见`image_unavailable_reason`；哈希错误、路径越界、卡片/编号库版本不同均拒绝，不回退到旧照片。

`caption`沿用该PNG所用的展示标题和餐品清单，可选项保留可选标记。U12已停用，新鸡翅薯条夹心为U23；不能把12重新分给新吃法。

带`references/local-bundle.json`的本地安装包包含只读编号数据库及22张本地PNG，命令不必另给数据库路径。数据在包内`data/`，路径按包的位置解析；搬到新目录或无源码工作区仍可调用。没有这个本地包时，公开catalog仍为空，不能声称公开版安装就有22张卡片。


## 只有加工卡片的资料包
安装/测试上下文提供加工卡运行包时，使用其numbered-catalog.sqlite3。同目录catalog.json带image_policy=processed_cards_only标记，编号入口可直接定位cards/Uxx.png；不需要开发目录的原始图片，不查找私人路径，不回退原图。研究资料库及其完整原始来源继续留本地。原图不随运行包分发，原始归因页面链接可保留。


## 共同正文图片输出
所有返回加工PNG的入口，最终回复必须使用结果的 `response_markdown`，或逐款保留 `image_markdown` / `inline_markdown`。`present_files`与底部产物入口不能替代正文图片。不要把图片语法包进代码块、改成路径文字或普通链接。缺图时不伪造图片，详见SKILL.md开头共同规则。WorkBuddy桌面必须保留脚本生成的local-file:// URL（路径已URL编码），不能改成裸路径、相对路径或file://。随机/餐品/优惠/补充灵感/当前清单/编号卡查询共享image_delivery.py输出，不各自拼接不同规则。
