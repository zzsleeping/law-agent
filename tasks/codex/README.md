# 交给 Codex 的资料收集任务

这里的每个任务书都可以单独交给 Codex 执行。

| 任务书 | 产出 | 用途 |
| --- | --- | --- |
| [01-decisions.md](01-decisions.md) | `collected/decisions/*.json` | 真实商标数据、冻结测试集、典型案例库 |
| [02-goods-classes.md](02-goods-classes.md) | `collected/goods/goods_items_full.xlsx` | 补全第 29、30、32、43 类商品项，减少“商品项未映射 → 待核实” |
| [03-glyph-data.md](03-glyph-data.md) | `collected/glyph/` | 选定汉字部件拆分数据，用来自动计算形近字，替代人工字表 |
| [04-more-decisions.md](04-more-decisions.md) | `collected/decisions/*.json`（第二批） | 扩充文书，补难区分的反例（已完成） |
| [05-pattern-cases.md](05-pattern-cases.md) | `collected/decisions/*.json`（第三批） | 按比对情形补“不近似”判例，供参考判例检索和判定评测 |

## 通用规则（每个任务都适用，任务书里不再重复）

1. **只写 `collected/` 目录**。不改 `app/`、`data/`、`tests/` 等任何现有文件；导入正式库由我们自己做。
2. **不编造**。每条记录都要能追溯到具体来源（网址或文件、页码、获取日期）。查不到的字段填 `null`，并在交付说明里写明原因；不要根据常识或推测补全。
3. **原样记录**。商标文字、商品名称、编号按来源原文照录，不改写、不繁简转换；来源本身明显有误时照录，在 `notes` 里说明。
4. **遇到登录、验证码、付费墙或访问限制就停下**，在交付说明里报告卡在哪里，不要绕过。遵守网站的 robots 和使用条款，请求之间留间隔，不做大批量抓取。
5. **个人信息**：权利人或申请人是自然人时，`owner` 只写“自然人”，不记录姓名、地址、证件号等。
6. **交付前自检**：运行
   ```bash
   python scripts/validate_collected.py
   ```
   没有报错再交付。
7. **交付说明**：在任务产出目录下写一份 `REPORT.md`，包括：用了哪些来源和检索方式、收了多少条、跳过了哪些及原因、哪些字段不确定、遇到的阻碍。

## 我们这边收到后要做的

1. 运行 `scripts/validate_collected.py`，再随机抽 5 条对照原始来源核对。
2. 通过后由我们写导入脚本放进 `data/`，重新建库。
3. 决定书中的商标对按 50% / 50% 分成调参集和冻结测试集；冻结测试集分好后技术侧不再看具体内容。
