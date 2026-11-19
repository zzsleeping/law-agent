# 商标评审文书第三批采集报告

2026 年 11 月 19 日新增 **34 份文书、35 对商标**，其中 **11 对**获认定标识不近似。按文书编号和申请号与前两批 152 份交叉查重。
收录 19 份驳回复审决定书、14 份无效宣告请求裁定书、1 份不予注册复审决定书。第 29、30、32、43 类范围内 12 份，涉及其他类别 22 份。涉及其他类别的引证已逐条标注。按项目脚本归类后，同一份文书在任一情形最多贡献三对，每个同名引证仅保留一个注册号。

## 来源和检索

共使用 168 条不同检索式，读取 481 个评审文书页面片段或全文，另核对 2 个公开裁判文书页面。仅保留可核实完整正文、编号和审理机关认定的案例。
评审正文来自标库网保留官方文书编号的转载。中国商标网评审入口在采集环境无法读取。公开判决只核对可直接访问的全文存档，其中一个站点返回 403，该页面未收录。类别和部分日期通过文书自带的商标详情或官方商标开放基本信息按号核对。
[中国商标网评审入口](https://pub.sbj.cnipa.gov.cn/toas-pub-prod/portalui-pub-prod/trademarkAssessment)

申请商品明细缺失 12 份，引证商品明细缺失 34 件。这些字段留空，并在对应 JSON 中注明。类似群仅在原文能对应到具体商品时填写。

用「完整包含」「显著性较弱」「整体含义」「尚可区分」「虽均含」「共有」「未构成近似商标」结合四类及商品词检索包含和共用部分。用「字序不同」「文字排列顺序不同」「叠字」「叠词」「重叠构成」「仅一字不同」「一字之差」「呼叫相同」「读音相同」「字形相近」「部件相近」检索稀缺情形，另查候选品牌、同名及形近字组合。本批主要检索式附在文末。

## 跳过原因

| 初筛和复核原因 | 数量 |
| --- | ---: |
| 尚无目标情形配额所需的认定 | 205 |
| 纯外文或图形 | 95 |
| 标题或中文文字不符合 | 85 |
| 未定位审理认定 | 21 |
| 缺编号和可核实中文引证 | 18 |
| 缺可核对引证编号 | 9 |
| 缺官方文书编号 | 7 |
| 检索命中但无法读取页面 | 5 |
| 页面缺正文 | 4 |
| 缺当事人段 | 3 |
| 申请类别范围待复核 | 1 |
| 正文争议商标与页首不一致 | 1 |

## 自检和配额差距

项目校验脚本的结果为 **0 错误、206 个警告**。警告包含前两批及第三批的缺项和提示。比对情形使用交付时的项目脚本及 --since 2026-11-19 统计。

```text
文书 34 份，商标对 35 对（retrieved_at ≥ 2026-11-19）
比对情形               近似 对数/文书数        不近似 对数/文书数
完全相同                 0/0              0/0     
完整包含                 0/0              5/5     
仅一字不同                0/0              3/3     
字序颠倒                13/13             0/0     
叠字                   1/1              0/0     
读音相同/相近             10/10             2/2     
字形相近                 0/0              0/0     
共用部分                 0/0              1/1     
共用字但未命中              0/0              0/0     
无文字命中                0/0              0/0
```

| 比对情形 | 官方认定 | 新增对数 | 涉及文书 | 配额 | 尚缺 |
| --- | --- | ---: | ---: | --- | --- |
| 完整包含 | 不近似 | 5 | 5 | 30 对，15 份 | 25 对，10 份 |
| 共用部分 | 不近似 | 1 | 1 | 40 对，20 份 | 39 对，19 份 |
| 仅一字不同 | 不近似 | 3 | 3 | 10 对 | 7 对 |
| 字序颠倒 | 近似 | 13 | 13 | 10 对 | 达标 |
| 字序颠倒 | 不近似 | 0 | 0 | 8 对 | 8 对 |
| 叠字 | 近似 | 1 | 1 | 5 对 | 4 对 |
| 叠字 | 不近似 | 0 | 0 | 5 对 | 5 对 |
| 读音相同/相近 | 近似 | 10 | 10 | 10 对 | 达标 |
| 读音相同/相近 | 不近似 | 2 | 2 | 10 对 | 8 对 |
| 字形相近 | 近似 | 0 | 0 | 10 对 | 10 对 |
| 字形相近 | 不近似 | 0 | 0 | 5 对 | 5 对 |

包含与共用部分的检索命中不少出自当事人陈述，部分官方认定只涉及商品类似或引证权利状态。字序和叠字检索中，能对应到两个实际标识的审理意见多为近似，未找到可计入对应情形的反例。单字差异和音近反例中，有些文书只写商品或服务不类似，这类结论没有记为标识不近似。原文同时讨论字形与发音的案例按脚本的首个分类统计，例如“帝怡 / 蒂怡”计入“读音相同/相近”。以上配额差距按实际收录数保留。

## 各情形的“不近似”案例

| 比对情形 | 文书编号 | 申请或争议商标 | 引证商标 | 原文认定理由 |
| --- | --- | --- | --- | --- |
| 完整包含 | [商评字[2021]第0000181653号](https://www.tmkoo.com/spw-ws!info.php?idEn=8179862558cab69c) | 鼠小小 | 小小 | 其与引证商标一至五在文字构成、呼叫、含义、整体视觉效果等方面存在一定区别 |
| 完整包含 | [商评字[2024]第0000258172号](https://www.tmkoo.com/spw-ws!info.php?idEn=5c83a1df3a4b7d7b) | 沃顿你好 | 你好 | 争议商标“沃顿你好”与引证商标“你好”文字构成存在一定差异，整体含义上形成较大区别 |
| 完整包含 | [商评字[2021]第0000240199号](https://www.tmkoo.com/spw-ws!info.php?idEn=19b6de6ac17ca4e2) | 九街淑芬 | 淑芬 | 与申请人引证商标一、二在呼叫、文字构成、含义等方面存在一定区别，未构成近似标识 |
| 完整包含 | [商评字[2018]第0000026890号](https://www.tmkoo.com/spw-ws!info.php?idEn=73d982c7b94f5636) | 小小的我Little me | 小小 | 与引证商标一、二、四在文字构成、呼叫、含义等方面均存在一定的区别，未构成近似商标 |
| 完整包含 | [商评字[2024]第0000258177号](https://www.tmkoo.com/spw-ws!info.php?idEn=9488faef7a2b7585) | 你好沃顿 | 你好 | 争议商标“你好沃顿”与引证商标“你好”文字构成存在一定差异，整体含义上形成较大区别 |
| 共用部分 | [商评字[2021]第0000240199号](https://www.tmkoo.com/spw-ws!info.php?idEn=19b6de6ac17ca4e2) | 九街淑芬 | 王淑芬串串 | 与申请人引证商标一、二在呼叫、文字构成、含义等方面存在一定区别，未构成近似标识 |
| 仅一字不同 | [商评字[2020]第0000033040号](https://www.tmkoo.com/spw-ws!info.php?idEn=4175d457b70800ed) | 百力士 | 大力士 | 但首字不同，争议商标由汉字“百力士”构成，其汉字部分“百力士”为臆造词 |
| 仅一字不同 | [商评字[2023]第0000375516号](https://www.tmkoo.com/spw-ws!info.php?idEn=0bac10fa102f8c1f) | 柏佳悦 | 柏悦 | 争议商标与引证商标一至六在文字构成、呼叫等方面尚可区分 |
| 仅一字不同 | [商评字[2025]第0000049521号](https://www.tmkoo.com/spw-ws!info.php?idEn=a89ec7c1b37a0368) | 俏蒂诗 QIAODISHI | 海蒂诗 | 在文字构成、呼叫上存在差异，整体尚可区分 |
| 字序颠倒 | 0 份 | | | |
| 叠字 | 0 份 | | | |
| 读音相同/相近 | [商评字[2018]第0000256572号](https://www.tmkoo.com/spw-ws!info.php?idEn=b83d80eed17c0fc3) | 晋山河 | 锦绣山河 | 由于争议商标与引证商标六在文字构成、呼叫等方面有所差异，未构成近似商标 |
| 读音相同/相近 | [商评字[2024]第0000333666号](https://www.tmkoo.com/spw-ws!info.php?idEn=c1273ed0abfa054c) | 吉拉多 Grandeur及图 | 吉娜朵 | 被异议商标与引证商标二、三在整体构成等方面尚可区分 |
| 字形相近 | 0 份 | | | |

## 本批检索式

```text
site:tmkoo.com/spw-ws 第29类 肉 "完整包含" "未构成近似商标"
site:tmkoo.com/spw-ws 第30类 糕点 "完整包含" "未构成近似商标"
site:tmkoo.com/spw-ws 第32类 啤酒 "完整包含" "未构成近似商标"
site:tmkoo.com/spw-ws 第43类 餐厅 "完整包含" "未构成近似商标"
site:tmkoo.com/spw-ws 第29类 牛奶 "完整包含" "整体含义" "未构成"
site:tmkoo.com/spw-ws 第30类 茶 "完整包含" "整体含义" "未构成"
site:tmkoo.com/spw-ws 第32类 饮料 "完整包含" "整体含义" "未构成"
site:tmkoo.com/spw-ws 第43类 咖啡馆 "完整包含" "整体含义" "未构成"
site:tmkoo.com/spw-ws 第29类 酸奶 "文字" "整体尚可区分"
site:tmkoo.com/spw-ws 第30类 调味品 "文字" "整体尚可区分"
site:tmkoo.com/spw-ws 第32类 果汁 "文字" "整体尚可区分"
site:tmkoo.com/spw-ws 第43类 饭店 "文字" "整体尚可区分"
site:tmkoo.com/spw-ws 第29类 "不构成近似商标" "显著性较弱" "我局认为"
site:tmkoo.com/spw-ws 第30类 "不构成近似商标" "显著性较弱" "我局认为"
site:tmkoo.com/spw-ws 第32类 "不构成近似商标" "显著性较弱" "我局认为"
site:tmkoo.com/spw-ws 第43类 "不构成近似商标" "显著性较弱" "我局认为"
site:tmkoo.com/spw-ws 第29类 "均含" "未构成近似商标"
site:tmkoo.com/spw-ws 第30类 "均含" "未构成近似商标"
site:tmkoo.com/spw-ws 第32类 "均含" "未构成近似商标"
site:tmkoo.com/spw-ws 第43类 "均含" "未构成近似商标"
site:tmkoo.com/spw-ws 第29类 "共有" "整体视觉" "尚可区分"
site:tmkoo.com/spw-ws 第30类 "共有" "整体视觉" "尚可区分"
site:tmkoo.com/spw-ws 第32类 "共有" "整体视觉" "尚可区分"
site:tmkoo.com/spw-ws 第43类 "共有" "整体视觉" "尚可区分"
site:tmkoo.com/spw-ws 牛奶 肉制品 "整体含义不同" "未构成" "引证商标"
site:tmkoo.com/spw-ws 茶 糕点 "整体含义不同" "未构成" "引证商标"
site:tmkoo.com/spw-ws 果汁 水饮料 "整体含义不同" "未构成" "引证商标"
site:tmkoo.com/spw-ws 茶馆 酒店 "整体含义不同" "未构成" "引证商标"
site:tmkoo.com/spw-ws 第29类 "文字构成" "含义" "可以区分" "未构成"
site:tmkoo.com/spw-ws 第30类 "文字构成" "含义" "可以区分" "未构成"
site:tmkoo.com/spw-ws 第32类 "文字构成" "含义" "可以区分" "未构成"
site:tmkoo.com/spw-ws 第43类 "文字构成" "含义" "可以区分" "未构成"
site:tmkoo.com/spw-ws 乳制品 "含有" "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 咖啡 "含有" "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 矿泉水 "含有" "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 餐饮服务 "含有" "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 我局认为 "文字顺序" "未构成近似商标"
site:tmkoo.com/spw-ws 经复审认为 "文字顺序" "未构成近似商标"
site:tmkoo.com/spw-ws 争议商标 "文字顺序" "未构成近似商标"
site:tmkoo.com/spw-ws 引证商标 "文字顺序" "未构成近似商标"
site:tmkoo.com/spw-ws 文字构成 "排列顺序不同" "整体含义"
site:tmkoo.com/spw-ws 商评字 "排列顺序不同" "整体含义"
site:tmkoo.com/spw-ws 驳回复审 "排列顺序不同" "整体含义"
site:tmkoo.com/spw-ws 裁定书 "排列顺序不同" "整体含义"
site:tmkoo.com/spw-ws 引证商标 "字序" "近似商标"
site:tmkoo.com/spw-ws 第30类 "字序" "近似商标"
site:tmkoo.com/spw-ws 第43类 "字序" "近似商标"
site:tmkoo.com/spw-ws 复审商品 "字序" "近似商标"
site:tmkoo.com/spw-ws 近似标识 "汉字顺序" "引证商标"
site:tmkoo.com/spw-ws 未构成近似 "汉字顺序" "引证商标"
site:tmkoo.com/spw-ws 我局认为 "汉字顺序" "引证商标"
site:tmkoo.com/spw-ws 商评字 "汉字顺序" "引证商标"
site:tmkoo.com/spw-ws 叠字 "引证商标" "近似商标"
site:tmkoo.com/spw-ws 叠词 "引证商标" "近似商标"
site:tmkoo.com/spw-ws 重叠 "引证商标" "近似商标"
site:tmkoo.com/spw-ws 重复排列 "引证商标" "近似商标"
site:tmkoo.com/spw-ws 叠字 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 重复 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 叠加 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 重复文字 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 仅一字 "未构成近似商标"
site:tmkoo.com/spw-ws 仅差一字 "未构成近似商标"
site:tmkoo.com/spw-ws 仅一字之差 "未构成近似商标"
site:tmkoo.com/spw-ws 仅一字不同 "未构成近似商标"
site:tmkoo.com/spw-ws 首字不同 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 末字不同 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 中间一字 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 个别汉字 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 呼叫相同 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 读音相同 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 读音近似 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 同音 "未构成近似商标" "含义"
site:tmkoo.com/spw-ws 呼叫相同 "未构成使用" "尚可区分"
site:tmkoo.com/spw-ws 呼叫相近 "未构成使用" "尚可区分"
site:tmkoo.com/spw-ws 读音相似 "未构成使用" "尚可区分"
site:tmkoo.com/spw-ws 读音相同 "未构成使用" "尚可区分"
site:tmkoo.com/spw-ws 形近字 "引证商标" "构成近似商标"
site:tmkoo.com/spw-ws 字形近似 "引证商标" "构成近似商标"
site:tmkoo.com/spw-ws 字形相近 "引证商标" "构成近似商标"
site:tmkoo.com/spw-ws 部件相近 "引证商标" "构成近似商标"
site:tmkoo.com/spw-ws 字形相近 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 字形近似 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 笔画相似 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 形近 "未构成近似商标" "我局认为"
site:tmkoo.com/spw-ws 第29类 "我局认为" "整体构成" "未构成近似商标"
site:tmkoo.com/spw-ws 第30类 "我局认为" "整体构成" "未构成近似商标"
site:tmkoo.com/spw-ws 第32类 "我局认为" "整体构成" "未构成近似商标"
site:tmkoo.com/spw-ws 第43类 "我局认为" "整体构成" "未构成近似商标"
site:tmkoo.com/spw-ws "波波" "重叠" "近似商标"
site:tmkoo.com/spw-ws "叠字" "不近似" "引证商标"
site:tmkoo.com/spw-ws "重叠构成" "商标" "呼叫"
"星星" "星" "商评字" "近似" 商标
site:tmkoo.com/spw-ws "虽均含" "未构成" 第29类
site:tmkoo.com/spw-ws "虽均含" "未构成" 第30类
site:tmkoo.com/spw-ws "虽均含" "未构成" 第32类
site:tmkoo.com/spw-ws "虽均含" "未构成" 第43类
site:tmkoo.com/spw-ws "显著性较弱" "未构成近似商标" 第29类
site:tmkoo.com/spw-ws "显著性较弱" "未构成近似商标" 第30类
site:tmkoo.com/spw-ws "显著性较弱" "未构成近似商标" 第32类
site:tmkoo.com/spw-ws "显著性较弱" "未构成近似商标" 第43类
site:tmkoo.com/spw-ws "整体含义" "未构成近似商标" 第29类 肉制品
site:tmkoo.com/spw-ws "整体含义" "未构成近似商标" 第30类 咖啡 茶
site:tmkoo.com/spw-ws "整体含义" "未构成近似商标" 第32类 饮料
site:tmkoo.com/spw-ws "整体含义" "未构成近似商标" 第43类 餐厅
site:tmkoo.com/spw-ws "字序不同" "含义" "经复审认为"
site:tmkoo.com/spw-ws "文字顺序颠倒" "引证商标"
site:tmkoo.com/spw-ws "文字排列顺序不同" "未构成" "引证商标"
site:tmkoo.com/spw-ws "仅字序不同" "近似标识"
site:tmkoo.com/spw-ws "不同的含义" "呼叫相同" "未构成近似商标"
site:tmkoo.com/spw-ws "仅一字不同" "尚可区分"
site:tmkoo.com/spw-ws "音同" "不构成近似商标" 引证商标
site:tmkoo.com/spw-ws "读音相同" "字形" "未构成使用"
site:tmkoo.com/spw-ws "在文字构成、呼叫等方面存在一定差异" "未构成近似商标" 饮料
site:tmkoo.com/spw-ws "整体可区分" "未构成近似商标" 茶
site:tmkoo.com/spw-ws "文字构成和整体含义" "未构成使用" 餐厅
site:tmkoo.com/spw-ws "整体视觉效果存在一定区别" "未构成近似" 食品
"坤星文具" "星坤" 商评字
"亚美航空" "美亚医疗" 决定书 裁定书
"哈罗哈罗" "哈罗" 商评字 驳回复审
"美亚" "亚美" "裁定书" "不构成近似商标"
site:zh.wikisource.org "字序" "诉争商标" "注册号"
site:zh.wikisource.org "文字顺序" "本院认为" "不构成近似商标" "注册号"
site:zh.wikisource.org "重叠" "引证商标" "本院认为" 商标
site:zh.wikisource.org "一个字" "不构成近似商标" 商标 注册号
site:tmkoo.com/spw-ws "与引证商标" "区别较大" "第29类" 牛奶 肉
site:tmkoo.com/spw-ws "与引证商标" "区别较大" "第30类" 糖 米
site:tmkoo.com/spw-ws "与引证商标" "区别较大" "第32类" 啤酒
site:tmkoo.com/spw-ws "与引证商标" "区别较大" "第43类" 飯店
site:tmkoo.com/spw-ws 徐记海鲜 餐厅 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 老乡鸡 餐厅 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 海底捞 餐厅 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 霸王茶姬 茶馆 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 康师傅 方便面 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 华莱士 餐厅 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 益禾堂 茶 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 同福 蜂蜜 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 喜茶 茶饮料 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 奶茶 饮料 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 白象 方便面 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 老干妈 调味品 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 雪花 啤酒 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 青岛 啤酒 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 农夫山泉 矿泉水 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 怡宝 饮料 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 小小 食品 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 旺旺 食品 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 三只松鼠 坚果 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws 金锣 肉 "未构成近似商标" "我局"
site:tmkoo.com/spw-ws “康帅傅” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “可口可乐” “可口可楽” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “周大福” “周大褔” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “士力架” “土力架” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “大白兔” “太白兔” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “三只松鼠” “三只淞鼠” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “娃哈哈” “娃哈咹” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “王老吉” “玉老吉” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “未” “末” “字形” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “己” “已” “字形” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “末字” “形近” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “近似字” “引证商标” "近似商标" "引证商标"
site:tmkoo.com/spw-ws “成成” "重复" "近似商标"
site:tmkoo.com/spw-ws “乐乐” "重复" "近似商标"
site:tmkoo.com/spw-ws “哈罗哈罗” "重复" "近似商标"
site:tmkoo.com/spw-ws “星星” "重复" "近似商标"
site:tmkoo.com/spw-ws “甜甜” "重复" "近似商标"
site:tmkoo.com/spw-ws “旺旺” "重复" "近似商标"
site:tmkoo.com/spw-ws “哈哈” "重复" "近似商标"
site:tmkoo.com/spw-ws “发发” "重复" "近似商标"
```
