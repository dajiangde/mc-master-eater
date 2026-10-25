# WorkBuddy 图片与交互调研

核查日期：2026-10-24。用户明确的手机入口为 WorkBuddy 手机 App；不能拿小程序、微信机器人或普通手机浏览器的能力替代它。

## 结论与建议

优先验证聊天内图片／图片产物与编号选择；完整 HTML 图库保留为补充。用户反馈手机 HTML 打开后只显示源码，说明桌面图库通过尚不足以验收安装后的跨端体验。PNG 也不能未经测试就宣称在聊天正文直接显示。

同一张本地 PNG 分别测试正文引用与 `present_files`，再测四格图和编号承接。如果仍只得到文件卡，应记录为「文件交付」，不能当成「原生聊天图片」。

## 官方能力与不能外推的边界

| 路线 | 当前文档依据 | 边界 |
| --- | --- | --- |
| 桌面文件产物／网页 | [结果查看](https://www.workbuddy.cn/docs/workbuddy/Results) 描述右侧结果区、产物和网页预览 | 桌面打开网页不代表手机 App 同样渲染 |
| 手机 App 文件产物 | [产物查看与分享](https://www.workbuddy.cn/docs/workbuddyapp/features/Share) 描述点击查看文件，列举 PDF、DOCX、Markdown 等 | 未明确承诺 HTML 交互渲染，也未证明所有图片能直接内联 |
| 手机多轮交流 | [任务执行与对话](https://www.workbuddy.cn/docs/workbuddyapp/features/Task-Execution) 支持同一任务持续追问与保留上下文 | 用户图片输入能力不等于助手图片输出能力 |
| 手机执行环境 | [App 简介](https://www.workbuddy.cn/docs/workbuddyapp/) 区分云端工作与连接电脑 | 桌面资源路径不可默认在云端沙箱可读；需独立核实安装和可用资源 |
| WorkBuddy MCP 应用界面 | [任务对话](https://www.workbuddy.cn/docs/workbuddy/Conversation#使用-mcp-应用界面) 明确桌面任务可在对话或右侧展示应用界面 | 只对提供界面的 MCP 应用成立；普通 HTML 不自动获得回传能力；没有手机承诺 |
| 标准 MCP Apps | [腾讯官方接入指南](https://www.workbuddy.cn/docs/cli/mcp-apps) 描述 `ui://` 资源、`text/html;profile=mcp-app`、`_meta.ui.resourceUri` 与消息回传 | 文档主要面向 CodeBuddy Web UI／IDE 场景，不能直接当 WorkBuddy App 适配证据；会增加自建 MCP 应用与连接配置 |
| Skill 安装包容量 | [技能上传说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market) | 所查公开说明未明确图片张数、ZIP 大小或文件数上限；不能宣布无限制 |

标准 MCP Apps 文档中的 `app.sendMessage` 与竞品使用的 `sendPrompt` 是不同接入机制，不能互相代换。按钮可点击、网页状态改变、消息进入主对话、助手接住选择，是四个独立检查点。

## 参赛作品源码对照

在此前 103 项 README 初筛基础上，本轮重新读取 7 个项目 14 个文件；SHA 和公开来源保存在本地 `work/research/workbuddy-interaction-20261024/sources.json`。这些是源码／作者记录核查，没有在手机 App 逐项安装复现。

| 作品 | 实际做法 | 可借鉴与限制 |
| --- | --- | --- |
| [麦门认证机](https://github.com/chuiziyao/maimen-certification/blob/main/SKILL.md) | Pillow 生成 PNG，Skill 要求 `present_files` 展示 | 优先测试这条正式图片产物路径；代码能生成 PNG 不等于手机内联成功；原脚本带作者 Windows 路径，不能照搬 |
| [麦麦塔罗牌](https://github.com/likangkangkang/mcd-tarot/blob/main/SKILL.md) | SVG 输出到 stdout，指令要求对话内展示，图文分开发 | 可参考紧凑单图与后续对话；没有本轮手机证据，插画 SVG 路径也不能证明成品照片能同样加载 |
| [麦惠生活](https://github.com/cc844673379-lgtm/mcd-hui-life/blob/main/references/visual-output.md) | `typeof sendPrompt === 'function'` 时回传，否则显示手动回复文字 | [作者日志](https://github.com/cc844673379-lgtm/mcd-hui-life/blob/main/workbuddy.md) 自述点击回传通过，但完整模板→内联渲染仍未复现；不是独立手机验收 |
| [麦门隐藏菜单研究所](https://github.com/wangxs1995/mcd-secret-menu-lab/blob/main/SKILL.md) | 聊天用 Markdown 配方，再附 HTML／PNG 卡片 | 明确承认文件不会自动显示；需区分配方信息卡与真实成品照片图库 |
| [麦门隐藏菜单实验室](https://github.com/Reak-Z/mcd-secret-menu-lab) | 主 Skill 为文本配方卡，另有 Pillow 图片卡和独立在线画廊 | 社交配方海报不是聊天内选图回传；手机友好网页不等于 WorkBuddy App 原生支持 |
| [麦麦出场图鉴](https://github.com/ddouworld/mcd-menu-stage/blob/main/SKILL.md) | 自包含 HTML，嵌入本地图、导出 PNG；调整需回到客户端 | 已明确页面不能自行发新消息，不能解决全部连续交互问题 |
| [McLottery Alchemist](https://github.com/Bryce-border/McLottery-Alchemist/blob/main/skills/mclottery-alchemist/references/agent-ui-integration.md) | 自定义 `postMessage` 桥接示例 | 文档明确宿主需实现 UI Bridge，演示不直接接真实 MCP；不能作为平台默认能力证据 |

## 过去两轮图片测试需要分开记录

- 成功轮：Skill 包内 19 张 WebP 内容内嵌进 HTML；安装文件完整，桌面 WorkBuddy 实际显示照片。宿主本地预览地址 `127.0.0.1` 不是远程图片来源；来源链接只做归因。
- 外链轮：直接要求聊天正文显示一张外部图片，实际未看到照片，且来源网络可达性也有异常。不能归因成 WorkBuddy 完全不支持外链。
- 包内单图直接进聊天正文：未完成验收。HTML 内嵌图片成功不等于这个检查通过。

## 产品交互候选与验证顺序

1. 随机单张真实照片 + 稳定 ID + 一句描述；用户可说「就这个／换一个」。
2. 类别探索优先四格图或 3～4 张图；图面标可见编号，脚本保存当批编号到稳定 ID 的映射。
3. 选中才展开来源和配方证据；只有明确准备点单才查门店和实时价格。
4. 内联可点击卡片作为增强候选。先测纯文本回传，再测图片来源限制与安装后的支持，不把外观演示当完成。
5. 标准 MCP Apps 作为后续增强研究；先确认 WorkBuddy 目标版本和手机实际支持，避免两天版本被额外服务部署阻塞。

## 资料保存

- 官方文档快照、源码、初筛记录都在 `work/research/`，该目录不公开提交。
- 此次公共检索采用 Agent Reach 的 GitHub CLI、Exa 与 Jina；Exa 达到免费限额后，官方网页通过公开读取工具交叉核对，没有登录平台路由切换。
- 历史文档会变；未来实现时重新核对目标 WorkBuddy 版本及实际工具 Schema。


## 2026-10-25 用户安装包反馈：PNG已交付，正文仍无图片

WorkBuddy AI5.8.4、Deepseek-V4.1-Flash，任务“Find hidden fries menu hacks”，用户输入“我想看薯条相关的隐藏吃法”。本轮真实present_files传入安装包内U08/U21/U23三个加工PNG，返回completed、Successfully presented 3 file(s)，previewed=[]。最终回复没有Markdown图片引用。UI正文为纯文字，底部View all artifacts (3)，右侧列表有三个PNG。结论仅是图片产物登记成功，没有正文直接出图；不能再把present_files称为已验证的正文图片展示。

需要独立验证正文图片引用/宿主可接受路径与真正可见结果；不凭文件存在、工具success或产物数量声称成功。该证据未证明平台全局不支持内联图片，也不证明模型不支持。用户在同一会话继续操作后已停止UI点击，没有发测试消息、改变模型或修改安装副本。脱敏证据work/validation/workbuddy-inline-image-20261025/diagnosis.json。


## 2026-10-25 WorkBuddy桌面正文图片：地址协议核验

用户授权独立测试并暂停操作后，在WorkBuddy AI 5.8.4 / Deepseek-V4.1-Flash新任务对同一加工PNG做对照。裸绝对路径与任务内相对路径只显示替代文本，file://形式保留为字面Markdown；local-file://local/编码路径与local-file:///编码绝对路径均显示完整图片。只读检查本地渲染代码确认其正文图片组件支持local-file协议，未修改宿主程序或安全设置。

因此统一交付使用脚本按实际路径生成的 `![编号 · 名称](local-file:///URL编码的绝对路径)`。无需启动localhost服务、上传图片、原图或额外MCP；普通推荐不主动调用present_files。所有工具调用完成后，最终回复仍保留图片语法，避免先在过程中出图、最后只留下文字。随机/餐品/优惠/补充灵感/编号卡/选号/当前清单共用image_delivery.py。

安装包按真源重新构建为实体目录，替换前已备份；本地冻结包在work/local-bundles/png-inline-v1-20261025/。新工作区真实薯条推荐已显示U08/U21/U23；重新读取收紧后的规则后，随机与换一批分别显示U03/U10，最后答复含2张图片且未再调用present_files。证据在work/validation/workbuddy-inline-image-20261025/，后续选号与优惠入口结果见同目录验收报告。

证据只覆盖本机macOS桌面版本与上述模型；手机App、云端会话、Windows及其他模型尚未验收，不能据此保证所有宿主版本。

补充验收已完成：固定选11号并展示清单，最后回复含U11正文图片；离线by-coupon结构化商品测试券与仅标题测试券分别显示主要推荐U11和补充灵感U08，最后回复含两图。对应截图与只含公开输出的脱敏日志已存上述验收目录。
