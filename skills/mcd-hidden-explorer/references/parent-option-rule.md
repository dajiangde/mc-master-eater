# 父商品 + 选项编码通用规则

图库里的编码、券里的编码、旧菜单记录里的编码，**都不等于可以直接下单的商品编码**。麦当劳中国菜单里同一串数字可能扮演三种角色，只有第一种能单独当 `productCode`：

| 角色 | 判定方法 | 能否单独作为 `productCode` |
|:--|:--|:--|
| 在售单品 | `query-meal-detail` 返回 `rounds` 为空 | 可以 |
| 父商品 | `rounds` 非空，本身可下单 | 可以，但必须带 `roundList` |
| 选项编码 | 出现在 `rounds[].choices[].code` | **不可以** |

判定只看接口返回，不看名字像不像单品、也不看它有没有独立价格。

## 已核实案例

2026-10-25，门店 `1410102`（龙岩莲南路，到店自取）：

```
query-meal-detail 9900008754 → 经典麦旋风
rounds[0] = { id:1, name:"选择麦旋风", minQuantity:1, maxQuantity:1,
              choices:[ {code:"1217", name:"奥利奥麦旋风", isDefault:1, quantity:1},
                        {code:"4900", name:"草莓麦旋风", isDefault:0, quantity:0} ] }
```

`1217` 是选项，不是商品。资料库与旧菜单把它记成 `奥利奥麦旋风` 的商品编码，直接当 `productCode` 传会失败。

正确写法：

```json
{"productCode": "9900008754", "quantity": 1,
 "roundList": [{"round": "1", "comboItemList": [{"code": "1217", "quantity": 1}]}]}
```

错误写法与实际返回：

```json
{"productCode": "1217", "quantity": 1}
```

> `600012 促销规则不支持该商品`

对照：`4437` 小杯玉米杯 `rounds` 为空，直接传 `{"productCode":"4437","quantity":1}` 正常核价 ¥13.50。

### 60006 不一定是售罄

同一天同一门店，买 2 份菠萝派：

```json
{"productCode": "9900008752", "quantity": 2,
 "roundList": [{"round": "1", "comboItemList": [{"code": "4105", "quantity": 2}]}]}
```

> `60006 商品已售罄或不可售，换一个商品或检查orderType/beType`

把子项数量改回 1 立刻成功，¥17.00：

```json
{"productCode": "9900008752", "quantity": 2,
 "roundList": [{"round": "1", "comboItemList": [{"code": "4105", "quantity": 1}]}]}
```

`60006` 的文案只说"售罄"，但真正原因常是**子项数量乘了父商品份数**。遇到 `60006` 先按这个顺序排查，不要立刻换商品：

1. 子项 `quantity` 是不是写成了父商品份数？
2. 选项编码是不是当了 `productCode`？
3. 必选轮次是不是漏了？
4. 以上都不是，才考虑门店真的售罄。

## 传参规则

1. **父商品编码**进 `productCode`，选项编码只进 `roundList[].comboItemList[].code`。
2. `roundList[].round` 用该轮次的 `id`（转成字符串）；缺失时用 1 起的序号。
3. **必选组**（`minQuantity >= 1`）必须出现，不能省略，也不能当成"可选"。`maxQuantity=1, minQuantity=1` 的口味组就是典型必选组。
4. **可选组**（`minQuantity = 0`）只在用户明确选了才写入 `roundList`；没选就整轮不出现。
5. 每轮已选项数要落在 `[minQuantity, max(1, maxQuantity)]` 内；`maxQuantity = -1` 表示不限。
6. 选项数量取 `choices[].quantity`，为 0 时按 1 计（用户选中即至少 1 份）。
7. **`comboItemList[].quantity` 按每份父商品记 1，不乘父商品份数。** 买 2 份派就写父商品 `quantity: 2`、子项 `quantity: 1`；把子项也写成 2 会返回 `60006`。
8. 同一父商品下所有必选轮次都要给齐；只给一部分会被判为配置不完整。
9. 价格只认 `calculate-price` 返回的 `price`（单位分）；父商品详情里的价格只是展示价。

## 落到代码

`scripts/meal_config.py` 把上述规则做成纯函数，不做网络调用、不算价：

```bash
# 看编码角色：sellable / parent，以及每个轮次的必选性
python3 scripts/meal_config.py roles --detail detail.json --code 1217

# 生成 calculate-price 的商品项（默认取默认选项）
python3 scripts/meal_config.py item --detail detail.json --quantity 1

# 指定口味
python3 scripts/meal_config.py item --detail detail.json --choose 4900

# 直接把购买清单转成 calculate-price 的 items（子项数量固定按 1 记）
python3 scripts/basket.py price-items --plan plan.json
```

Python 调用：

```python
from meal_config import describe, find_choice, build_item, MealConfigError

describe(detail)          # -> {"role": "parent", "rounds": [...]}
find_choice(detail, "1217")  # -> {"parent_code": "9900008754", "round": "1", ...}
build_item(detail, 1)     # -> 可直接放进 calculate-price 的 items 项
```

以下情况直接抛 `MealConfigError`，不生成请求：

- 选项编码不属于该商品（避免悄悄回落到默认口味）；
- 轮次标签不存在；
- 必选组没有默认项、用户也没指定；
- 已选项数超出 `maxQuantity`；
- 数量小于 1。

`600012` 的解释统一走 `explain_failure()`，只给方向、不猜结论：可能是选项编码当了商品编码，也可能是券与商品不匹配，两者都要分别核实。

## 适用面

同一形状还出现在：

- **套餐**：多轮次，主件 + 配菜 + 饮料，每轮都可能必选；
- **麦旋风 / 新地口味**：口味组必选，差价 `diffPrice` 可能为 `+ ¥0` 或加价；
- **派的口味**、**咖啡的奶/糖**：多为可选组；
- **券的适用商品**：券返回的 `productCode` 若在 `query-meals` 里查不到，先怀疑它是父商品下的选项或套餐编码，不要直接拿去核价。

## 检查清单

下单/核价前逐条过：

1. `query-meals` 里有这个编码吗？没有就换编码，不要硬传。
2. `query-meal-detail` 的 `rounds` 是空还是非空？
3. 非空时，每个 `minQuantity >= 1` 的轮次都给了值吗？
4. 给的选项编码都在该轮 `choices` 里吗？
5. 券的适用商品编码与父商品编码一致吗？不一致就是券不适用，不是"试试看"。
