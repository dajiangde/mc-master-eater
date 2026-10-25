![麦门老吃家：红黄积木工作坊，隐藏吃法，认真研究。](assets/readme/maimen-brick-hero.png)

# 🍔 麦门老吃家 · Maimen Master Eater

> **全网民间隐藏吃法严谨考据 · 麦当劳官方 MCP 实时拆解核价工作台**
>
> 民间吃法不是官方隐藏商品，它是一代代麦门食客的智慧结晶。不凭空编造配方，不盲目推荐冷门。说出你的想吃灵感，AI 帮你考据溯源、拆解单品、门店实时核价、算清真热量。

[![GitHub Stars](https://img.shields.io/github/stars/dajiangde/mc-master-eater?style=social)](https://github.com/dajiangde/mc-master-eater)
[![MCP McDonald's China](https://img.shields.io/badge/MCP-McDonald's%20China%20Certified-DA291C?logo=mcdonalds&logoColor=white)](https://github.com/M-China/mcd-mcp-server)
[![WorkBuddy Native](https://img.shields.io/badge/Platform-WorkBuddy%205.8+-2F6BFF?logo=target)](https://www.workbuddy.cn/)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests Passing](https://img.shields.io/badge/Tests-326%20Passed-brightgreen)](tests/)
[![Data Integrity](https://img.shields.io/badge/Hallucination-0%25%20(Strict%20Audit)-orange)](#-老吃家的四维考据铁律)
[![Catalog](https://img.shields.io/badge/Hacks%20Catalog-22%20Active%20Cards-red)](#-22-款麦门老吃家精选图鉴)

> 🏆 **本项目正在参加 [2026 麦当劳程序员创意开发大赛](https://github.com/M-China/mcd-developer-innovation-challenge)**<br>
> 喜欢老吃家的严谨与美味？欢迎在右上角为我们点上一颗 **⭐ Star** 支持麦门！

---

## 🏆 参赛信息

| 项目 | 信息 |
| --- | --- |
| 参赛作品 | 麦门老吃家 · `mc-master-eater` |
| 比赛 | [麦当劳程序员创意开发大赛](https://github.com/M-China/mcd-developer-innovation-challenge) |
| 报名记录 | [官方报名 Issue #1269](https://github.com/M-China/mcd-developer-innovation-challenge/issues/1269) |
| 官方回复 | [2026-10-24 回复“已成功参赛”](https://github.com/M-China/mcd-developer-innovation-challenge/issues/1269#issuecomment-6383930402)；后续资格与排名按活动规则核验 |
| 参赛声明 | [官方原文，未修改](CONTEST_DECLARATION.md) |
| MCP 接入 | [集成说明](MCP_INTEGRATION.md) · [脱敏配置示例](mcp-config.example.json) |
| WorkBuddy 记录 | [开发摘要](workbuddy.md)，不是完整对话导出，不据此承诺专项奖励资格 |

报名记录最初使用旧名称“麦麦隐藏吃法探索器”；现项目与 Skill 已统一为“麦门老吃家 / mc-master-eater”。官方要求参赛仓库持续公开可访问，报名回复不替代后续资格审核。

---

## 🎬 交互演示：从挑选灵感到清单核价

不用先想好餐品名。一句“随便推荐几个”，从挑灵感开始。

![麦门老吃家使用演示：浏览编号卡片，选择11号，展开做法，查看购买清单与核价样例。](assets/readme/maimen-usage.gif)

*26 秒循环演示。画面为积木风交互示意，采用图形卡片；完整图片体验使用隐藏吃法照片卡片。演示中的价格采用 2026-10-25 龙岩莲南路店已有核验记录。*

---

## 💡 为什么需要「麦门老吃家」？

你一定在社交平台刷到过这些让人垂涎的**神仙吃法**：<br>
*“麦香鱼夹菠萝派！”、“玉米杯拌奥利奥麦旋风！”、“鸡翅去骨塞薯条！”……*

但每当你兴冲冲走进门店、站在点餐机或手机 App 前，现实总会无情打脸：
- 🤦‍♂️ **叫不出名字**：柜台根本没有这件商品，全靠自己硬拼；
- 🧩 **原料摸不透**：到底要买几包酱？哪个是固定单品，哪个可以选口味（菠萝派还是香芋派）？
- ⏰ **时段不对路**：大中午兴冲冲去点薯饼夹冰淇淋，才发现薯饼是早餐限定；
- 💸 **满减反被割**：用了看似立减 20 元的优惠券，结果整单反而比单点多花了 4 毛钱，热量还爆表；
- 🤖 **AI 乱幻觉**：普通问答模型常常胡编乱造“麦当劳已推出抹茶冰淇淋”、“草莓新地全国供应”……

### **老吃家，就是为你把关的那个人。**

「麦门老吃家」拒绝做天马行空的“赛博做菜发生器”。我们建立了一套**可考据、能落地、真实核价、带热量验证**的隐藏吃法专家系统。

---

## ✨ 核心特性：老吃家的自我修养

| 场景模式 | 你只需说 | 老吃家为你做 |
| :--- | :--- | :--- |
| 🎲 **随便看看** | *“不知道吃啥，随便推荐几个”* | 跨品类均衡轮换，优先推荐本轮未看过的灵感，绝不机械重复 |
| 🍟 **精准寻味** | *“想吃薯条相关的吃法”* | 双层商品族识别，精准命中；**薯条绝不智障推荐薯饼** |
| 🎫 **持券寻珍** | *“我卡包里有这几张券，能做啥？”* | 深度匹配卡券商品，区分【核心推荐】与【补充灵感】，绝不强行凑单 |
| 🔄 **口味自选** | *“我不爱吃菠萝派，换香芋派”* | 智能拆解父商品选项组，一句话秒换，清单与价格即时联动 |
| 💰 **官方验价** | *“帮我看看这家店做下来多少钱”* | 真实调用麦当劳中国官方 MCP，查当前门店、实时算价、杜绝估算 |
| 🥗 **热量透视** | *“吃了会不会负罪感拉满？”* | 官方营养表实时汇总，缺项严谨标明“已知部分热量”，拒当糊涂账 |

---

## 🎨 22 款「麦门老吃家」精选图鉴

老吃家不以“数量虚标”取胜。全量收录的 **22 款活动吃法（U01~U23）** 均经过全网高赞溯源与食材可操作性审查，并配以统一制作的 **1080×1440 麦门美学卡片**：

```text
┌──────────────────────────────────────────────────┐
│  🍔 麦门老吃家   U11                319 kcal     │
│  ──────────────────────────────────────────────  │
│                                                  │
│          [ 1080×1440 高清实拍成品展示 ]           │
│                                                  │
│  ──────────────────────────────────────────────  │
│  玉米奥利奥麦旋风                                │
│  所需餐品：小杯玉米杯 + 经典麦旋风 (奥利奥)      │
│  简明步骤：玉米粒倒入麦旋风，搅拌后舀着吃        │
│                                                  │
│                   【 麦门老吃家 · 灵感收录 】     │
└──────────────────────────────────────────────────┘
```

- 🏷️ **唯一固定编号**：编号跨轮次恒定（11号对应 U11），支持多选、多轮挑选、取消与替换；
- 🛡️ **停用编号永久留档**：12号停用保留、绝不前移挪用，真实记录民间吃法流变；
- 🔖 **老吃家专属印章**：醒目的红黄配色与复古灵感方印，自带官方计算的热量角标。

---

## 📊 官方 MCP 真实核价跑分（严谨实测）

> 💡 **拒绝假装连接**：以下数据均来自麦当劳中国官方 MCP 真实接口响应（实测门店：龙岩莲南路得来速餐厅 1410102 / 渠道：到店自取）：

| 吃法编号与名称 | 所需真实商品拆解 | 官方 MCP 核价结果 | 官方营养热量 | 避坑与用券实测结论 |
| :--- | :--- | :---: | :---: | :--- |
| **U11 玉米奥利奥麦旋风** | 小杯玉米杯 `4437` + 经典麦旋风 `9900008754` (选 `1217`) | **¥28.50** | 319 千卡 | 攻克奥利奥口味非单品痛点；卡包三张券均不适用，**如实报告省 ¥0，绝不强行忽悠** |
| **U06 派拌麦旋风 (默认)** | 派 (选菠萝派 `9900008750`) + 经典麦旋风 (选奥利奥 `1217`) | **¥23.50** | 487 千卡 | 双必选口味组，无缝支持改香芋派 (527 千卡)，价格保持 ¥23.50 |
| **U18 麦香鱼菠萝派** | 麦香鱼 `1400` + 派 (选菠萝派) | **¥31.00** | 546 千卡 | 网红奇妙咸甜搭配，整单直接官方试算 |
| **U05 三肉叠堡 (三合一)** | 双吉 `1430` + 麦辣鸡腿堡 `1440` + 麦香鸡 `1450` | 单点 **¥59.50**<br>券后 **¥59.90** | 1127 千卡 | **防套路审计**：用鸡腿堡三件套券反而贵 ¥0.40（但多饮料薯条），如实向用户提示差价真相！ |
| **U23 鸡翅薯条夹心** | 麦辣鸡翅2块 + 中薯条 | **¥27.00** | 536 千卡 | 最新实拍考据入库，拔骨插薯条的神仙体验 |

> 📌 **核心避坑发现**：**“奥利奥麦旋风”在门店是“经典麦旋风”下面的口味选项。** 配置时必须构造“父商品＋口味选项”（`roundList`），不能把口味编码当成独立商品。改口味后也要重核清单、价格和热量。

---

## 🔬 老吃家的四维考据铁律

为了防止 AI 幻觉污染食客体验，本项目严格恪守工程准则：

1. **零虚构事实**：只有封面的民间图文一律标明 `cover_only`，缺失步骤保留 `null`，绝不脑补；
2. **时令与地域锁定**：普通圆筒、抹茶雪冰等非全时段或缺货原料明示替代方案，避免点不到尴尬；
3. **复合商品算法**：首创父商品 + `roundList` 递归选品机制，精准解决麦当劳“选项不能当单品卖”的底层逻辑；
4. **安全与隐私底线**：领券与下单必须经用户显式确认；零自动代付，无任何隐私信息上报。

---

## 🛠️ 硬核工程架构

项目具备完备的工业级工程测试与状态机支撑：

```
skills/mcd-hidden-explorer/
├── references/             # 规范与配置
│   ├── numbered-selection.md    # 固定编号与商品映射规范
│   ├── parent-option-rule.md    # 父商品+roundList选项编码规则
│   └── product-aliases.json     # 商品族与排他词典
├── scripts/                # 核心驱动引擎
│   ├── discover.py              # 三大入口调度器 (随机/餐品/卡券)
│   ├── session_state.py         # 跨轮次连续会话状态机
│   ├── numbered_catalog.py      # SQLite 编号管理与卡片数据源
│   ├── meal_config.py           # 官方 MCP 父商品选项配置器
│   └── basket.py                # 购物清单规划、热量聚合与比价器
└── tests/                  # 单元测试集 (326 Tests Passing)
```

- **326 项单元测试全绿**：覆盖发现逻辑、会话状态机、边界排他、父商品选项匹配、离线热量计算、选号核券与安全拦截；
- **纯标准库打造**：Python 3.9+ 零冗余第三方 Python 依赖，开箱即用，极速响应。

---

## 🚀 快速上手

**说明：当前公开仓库提供 Skill 核心代码与积木风演示素材；22 张高清实拍照片卡片及对应研究编号库属于受控素材，不随基础仓库公开分发。直接克隆只获得核心代码；正式资料库当前为空，完整探索需要含图资料包或自行完成资料收录。**

### 1. 作为 WorkBuddy Skill 使用（推荐）

新增吃法的含图版本请使用完整构建的 ZIP：发布后从 [Releases](https://github.com/dajiangde/mc-master-eater/releases) 下载 `mc-master-eater.zip`，开发候选从对应 Actions 的 Artifacts 下载。包内包含吃法、编号库、加工卡和缩图，通过 WorkBuddy 安装入口导入或更新；旧安装不会随仓库更新自动刷新。以下克隆方式是基础源码安装，不能替代含图版本。

1. 克隆本仓库或下载发布包：
   ```bash
   git clone https://github.com/dajiangde/mc-master-eater.git
   cd mc-master-eater
   ```
2. Skill 标识与仓库统一为 `mc-master-eater`（中文名：麦门老吃家）。源码暂保留在 `skills/mcd-hidden-explorer`，安装时使用新名称：
   ```bash
   mkdir -p ~/.workbuddy-ai/skills
   # 如已有旧版，请先备份，避免混入不同版本
   cp -R skills/mcd-hidden-explorer ~/.workbuddy-ai/skills/mc-master-eater
   ```
3. 在 WorkBuddy 中配置并启用 [麦当劳中国 MCP 连接器](MCP_INTEGRATION.md)；
4. 直接对 AI 说：
   > *“麦门老吃家，随便给我推荐几个隐藏吃法！”*<br>
   > *“我想看薯条能怎么吃？”*<br>
   > *“选 11 号，先说说需要点什么。”*

目前的图片正文展示验收覆盖 macOS 上的 WorkBuddy AI 5.8.4 / Deepseek-V4.1-Flash；手机、云端与其他系统仍需分别验证。

### 2. 开发者本地调试与运行
```bash
# 1. 运行 326 项单元测试
python3 -B -m unittest discover -s tests -q

# 以下推荐示例需要完整含图包或显式指定 --database
# 2. 体验随机推荐
python3 skills/mcd-hidden-explorer/scripts/discover.py random --limit 3

# 3. 按餐品查找
python3 skills/mcd-hidden-explorer/scripts/discover.py by-product "麦香鱼"

# 4. 查询 11 号吃法详情与配方
python3 skills/mcd-hidden-explorer/scripts/numbered_catalog.py select 11

# 5. 校验公开资料库格式
python3 skills/mcd-hidden-explorer/scripts/explore.py validate
```

---

## 📖 项目文档与开发规范

- [投稿、自己添加与完整安装包自动化](docs/CONTENT_PIPELINE.md)：两种入口共用收录器，资料与图片一起构建；待审条目不进入推荐池。
- [Skill 入口定义](skills/mcd-hidden-explorer/SKILL.md)
- [演示素材说明](assets/readme/SOURCES.md)
- [项目需求与讨论决策](docs/PROJECT_CONTEXT.md)
- [当前进展与验收状态](docs/STATUS.md)
- [开发规范与验收标准](docs/DEVELOPMENT_GUIDE.md)
- [WorkBuddy 交互调研报告](docs/INTERACTION_RESEARCH.md)
- [参赛作品声明](CONTEST_DECLARATION.md)
- [MCP 集成说明](MCP_INTEGRATION.md)
- [开发过程记录](workbuddy.md)

---

## 📜 比赛与免责声明

- 本项目为独立开发的非官方开源参赛作品，参加 **2026 麦当劳程序员创意开发大赛**，无麦当劳（中国）官方商业背书；
- “麦当劳”、“麦门”及相关餐品商标所有权归原权利人所有；
- 本项目提供的配方来自民间食客经验整理，营养数据计算参考官方公开营养表，不构成专业医疗与营养建议；实际餐品供应与最终结算价格以麦当劳官方渠道实时结果为准；禁止提交凭据、个人信息或未获授权素材。

<div align="center">

**🍔 麦门永存 · 愿每一位老吃家都能吃到属于自己的隐藏美味 🍟**

</div>
