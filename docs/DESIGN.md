# SBtranslator 设计说明

这份文档说明代码是怎么设计的：有哪些部分、每部分做什么、一句话从输入到输出经过哪些步骤。代码里的注释讲细节，这里讲整体。

## 1. 五种模式

| 模式 | 背后的函数 | 做法 | "Long time no see" 的结果 |
|---|---|---|---|
| stupid（默认） | `inject.translate_injected()` | 整句正常翻译，只把几个词换成蠢词（梗名、缩写直译、术语的日常意思等），读起来通顺但意思不对 | @frozen: teses, your HLTV top is 0, lol → @冰雪奇缘：滔搏们，你的一半生活电视顶部是0，英雄联盟 |
| wordy | `translate_word_by_word()` | 每个词单独翻译，一部分词换成「错但真实存在」的意思 | Long time no see → 久时间非望、长期时间没有望（每次不同） |
| plain | `translate_word_by_word(rare=False)` | 每个词单独翻译，用常见意思 | 长的时间不看 |
| proper | `translate()` | 整句正常翻译 | 好久不见 |
| classical | `translate_classical()` | 整句翻成文言文，繁体字 | 久違矣 |

除了文言文用 Bing，其他模式都用 Google 翻译。所有模式都需要联网。

## 2. 文件结构

```
SBtranslator/
├── translator.py      根目录的入口：py translator.py "..."（只调用包里的 main()）
├── learn.py           根目录的入口：py learn.py
├── overlay.py         根目录的入口：py overlay.py，也是 exe 的入口
├── listen.py          根目录的入口：py listen.py douyu 6657
├── build_exe.py       用 PyInstaller 打包成 dist/SBtranslator-windows.zip
├── pyproject.toml     pip 安装配置，定义 sbtranslator 等 4 个命令
├── docs/DESIGN.md     这份文档
└── sbtranslator/      真正的代码（一个 Python 包）
    ├── __init__.py    门面：translate(text, mode, rarity)，外部程序只调用它
    ├── translator.py  翻译逻辑和命令行，分 12 个部分
    ├── inject.py      默认的傻瓜模式：正常翻译打底，塞进蠢词
    ├── phrases.py     从弹幕做短语表（载物玩耍 → zywoo play）
    ├── learn.py       维基百科爬虫，学梗和人名
    ├── chat.py        读斗鱼和 Twitch 直播间的弹幕（只读）
    ├── learn_chat.py  从弹幕里找梗
    ├── server.py      HTTP 接口，给其他语言的程序用
    ├── overlay.py     置顶悬浮窗
    ├── check.py       用本地 AI 模型（DeepSeek，经 Ollama）校对傻瓜翻译
    └── data/          词表、梗词典、简繁转换表
```

根目录的三个 `.py` 只是为了让 `py translator.py` 这种老命令继续能用，代码都在 `sbtranslator/` 里。

## 3. UML 类图

```mermaid
classDiagram
    class inject {
        <<inject.py 注入模式>>
        +translate_injected(text, details) str
        +inject(text) tuple
        +stupid_word(token, proper) str
        +handle_word(token, any_unique) str
        -_repair(output, wanted) str
    }
    class phrases {
        <<phrases.py 弹幕短语表>>
        +make_candidates(chinese_memes) dict
        +review()
        +split_words(phrase) list
        +to_english(word, handles) str
        +nicknames() dict
    }
    class sbtranslator {
        <<__init__.py 门面>>
        +MODES
        +translate(text, mode, rarity) str
    }
    class Pipeline {
        <<translator.py 第9、11、12部分>>
        +SKIPPED_WORDS
        +CONTRACTIONS
        +translate_word_by_word(text, rare, target_rarity) str
        +expand_contraction(token) list
        -word_options(word) list
        +main()
    }
    class GoogleTranslate {
        <<translator.py 第1部分>>
        +translate(text) str
        -_translate_chrome_ex(text) str
        -_translate_gtx(text) str
        -_translate_words_chrome_ex(words) list
        -_translate_words_gtx(words) list
        -_get_json(url, params) dict
    }
    class ClassicalChinese {
        <<translator.py 第2部分>>
        -_bing_session
        -_s2t_table
        +translate_classical(text) str
        +has_simplified(text) bool
        +to_traditional(text) str
        -_get_bing_session() tuple
        -_load_s2t_table() dict
    }
    class Meanings {
        <<translator.py 第3、4、6、7部分>>
        +STANDALONE_FORMS
        +EXTRA_MEANINGS
        +IRREGULAR_PAST_FORMS
        -_round_trip_cache
        +dictionary_meanings(word, standalone_only) list
        +round_trip_meanings(word) list
        +standalone_meaning(word) str
    }
    class Rarity {
        <<translator.py 第3、8部分>>
        +TARGET_RARITY = 0.8
        +MAX_RARITY = 3.0
        +spread_rarity(options, target_rarity) dict
    }
    class CompoundWords {
        <<translator.py 第5部分>>
        +MIN_SPLIT_LETTERS = 4
        +split_compound(word) list
        -_best_split(w, parts_set) list
        -_is_real_word(part) bool
    }
    class Memes {
        <<translator.py 第10部分>>
        +MEMES_FILES
        -_memes
        +meme_for(word) str
        +closest_name(word, names) str
        -_load_memes() dict
        -_typo_distance(a, b) int
    }
    class learn {
        <<learn.py 爬虫>>
        +learn(titles, seeds, common_words) dict
        +english_pages(titles) dict
        +chinese_pages(zh_titles) dict
        +clean_zh(name) str
        +find_nickname(intro) str
        -api(lang, params) dict
        +main()
    }
    class chat {
        <<chat.py 读弹幕>>
        +messages(source, room, seconds)
        +douyu_messages(room, seconds)
        +twitch_messages(channel, seconds)
    }
    class learn_chat {
        <<learn_chat.py 弹幕学梗>>
        +record(source, room, minutes) int
        +find_memes(min_people) tuple
        +learn(chinese, english) tuple
        +main()
    }
    class check {
        <<check.py 本地模型校对>>
        +MODEL = deepseek-r1:14b
        +VARIANTS = 4
        +checked_translation(text, rarity, rare) str
        +proofread(english, candidates, proper) str
        -_ask(messages, model, timeout) str
        -_skeleton(text) str
    }
    class BaseHTTPRequestHandler {
        <<Python 标准库>>
    }
    class Handler {
        <<server.py>>
        +do_GET()
        +do_POST()
        +do_OPTIONS()
        -_translate(params)
        -_send(status, body)
    }
    class Overlay {
        <<overlay.py>>
        +root
        +events Queue
        +request int
        +translate()
        +copy()
        +toggle()
        -_work(request, text, mode, rarity)
        -_poll()
        -_build()
    }
    class DataFiles {
        <<data 文件夹>>
        memes_learned.json
        memes.json
        memes_chat.json
        stupid_words.json
        phrases.json
        nicknames.json
        players.txt
        chat_meanings.json
        meme_seeds.txt
        words/common_english.txt
        opencc/STCharacters.txt
        opencc/STPhrases.txt
        .cache/round_trip.json
    }
    class OnlineServices {
        <<网上的服务>>
        Google Translate
        Bing Translator
        Wikipedia API
        斗鱼 / Twitch 弹幕
        Ollama 本地模型
    }

    BaseHTTPRequestHandler <|-- Handler
    Handler ..> sbtranslator : translate()
    Overlay ..> sbtranslator : translate()
    sbtranslator ..> inject : stupid
    sbtranslator ..> Pipeline : wordy / plain
    inject ..> GoogleTranslate : 整句翻译
    inject ..> Memes : 梗名
    inject ..> CompoundWords : 复合词
    inject ..> phrases : 外号
    inject ..> DataFiles : 读 stupid_words.json、phrases.json
    learn_chat ..> phrases : 出短语候选
    phrases ..> DataFiles : 写 phrases.json
    sbtranslator ..> GoogleTranslate : proper
    sbtranslator ..> ClassicalChinese : classical
    sbtranslator ..> check : check=True
    check ..> Pipeline : 生成 4 个版本
    check ..> OnlineServices : Ollama
    Pipeline ..> Memes : 第3步 梗词
    Pipeline ..> CompoundWords : 第4步 复合词
    Pipeline ..> GoogleTranslate : 第5步 逐词翻译
    Pipeline ..> Meanings : 第6-7步 候选意思
    Pipeline ..> Rarity : 第7步 分配稀有度
    Meanings ..> GoogleTranslate : 查词典
    CompoundWords ..> GoogleTranslate : 查词典
    Memes ..> DataFiles : 读
    ClassicalChinese ..> DataFiles : 读 opencc
    learn ..> DataFiles : 写 memes_learned.json
    learn ..> OnlineServices : Wikipedia
    learn_chat ..> chat : 读弹幕
    chat ..> OnlineServices : 斗鱼 / Twitch
    learn_chat ..> DataFiles : 写 chat_meanings.json
    Meanings ..> DataFiles : 读 chat_meanings.json
    GoogleTranslate ..> OnlineServices : Google
    ClassicalChinese ..> OnlineServices : Bing
```

**怎么看这张图：**

- 代码大部分是函数，不是类。图里写着「translator.py 第 N 部分」的方框，是 `translator.py` 里的一组函数，当成一个类来画，好看清它们的分工；名字（Pipeline、Meanings 等）是为这张图起的，代码里没有这些类。代码里真正的类只有 `Handler`（server.py）和 `Overlay`（overlay.py）。
- `+` 是给外面用的函数，`-` 是内部函数（名字以 `_` 开头）。只写了重要的函数，完整的列表看代码。
- 空心三角箭头是继承：`Handler` 继承 Python 自带的 `BaseHTTPRequestHandler`。
- 虚线箭头是「调用 / 用到」，箭头上的字说明用来做什么。

## 4. 两种傻瓜模式的流程

### 默认的傻瓜模式（注入，`inject.py`）

逐词翻译读起来像乱码，而好笑的机翻梗是「通顺但意思不对」：只有几个词是蠢的，其他都是正常中文。所以默认模式这样做：

1. 先整句正常翻译，知道每个词在这句里的正确意思。
2. 挑出要变蠢的词，查出它的蠢译法（`stupid_word()`），按这个顺序：弹幕短语表（life game → 生命游戏，最长的优先）、梗名和战队名（frozen → 冰雪奇缘，复数随机变成「滔搏们」或「一些滔搏」）、选手外号（zywoo → 载物）、缩写展开再逐词直译（HLTV → half life tv → 一半生活电视）、选手 ID 读成最近的英文词（m0NESY → money → 钱）、术语的日常意思（major → 主要，只有正常译文里没有这个意思时才换）、复合词、像名人名字的独特词（karrigan → 刀锋女王）。
3. 把蠢词用【】直接写进英文原句（your 【主要】 champion），整句交给 Google 翻译，Google 会围着这些词把语序和虚词补成正常中文。
4. 去掉【】，把 Google 改动过的蠢词按字形换回来（滔滔搏们 → 滔搏们）。有词丢了就换「」再试一次。

加 `--check` 时，第 3 步改由本地模型造句：要求每个蠢词一字不差地出现，程序检查，不行就再问，最多 3 次，还不行就用 Google 的版本。Google 最常改掉的是动词（clutch 离合器、play 玩耍），本地模型能放进去。

### 逐词模式（wordy，`translate_word_by_word()`）

原来的傻瓜模式，翻译腔更重，每个词单独翻译。代码里也按这 8 步编号。

```mermaid
flowchart TD
    A["英文句子"] --> B["1 切成单词和标点"]
    B --> C["2 清理：展开 can't，去掉 the"]
    C --> D["3 梗词和人名直接替换"]
    D --> E["4 复合词拆开"]
    E --> F["5 每个词单独翻译，一次请求"]
    F --> G["6 过去式词用它本身的意思"]
    G --> H{"stupid 模式？"}
    H -- 是 --> I["7 列出每个词的候选意思，按预算分配稀有度"]
    H -- 否，plain 模式 --> J["8 拼回句子，换成中文标点"]
    I --> J
```

用这句话走一遍（下面是在你电脑上实际跑出来的中间结果）：

> teses: wow frozen, your firepower is the same as karrigan, you can't even make him into playoff, lol

| 步骤 | 做了什么 | 这句话的结果 |
|---|---|---|
| 1 切词 | 用正则把单词和标点分开 | `teses` `:` `wow` `frozen` `,` `your` `firepower` … |
| 2 清理 | `can't` → `can` `not`；去掉 `the` | 少了 the，多了 can、not |
| 3 梗词 | 查梗词典（第 10 部分） | teses → 滔搏们（TES 的复数），frozen → 冰雪奇缘，karrigan → 刀锋女王（当成 kerrigan 的拼写错误），lol → 英雄联盟 |
| 4 复合词 | 拆成常见词（第 5 部分），拆出来的部分也查梗词典 | firepower → fire + power，playoff → play + off，off 在 memes.json 里 → 关 |
| 5 逐词翻译 | 剩下的词一次发给 Google | wow → 哇，fire → 火，power → 力量，same → 相同的，as → 作为，can → 能，not → 不是，even → 甚至 … |
| 6 过去式 | 这句没有；比如 saw 会变成 锯 | |
| 7 稀有度 | 先整句正常翻译，看哪些意思「对」；再给每个词列候选意思，随机分配稀有度预算 | even 的正常意思是「连」（正常译文里有「连」），候选有 偶数 0.92、更 1.5（往返查词找到的）、甚而 2.4；12 个词参加，预算 0.8 × 12 = 9.6 |
| 8 拼句子 | 换成中文标点，中文词之间不加空格 | 滔搏们：哇冰雪奇缘，你的火力量是同样如同刀锋女王，您可非偶数让他进入玩关，英雄联盟 |

第 7 步每次随机，所以每次结果不一样。

## 5. 每个部分在做什么

### sbtranslator/translator.py

| 部分 | 主要函数和设置 | 作用 |
|---|---|---|
| 1 Google 翻译 | `translate()`、`_translate_words_chrome_ex()`、`_get_json()` | 调用 Google 免费的翻译接口。每种请求有两个接口，第一个失败（比如被限流 429）就换第二个 |
| 2 文言文 | `translate_classical()`、`to_traditional()` | Google 不支持文言文，所以用 Bing 网页版的接口（先从 Bing 页面拿 cookie 和 token）。结果里的简体字用 OpenCC 词典转成繁体，先匹配最长的词 |
| 3 设置 | `TARGET_RARITY`、`STANDALONE_FORMS`、`EXTRA_MEANINGS`、`IRREGULAR_PAST_FORMS` | 所有可以调的数字和词表都集中在这里 |
| 4 词典意思 | `dictionary_meanings()` | 取 Google 词典里一个词的全部意思和使用频率，算出稀有度 = −log10(频率) |
| 5 复合词 | `split_compound()`、`_best_split()` | 用动态规划把词拆成常见词，部件越少越好；再用 Google 词典确认每个部件是真词（排除 fri + end 这种） |
| 6 往返查词 | `round_trip_meanings()` | 英→中→英→中，找词典里没有的意思（list → 单子）。只对最常见的 3000 个词做，结果存到缓存文件 |
| 7 过去式 | `standalone_meaning()` | saw、left 这种本身也是词的过去式，用它本身最常见的意思（锯、左） |
| 8 稀有度 | `spread_rarity()` | 整句有一个稀有度预算（目标 × 词数），随机顺序给每个词分一部分，所以有的词离谱，有的词正常，平均值等于目标 |
| 9 清理规则 | `expand_contraction()`、`SKIPPED_WORDS` | 展开 can't、I'm；去掉 the |
| 10 梗词 | `meme_for()`、`closest_name()` | 查梗词典：先查原词，再查复数（加「们」）。不是英文单词的独特词（比如选手名）当成拼写错误，换成最像的有名的名字：karrigan 和 kerrigan 只差一个字母，所以变成 kerrigan 的译名 刀锋女王 |
| 11 流程 | `translate_word_by_word()` | 把上面所有部分按第 4 节的 8 步串起来 |
| 12 命令行 | `main()` | 读命令行参数，选模式，翻译一次或进入交互模式 |

### 其他文件

| 文件 | 作用 |
|---|---|
| `sbtranslator/__init__.py` | 门面。外部程序只调用 `translate(text, mode, rarity)`，不需要知道每种模式由哪个函数实现 |
| `sbtranslator/learn.py` | 爬虫。对每个维基页面：英文版拿中文链接和重定向（LoL），中文版拿简体标题和开头的「简称TES」，去掉「电子竞技俱乐部」这类后缀。开头如果有「自封」「人称」「绰号」这样的外号（自封刀锋女王），就用外号代替名字。结果存进 `memes_learned.json`，每次请求间隔 0.5 秒 |
| `sbtranslator/chat.py` | 读直播间弹幕，只读、匿名，从不发言。Twitch 用匿名 IRC；斗鱼用 WebSocket 加斗鱼自己的 STT 格式，WebSocket 是用标准库自己写的，所以不用装别的包 |
| `sbtranslator/learn_chat.py` | 从弹幕学梗。弹幕存在缓存文件夹里（用户名换成短哈希）。至少 3 个不同的人发过的短弹幕算中文梗，翻成英文后，最后一个有意义的词得到这个梗作为傻瓜意思（恶龙呢 → "Where's the dragon?" → dragon）；英文聊天里不是英文单词的词（LULW）算英文梗，Google 能翻的就变成梗词 |
| `sbtranslator/inject.py` | 默认的傻瓜模式，见第 4 节。表在 `data/stupid_words.json`（战队名和撞名的游戏缩写、缩写展开、术语的日常意思），可以自己加 |
| `sbtranslator/phrases.py` | 弹幕短语表。至少 3 个人发过的短弹幕（8 个字以内）切成词，每个词找英文：先查外号表（载物 → zywoo），再看英文意思里有没有选手 ID（设备 → device），都没有就用最常见的意思（生命 → life），拼成 life game → 生命游戏 这样的候选。`py listen.py --review` 逐个确认，确认的进 `phrases.json` |
| `sbtranslator/check.py` | 本地模型（`--check`）。默认傻瓜模式里由它造句（见第 4 节）；wordy 和 plain 模式里是校对。傻瓜模式一次生成 4 个版本（共用同一批查询，不多花请求），交给本机 Ollama 里的 DeepSeek-R1 14b，让它挑最好笑、但还读得通的一个，只准增删「的、了、在」这类虚词。程序会核对：去掉虚词和标点后，句子必须和它挑的那个一模一样，否则就不用它的修改 |
| `sbtranslator/server.py` | HTTP 接口。Python 自带的 `ThreadingHTTPServer` 每来一个请求就开一个线程，交给 `Handler`；`Handler` 只负责把请求转成 `translate()` 调用，再把结果写成 JSON |
| `sbtranslator/overlay.py` | 悬浮窗。tkinter 只允许主线程碰窗口，所以翻译在工作线程里做，热键在热键线程里等；两者都把结果放进队列 `events`，主线程每 50 毫秒用 `_poll()` 取出来显示 |
| `build_exe.py` | 用 PyInstaller 把 Python、代码和 data 打成一个文件夹再压缩成 zip（不用单文件 exe，因为它容易被杀毒软件误报）|

## 6. 数据文件

| 文件 | 内容 | 谁读 / 谁写 |
|---|---|---|
| `data/memes_learned.json` | 爬虫学到的梗：`{"lol": "英雄联盟", ...}` | learn.py 写，第 10 部分读 |
| `data/memes.json` | 你自己写的梗，优先级最高 | 你写，第 10 部分读 |
| `data/memes_chat.json` | 从英文弹幕学到的梗：`{"lulw": "卢尔夫", ...}` | learn_chat.py 写，第 10 部分读 |
| `data/stupid_words.json` | 默认傻瓜模式的手写表：names（导航、魔兽世界）、acronyms（hltv → half life tv）、everyday（major → 主要） | 你写，inject.py 读 |
| `data/phrases.json` | 确认过的短语：`{"life game": "生命游戏"}` | `py listen.py --review` 写，inject.py 读 |
| `data/phrase_candidates.json` | 等你确认的短语候选，和拒绝过的 | phrases.py 读写 |
| `data/nicknames.json` | 选手中文外号：`{"载物": "zywoo"}`，两个方向都用 | 你写，phrases.py 和 inject.py 读 |
| `data/players.txt` | 选手 ID 名单，用来认出 设备 → device | 你写，phrases.py 读 |
| `data/chat_meanings.json` | 从中文弹幕学到的傻瓜意思：`{"dragon": ["恶龙呢"]}` | learn_chat.py 写，第 11 部分的候选意思读 |
| `data/meme_seeds.txt` | 不带参数运行 learn.py 时要学的维基页面 | 你写，learn.py 读 |
| `data/words/common_english.txt` | 最常见的 1 万个英文词，按频率排序 | 复合词、往返查词、梗词判断「是不是普通词」都用它 |
| `data/opencc/*.txt` | 简体 → 繁体对照表 | 第 2 部分读 |
| `.cache/chat/*.tsv` | 录下来的弹幕，每行「用户哈希 + 内容」 | learn_chat.py 读写，不进 git |
| `.cache/round_trip.json` | 往返查词的缓存（exe 里放在 %LOCALAPPDATA%\SBtranslator） | 第 6 部分读写，git 不管它 |

## 7. 为什么这样设计

- **函数为主，不用类。** 翻译的每一步都是「输入一个词或句子，输出结果」，不需要保存状态，用函数最简单。要保存状态的地方（HTTP 请求、窗口）才用类。
- **门面。** 外部只依赖 `sbtranslator.translate()`，内部怎么改都不影响服务器、悬浮窗和别人的程序。
- **用到才加载，加载一次。** 词表、OpenCC 表、梗词典第一次用到时才读，存在以 `_` 开头的模块变量里，之后直接用。往返查词的结果还存到文件，下次运行也不用再查。
- **每个网络请求都有备用方案。** Google 两个接口轮流试；Bing 的会话过期就重新拿；往返查词或词典查询失败，就跳过这个「额外」步骤，不让整句翻译失败。
- **并行查词。** 每个词要查好几次，所以用 4 个线程同时查。缓存被多个线程共用，用锁保护。
- **优先级明确。** 手写的梗 > 学到的梗 > 过去式规则 > 稀有度分配。复合词拆出来的部分保持自然意思，因为拆开本身已经够傻了。
- **可调的东西集中放。** 想改效果只需要改第 3 部分的设置和 data 文件夹里的文件，不用动逻辑。

## 8. 想改效果，改哪里

| 想要 | 改哪里 |
|---|---|
| 整体更傻或更正常 | `TARGET_RARITY`（第 3 部分），或运行时加 `--rarity` |
| 加一个梗 | `data/memes.json`，比如 `"off": "关"` |
| 加蠢词、梗名、缩写 | `data/stupid_words.json`（默认傻瓜模式） |
| 加选手外号或短语 | `data/nicknames.json`、`data/phrases.json`，或 `py listen.py --review` 确认弹幕里的候选 |
| 让 AI 造句或挑版本 | 加 `--check`；换模型设环境变量 `SBTRANSLATOR_MODEL`；版本数是 check.py 里的 `VARIANTS` |
| 从直播间学梗 | 直播时运行 `py listen.py douyu 6657`，学到的越积越多 |
| 让爬虫学新的页面 | `data/meme_seeds.txt` 加一行，然后运行 `py learn.py` |
| 单字换成完整的词（次 → 次数） | `STANDALONE_FORMS`（第 3 部分） |
| 补充 Google 词典没有的意思 | `EXTRA_MEANINGS`（第 3 部分） |
| 某些词不要拆开 | `MIN_SPLIT_LETTERS`、`NOT_PARTS`（第 5 部分） |
