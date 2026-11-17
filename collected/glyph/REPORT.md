# 汉字部件拆分数据

获取日期为 2026-11-16。

## 候选对比

| 数据 | 维护者与 Git 快照日期（UTC） | 上游许可 | 格式 | 规范字头覆盖 | 含结构符 | 含结构符且没有问号占位 | 主要取舍 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| [CJKVI IDS](https://github.com/cjkvi/cjkvi-ids) | kawabata · [2019-02-06](https://github.com/cjkvi/cjkvi-ids/commit/86b4d16159f0079437870408f0ca186e529015db) | GNU General Public License v2 or later（GPL-2.0-or-later，依 CHISE 条款） | TSV。码点、字头、多列 IDS，可带地区后缀。 | 8,105（100.00%） | 7,952（98.11%） | 7,952（98.11%） | 单文件，规范字头全覆盖，拆分率最高。地区异体及圈号部件需要解析。 |
| [CHISE IDS](https://github.com/chise/ids) | CHISE 项目（Tomohiko Morioka 等） · [2026-03-15](https://github.com/chise/ids/commit/0b45762b5728783fc2bc58a1e3c57ba0a7c5fcfc) | GNU General Public License v2 or later（GPL-2.0-or-later） | TSV。码点、字头、IDS，部分行另有 @apparent。 | 8,105（100.00%） | 7,838（96.71%） | 7,838（96.71%） | 持续更新，规范字头全覆盖。多个文件，包含 CHISE 部件实体引用。 |
| [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) | Shaunak Kishore（skishore） · [2026-03-08](https://github.com/skishore/makemeahanzi/commit/bddc96d41bef78427ed0e034e9f7e31d71fd1b92) | GNU Lesser General Public License v3 or later（LGPL-3.0-or-later，适用于 dictionary.txt） | JSON Lines。character、decomposition、matches 等字段。 | 6,866（84.71%） | 6,832（84.29%） | 6,569（81.05%） | 有笔画与部件的对应索引。规范字覆盖较少，部分拆分含未知部件。 |

CJKVI 的许可说明将本次选中的 `ids.txt` 指向 CHISE 条款。CHISE 明确授予 GPL 第 2 版或任意后续版本的使用和再分发权。比赛中可以使用。随项目公开分发数据时，应保留数据版权和上游许可声明、附带许可证，并遵守适用的 GPL 条款。Make Me a Hanzi 的 `dictionary.txt` 也允许按 LGPL 条款使用和分发。该项目的笔画图形文件采用另列的许可，未纳入本次统计和交付。

[CJKVI 许可说明](https://github.com/cjkvi/cjkvi-ids/blob/86b4d16159f0079437870408f0ca186e529015db/README.md#licenses) · [CHISE 许可说明](https://github.com/chise/ids/blob/0b45762b5728783fc2bc58a1e3c57ba0a7c5fcfc/README.md#license) · [Make Me a Hanzi 许可声明](https://github.com/skishore/makemeahanzi/blob/bddc96d41bef78427ed0e034e9f7e31d71fd1b92/COPYING) · [GNU GPL 第 2 版全文](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)

## 选定数据

选用 CJKVI IDS 的 `ids.txt`，提交版本为 `86b4d16159f0079437870408f0ca186e529015db`。它覆盖全部规范字头，对 7,952 个规范字给出带结构符的 IDS，并通过如 `[G]` 的地区标签区分部分字形。文件原样保存，SHA-256 为 `bfc70a8c09f9f5616ebf0543bd6681e67314e9f7ae2307e5ae8c6f15bdc5c6a6`。目录已附 CJKVI、CHISE 上游许可声明及 GPL 第 2 版全文。

本次选用一个数据集。CJKVI 与 CHISE 同源，规范字头覆盖相同。Make Me a Hanzi 的部件与笔画对应关系可供后续独立评估，单独使用其词典只能覆盖 6,866 个规范字头。示例中，CJKVI 将“己”列为单字部件，无法凭这条记录判定它与“已”相差几笔。CJKVI 的“茶”使用三元上下结构，CHISE 使用嵌套的两级上下结构，二者的结构表达存在差异。

## 统计方法

1. 将《通用规范汉字表》公开文本转录中的第 0001–8105 号条目作为分母。依编号顺序取每行首个 Unicode 码点，排除脚注后缀及变体选择符。断言编号连续、去重后字头仍有 8,105 个。该输入使用公开转录，尚未逐字与教育部 PDF 对照。统计输入 SHA-256 为 `b9a98c5d1a4b0aec2c0867bbccbdfb4a453540f602dc612f05a1b0d3518dd93e`。
2. CJKVI 从 `ids.txt` 首列的 Unicode 码点取字头。CHISE 合并固定版本中全部 18 个 `IDS-UCS-*.txt` 文件，首列兼容 `U+` 和 `U-` 写法。Make Me a Hanzi 解析 `dictionary.txt` 每行 JSON 的 `character` 字段。各取唯一字头，与分母按码点求交集，不做繁简、异体或兼容字转换。
3. 字头命中即计入覆盖。命中的任一 IDS 字段存在 IDS 运算符（U+2FF0–U+2FFF、U+31EF，含 CHISE 扩展结构实体）时，计入含结构符；同一字段无 `？` 或 `?` 时，再计入最后一列。圈号、其他实体引用仍按原值保留，这一指标只检查问号占位。字头自指记录计入覆盖；只有自指的记录没有结构符。
4. Make Me a Hanzi 缺 1,239 个规范字头。CHISE 与 CJKVI 的字头未见缺失。未入选的两套数据只用于统计，交付目录只包含选中的数据、许可和报告。

[教育部《通用规范汉字表》](https://www.moe.gov.cn/jyb_xwfb/moe_2082/siju/yywzxxgls/ztzl_yywzgfbz/201306/t20130601_186002.html) · [8105 字统计用公开转录](https://github.com/kurikomoe/TCAA_CHS/blob/main/third/%E9%80%9A%E7%94%A8%E8%A7%84%E8%8C%83%E6%B1%89%E5%AD%97%E8%A1%A8.txt)

## 五字原始行

### CJKVI IDS

[ids.txt](https://github.com/cjkvi/cjkvi-ids/blob/86b4d16159f0079437870408f0ca186e529015db/ids.txt)

```text
U+6C90	沐	⿰氵木
U+6CAD	沭	⿰氵术[G]	⿰氵朮[TK]
U+8336	茶	⿳艹人朩
U+837C	荼	⿱艹余
U+5DF1	己	己
```

### CHISE IDS

[IDS-UCS-Basic.txt](https://github.com/chise/ids/blob/0b45762b5728783fc2bc58a1e3c57ba0a7c5fcfc/IDS-UCS-Basic.txt)

```text
U+6C90	沐	⿰氵木
U+6CAD	沭	⿰氵术
U+8336	茶	⿱艹⿱𠆢朩
U+837C	荼	⿱艹余
U+5DF1	己	己
```

### Make Me a Hanzi

[dictionary.txt](https://github.com/skishore/makemeahanzi/blob/bddc96d41bef78427ed0e034e9f7e31d71fd1b92/dictionary.txt)

```text
{"character":"沐","definition":"to bathe, to cleanse, to shampoo, to wash","pinyin":["mù"],"decomposition":"⿰氵木","etymology":{"type":"pictophonetic","phonetic":"木","semantic":"氵","hint":"water"},"radical":"氵","matches":[[0],[0],[0],[1],[1],[1],[1]]}
{"character":"沭","definition":"a river in Shantung province","pinyin":["shù"],"decomposition":"⿰氵术","etymology":{"type":"pictophonetic","phonetic":"术","semantic":"氵","hint":"water"},"radical":"氵","matches":[[0],[0],[0],[1],[1],[1],[1],[1]]}
{"character":"茶","definition":"tea; tea leaves; tea plant","pinyin":["chá"],"decomposition":"⿱艹⿱人木","etymology":{"type":"pictophonetic","semantic":"艹","hint":"plant"},"radical":"艹","matches":[[0],[0],[0],[1,0],[1,0],[1,1],[1,1],[1,1],[1,1]]}
{"character":"荼","definition":"a bitter vegetable","pinyin":["tú"],"decomposition":"⿱艹余","etymology":{"type":"pictophonetic","phonetic":"余","semantic":"艹","hint":"plant"},"radical":"艹","matches":[[0],[0],[0],[1],[1],[1],[1],[1],[1],[1]]}
{"character":"己","definition":"self, oneself; personal, private; 6th heavenly stem","pinyin":["jǐ"],"decomposition":"⿱？乚","etymology":{"type":"pictographic","hint":"A loom woven with thread"},"radical":"己","matches":[null,null,[1]]}
```
