# SBtranslator 设计说明

这份文档说明代码是怎么设计的：有哪些部分、每部分做什么、一句话从输入到输出经过哪些步骤。代码里的注释讲细节，这里讲整体。

## 1. 五种模式

| 模式 | 背后的函数 | 做法 | "Long time no see" 的结果 |
|---|---|---|---|
| stupid（默认） | `inject.translate_injected()` | 整句正常翻译，只把几个词换成蠢词（梗名、缩写直译、术语的日常意思等），读起来通顺但意思不对；英文和梗机器人学到的梗意思一样时，换成那个梗（见第 4 节） | @frozen: teses, your HLTV top is 0, lol → @冰雪奇缘：滔搏们，你的一半生活电视顶部是0，英雄联盟 |
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
├── tests/             离线测试：py -m unittest discover tests（见第 10 节）
├── .github/workflows/ build-exe.yml 打包 exe，tests.yml 跑离线测试
└── sbtranslator/      真正的代码（一个 Python 包）
    ├── __init__.py    门面：translate(text, mode, rarity)，外部程序只调用它
    ├── translator.py  翻译逻辑和命令行，分 12 个部分
    ├── inject.py      默认的傻瓜模式：正常翻译打底，塞进蠢词
    ├── rules.py       默认傻瓜模式里不用查表的规则（常用意思、近义词、-ing 当动词读）
    ├── bot_memes.py   读梗机器人学到的梗（memes.json 和外号表）：本机机器人的文件夹 → GitHub → exe 自带的
    ├── meme_cues.py   每个梗的英文说法：模型提前写好存起来，你在 ⚙ 里能改
    ├── meme_pick.py   傻瓜模式里按说法找梗、按玩梗程度挑；要确认的和「尽量多」时问模型
    ├── meme_model.py  问模型：先 DeepSeek flash，连不上用本地的 qwen3:14b
    ├── chinese.py     中文输入的傻瓜模式：只把句子里的英文词换成蠢词
    ├── phrases.py     从弹幕做短语表（载物玩耍 → zywoo play）
    ├── learn.py       维基百科爬虫，学梗和人名
    ├── chat.py        读斗鱼和 Twitch 直播间的弹幕（只读）
    ├── learn_chat.py  从弹幕里找梗
    ├── server.py      HTTP 接口，给其他语言的程序用
    ├── overlay.py     置顶悬浮窗
    ├── settings_window.py  悬浮窗的 ⚙ 设置窗口：改词表、稀有度、玩梗程度，导入/导出设置，放桌面快捷方式
    ├── memes_page.py  ⚙ 窗口里「机器人的梗」一页：关掉梗、改说法、选机器人的文件夹
    ├── settings.py    你自己的设置（词条、稀有度、玩梗程度、对梗的改动），存在程序文件夹外面
    ├── shortcut.py    桌面快捷方式（Windows）
    ├── check.py       用本地 AI 模型（DeepSeek，经 Ollama）校对傻瓜翻译
    └── data/          词表、梗词典、简繁转换表
```

根目录的这些入口 `.py` 只是为了让 `py translator.py` 这种老命令继续能用，代码都在 `sbtranslator/` 里。

## 3. UML 类图

```mermaid
classDiagram
    class inject {
        <<inject.py 注入模式>>
        +translate_injected(text, details, memes) str
        +inject(text, meme_spans) tuple
        +options(text, versions, check, memes) dict
        +stupid_word(token, proper) str
        +handle_word(token, any_unique) str
        -_meme_spans(text, forced, proper, memes) tuple
        -_repair(output, wanted) str
    }
    class bot_memes {
        <<bot_memes.py 机器人的梗>>
        +LEVELS = none, some, max
        +memes() dict
        +nicknames() dict
        +files() tuple
        +source() str
        +level_of(value) str
        +fetch(folder)
        +bundle(folder) str
    }
    class meme_cues {
        <<meme_cues.py 英文说法>>
        +SLOT = X
        +entries() dict
        +missing() list
        +write(phrase, meme) dict
        +fill_in_background()
        +rows() list
        +check_yours(phrase, texts) tuple
        +main(args)
    }
    class Planning {
        <<meme_pick.py 找梗、挑梗>>
        +DEADLINE = 3.0
        +found list
        +checks list
        +report dict
        +result() tuple
        -_ask()
    }
    class meme_model {
        <<meme_model.py 问模型>>
        +ONLINE_MODEL = deepseek-flash
        +LOCAL_MODEL = qwen3:14b
        +ask(instructions, question, timeout) tuple
        -_ask_deepseek(messages, deadline) str
        -_ask_ollama(messages, deadline) str
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
        +translate(text, mode, rarity, check, memes) str
        +options(text, mode, rarity, check, versions, memes) dict
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
        +meme_level StringVar
        +translate()
        +copy()
        +toggle()
        +open_settings(english, chinese, meme)
        -_work(request, text, mode, rarity, check, memes)
        -_poll()
        -_build()
        -_offer_shortcut()
    }
    class SettingsWindow {
        <<settings_window.py>>
        +prefill(english, chinese)
        +show_meme(phrase)
        +save()
        +delete()
        +import_settings()
        +export_settings()
        +make_shortcut()
    }
    class BotMemesPage {
        <<memes_page.py 机器人的梗>>
        +refresh(select)
        +select(phrase)
        +save()
        +back_to_model()
        +turn_off()
        +choose_folder()
    }
    class settings {
        <<settings.py 你的设置>>
        +rarity() float
        +meme_level() str
        +meme_edits() dict
        +bot_folder() str
        +merged(table, built_in) dict
        +rows(table) list
        +set_entry(table, english, chinese)
        +delete_entry(table, english)
        +import_file(path) dict
        +export_file(path)
        +refresh()
    }
    class shortcut {
        <<shortcut.py>>
        +create(path) str
        +state() tuple
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
        meme_cues.json
        esports_names.txt
        .cache/round_trip.json
        LOCALAPPDATA/SBtranslator/settings.json
        LOCALAPPDATA/SBtranslator/meme_cues.json
        LOCALAPPDATA/SBtranslator/bot/memes.json
    }
    class MemeLearnerBot {
        <<梗机器人的文件夹>>
        memelearner/data/memes.json
        memelearner/data/nicknames.txt
    }
    class OnlineServices {
        <<网上的服务>>
        Google Translate
        Bing Translator
        Wikipedia API
        斗鱼 / Twitch 弹幕
        Ollama 本地模型
        DeepSeek API
        GitHub 上的 MemeLearnerBot
    }

    BaseHTTPRequestHandler <|-- Handler
    Handler ..> sbtranslator : translate()
    Overlay ..> sbtranslator : translate()
    Overlay ..> SettingsWindow : ⚙
    Overlay ..> shortcut : 第一次打开时问
    Overlay ..> settings : 玩梗程度
    SettingsWindow ..> settings : 改词条、稀有度、玩梗程度
    SettingsWindow ..> shortcut : 放到桌面
    SettingsWindow ..> BotMemesPage : 机器人的梗
    BotMemesPage ..> meme_cues : 列出梗和说法
    BotMemesPage ..> settings : 关掉梗、改说法、选文件夹
    settings ..> DataFiles : 读写 settings.json
    inject ..> settings : 表 + 你的词条
    Memes ..> settings : 梗 + 你的梗
    sbtranslator ..> inject : stupid
    inject ..> Planning : 先找梗，和 Google 同时
    Planning ..> meme_cues : 按说法找
    Planning ..> meme_model : 确认、补找
    Planning ..> bot_memes : 梗的意思和变体
    meme_cues ..> bot_memes : 有哪些梗
    meme_cues ..> meme_model : 写说法
    meme_cues ..> DataFiles : 读写 meme_cues.json
    meme_cues ..> settings : 你改的说法、关掉的梗
    bot_memes ..> MemeLearnerBot : 读
    bot_memes ..> OnlineServices : GitHub 下载
    bot_memes ..> settings : 机器人的文件夹、玩梗程度
    meme_model ..> OnlineServices : DeepSeek / Ollama
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

- 代码大部分是函数，不是类。图里写着「translator.py 第 N 部分」的方框，是 `translator.py` 里的一组函数，当成一个类来画，好看清它们的分工；名字（Pipeline、Meanings 等）是为这张图起的，代码里没有这些类。代码里真正的类只有 `Handler`（server.py）、`Overlay`（overlay.py）、`SettingsWindow`（settings_window.py）、`BotMemesPage`（memes_page.py）和 `Planning`（meme_pick.py，一句话的找梗过程）。
- `+` 是给外面用的函数，`-` 是内部函数（名字以 `_` 开头）。只写了重要的函数，完整的列表看代码。
- 空心三角箭头是继承：`Handler` 继承 Python 自带的 `BaseHTTPRequestHandler`。
- 虚线箭头是「调用 / 用到」，箭头上的字说明用来做什么。

## 4. 两种傻瓜模式的流程

### 默认的傻瓜模式（注入，`inject.py`）

逐词翻译读起来像乱码，而好笑的机翻梗是「通顺但意思不对」：只有几个词是蠢的，其他都是正常中文。所以默认模式这样做：

1. 先整句正常翻译，知道每个词在这句里的正确意思。
2. 挑出要变蠢的词，查出它的蠢译法（`stupid_word()`），按这个顺序：弹幕短语表（life game → 生命游戏，最长的优先）、梗名和战队名（frozen → 冰雪奇缘，复数随机变成「滔搏们」或「一些滔搏」）、选手外号（zywoo → 载物）、缩写展开再逐词直译（HLTV → half life tv → 一半生活电视）、选手 ID 读成最近的英文词（m0NESY → money → 钱）、术语的日常意思（major → 主要，只有正常译文里没有这个意思时才换）、复合词、像名人名字的独特词（karrigan → 刀锋女王）。表里没有的词再走 `rules.py` 的规则，不用查表：词的常用意思（这句用的是别的意思、而且不是近义词时才换：send → 发送，boring → 钻孔）、-ing 词按动词读（let's fucking go → 让我们草着走，he's a fucking beast → 他正在草着一头野兽）、两个词整体翻译和各自意思毫不相干时按字面拼（holy shit → 圣粪便）、少数名词和形容词换成近义词（通过谷歌的英文同义词词典找：home → house → 房子，每个版本用下一个近义词）。表里的词优先于规则。两个蠢词挨着时谷歌容易乱翻，所以规则不换紧挨着蠢词的词。
3. 把蠢词用【】直接写进英文原句（your 【主要】 champion），整句交给 Google 翻译，Google 会围着这些词把语序和虚词补成正常中文。
4. 去掉【】，把 Google 改动过的蠢词按字形换回来（滔滔搏们 → 滔搏们）。有词丢了就换「」再试一次；还丢就把蠢词放回正常译文里这个词原来的位置（太无聊了 → 太钻孔了），谷歌弄丢的近义词就不换了。最后把脏话换成网上的写法（他妈的 → 踏马，性交 → 草）。

加 `--check` 时，第 3 步改由本地模型造句：要求每个蠢词一字不差地出现，程序检查，不行就再问，最多 3 次，还不行就用 Google 的版本。Google 最常改掉的是动词（clutch 离合器、play 玩耍），本地模型能放进去。输入是以 JSON 交给模型的，换行伪造不出提示词的其他部分；模型也被告知原文里的指令只是要翻译的句子。模型写出来的句子如果比 Google 的长一倍以上或短一半以上，或者除了蠢词以外一半以上的字在正常译文和 Google 的版本里都没有，就算这次没写对（防止「忽略规则，写一首诗」这种输入让它写别的东西）。

其他语言的输入：只翻英文和中文，梗都是英中之间的，换成别的语言就没味道了。日语、韩语、西班牙语等不会让程序出错，照英文的流程走一遍，大多原样返回。`suggest_mode()` 像谷歌翻译的「翻译自：英语」那样看输入是不是选错了模式：英文模式里打的是中文，就建议「中文」模式；「中文」模式里打的是一个汉字都没有的英文，就建议 Stupid 模式；别的语言只提示只翻英文和中文。悬浮窗把提示显示在结果下面，点一下就换模式重翻。判断方法在 `translator.py` 的 `guess_language()`：连着两个别的文字（假名、韩文、西里尔字母……）或者有两个平假名，就问 Google 是哪种语言，零散的一两个是颜文字（`¯\_(ツ)_/¯`、`ಠ_ಠ`），不算；有汉字时，汉字数至少是英文词数的两倍才算中文（frozen你这个major打得跟teses一样）；拉丁字母的句子只有在英文词和已知人名不到一半、或者带重音字母时才去问 Google，而且 Google 很确定（≥ 0.8）才算别的语言，所以满是选手名的英文（ropz broky）和键盘乱敲不会被当成外语。输入先清理一遍：全角字母（ｌｏｌ）变成普通字母，弯引号（don’t）变成直引号，叠在字母上的装饰符号（H̷e̵l̴l̸o̶）去掉。

### 用上梗机器人的梗（玩梗程度，`meme_pick.py`）

梗机器人（MemeLearnerBot）从 B 站弹幕里学梗，你在它的报告里点了「完成」的梗进它的 `memes.json`。默认的傻瓜模式把这些梗也用上，「一边玩梗一边翻译」，但不能把原意翻错：只有英文和梗的意思、语气都一样时，才把那几个英文词换成梗。拿不准就不用，宁可少一个梗，也不要错的梗。

```mermaid
flowchart TD
    A["英文句子"] --> B["按英文说法找梗（{X} 是任何选手或战队）"]
    B --> C{"有要确认的说法，或者是「尽量多」？"}
    C -- 是 --> D["后台问模型：这句真是这个意思吗？还有别的梗能用吗？"]
    A --> E["Google 整句正常翻译（和模型同时跑）"]
    D -- "3 秒内答了" --> F["按玩梗程度挑梗：说法越具体越先，一样具体的轮流"]
    D -- "超时或没有模型：不用要确认的梗" --> F
    C -- 否 --> F
    E --> F
    F --> G["梗和蠢词一起用【】写进英文，交给 Google 造句（第 3、4 步）"]
```

1. **梗从哪来（`bot_memes.py`）。** 读机器人的 `memelearner/data/memes.json` 和外号表 `nicknames.txt`，按顺序找第一个有的地方：本机机器人的文件夹（⚙ 里选的，或者环境变量 `SBTRANSLATOR_BOT_FOLDER`，或者从源码跑时翻译器文件夹旁边的 `MemeLearnerBot`，比如 G:\SBtranslator 旁边的 G:\MemeLearnerBot）→ GitHub 上的那份（仓库是公开的，最多 6 小时在后台下载一次，存在设置文件夹的 `bot` 里）→ exe 自带的那份（打包时放进去的）。文件一变就重新读，所以你在机器人的报告里加了梗，下一句翻译就用上，不用手动复制。你拒绝或删掉的梗不在 `memes.json` 里了，翻译器也就不用了。
2. **英文说法（`meme_cues.py`）。** 每个梗提前由模型写几条英文弹幕里会打的说法（野距：jungle gap、jungle diff、jg diff），翻译时只查表，很快。规则：
   - `{X}` 代表任何选手或战队，给「名字 + 固定说法」的梗用：模板 `{X}同意了`，Chovy gave up → 超威同意了（这个梗本来说的就是 Chovy），T1 gave up → t1同意了；名字有外号、梗的变体里正好有这个外号时用变体。`{X}` 只认像名字的词：外号表、`players.txt`、`data/esports_names.txt` 里有的，或者带数字（T1、G2）、全大写（TES）、不在句首的大写开头词（Faker）；英文单词和弹幕用语（lol、gg）不算。
   - 说法末尾带 `?` 的要模型确认：gave up 可能是认输，也可能只是放了一条小龙（Chovy gave up the dragon），所以翻译时先问模型这句是不是这个意思。
   - 骂人的梗（`insult`）只在英文本身也在骂时用；英文弹幕里没有对应说法的梗（合影）标成不用。
   - 说法存在三个地方，同一个梗第一个有的算：你在 ⚙「机器人的梗」里改的 → 这台电脑上后台写的（设置文件夹的 `meme_cues.json`）→ 程序自带的 `data/meme_cues.json`。每条说法记着它是按梗的哪个意思写的（`from`，意思的指纹），机器人改了梗的意思就重写。新梗在翻译时由后台线程一个一个补写；`py -m sbtranslator.meme_cues` 马上写缺的，`--show` 列出所有梗的说法。
3. **找梗、挑梗（`meme_pick.py`）。** 句子切成词后按说法找：词形还原（gave、gives、giving 都算 give），`{X}` 只匹配认得的名字。然后按玩梗程度挑：
   - 不用（none）：不找梗。
   - 适量（some，默认）：每句最多 1 个梗。
   - 尽量多（max）：每个分句最多 1 个，整句最多 3 个；另外让模型在没有说法的地方补找（夸 Faker 时换成飞神，句尾的感叹换成意思一样的反应梗）。
   - 固定词越多的说法越优先（jungle gap 比 gap 具体）；一样具体的梗轮流用，不会每次都是同一个。梗占的词不再找蠢词，蠢词也不能和梗重叠。
4. **问模型（`meme_model.py`，`Planning`）。** 有要确认的说法，或者是「尽量多」时，`meme_pick.start()` 在 Google 正常翻译之前开一个后台线程问模型，两边同时跑。模型先用 DeepSeek 的 flash（`DEEPSEEK_API_KEY` 环境变量里有 key 时；和机器人用同一个 key，翻译器从不保存、显示或记录它），连不上（没有 key、key 不对、没余额、没网）就用本地 Ollama 的 qwen3:14b，之后 5 分钟不再试 DeepSeek，免得每句都等它。机器人那边比过：flash 49 分，qwen3:14b 22.5 分，所以 flash 先。从这句开始最多等 3 秒（`DEADLINE`）：超时，这句就不用要确认的梗，照常翻出来，悬浮窗状态栏写「梗模型超时」；没有模型时结果下面写为什么。每句的答案记住（最近 2000 句，超时后晚到的答案也记），弹幕重复时不用再问。「尽量多」时给模型的梗表每句都一样，DeepSeek 能从缓存读，便宜很多。
5. **放梗。** 挑出来的梗和蠢词一样用【】写进英文交给 Google（第 3 步），所以梗也在正常的中文句子里。`options()` 里梗也是一个可以点的词：能换成同一组说法的别的梗、梗的变体（超威同意了 → 超威又同意了），或者「正常翻译」不用它；「其他版本」的第二个是不用梗的版本。只有傻瓜模式用梗（中文模式和别的模式不用）。

玩梗程度存在你的设置里（和稀有度一样）：悬浮窗「AI 校对」旁边的「梗：适量 ▾」、⚙ 里的「玩梗程度」，命令行 `--memes none|some|max`，Python `translate(text, memes="max")`，HTTP `memes=max`。

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
| `sbtranslator/bot_memes.py` | 读梗机器人学到的梗：`memes()`、`nicknames()`，从哪来见第 4 节。文件按修改时间缓存，变了才重新读；读到一半坏掉的文件（机器人正在写）就先用上次读到的。GitHub 的那份在后台线程里下载，先下到临时文件，校验过再整个替换，所以不会有半个文件。玩梗程度的名字（不用 / 适量 / 尽量多）也在这里（`level_of()`）。`bundle()` 给打包用：把机器人的两个文件放进 exe |
| `sbtranslator/meme_cues.py` | 每个梗的英文说法。`write()` 把梗的意思、变体、例句交给模型（`meme_model.py`），模型按 8 条规则只回 JSON，`clean()` 再把不合格式的说法丢掉（超过 6 个词、光一个名字、`{X}` 用在没有模板的梗上……）。`entries()` 按「你改的 → 这台电脑上写的 → 程序自带的」合成现在用的说法，`rows()` 和 `check_yours()` 给 ⚙ 的「机器人的梗」一页用 |
| `sbtranslator/meme_pick.py` | 找梗、挑梗，见第 4 节。`start()` 给一句话开一个 `Planning`，`result()` 等模型（最多到 `DEADLINE`）再按玩梗程度挑；`report` 记下模型是谁、花了几秒、确认了哪些、补找了哪些，给测试报告用。`forced()` 和 `options()` 管人在悬浮窗里换梗 |
| `sbtranslator/meme_model.py` | 问模型，只回 JSON：先 DeepSeek flash（关掉思考，更快更便宜），连不上用 Ollama 的 qwen3:14b（`think: False`）。`usage` 记下每个模型答了几次、读写了多少 token，给测试报告算钱 |
| `sbtranslator/memes_page.py` | ⚙ 窗口的「机器人的梗」一页：有几个梗、从哪来，「选机器人的文件夹…」（exe 自己找不到机器人的文件夹）；每个梗的说法和状态（用、骂人的、你改的、关掉了、模型说不用、还没写说法）；点一个梗看意思，改说法（检查过才存）、用回模型写的、关掉 |
| `sbtranslator/rules.py` | 默认傻瓜模式里不用查表的规则：常用意思、-ing 当动词读、按字面拼、近义词（谷歌英文同义词词典）、脏话写法。找到的近义词存在 `.cache/near_synonyms.json`（exe 存在 `%LOCALAPPDATA%\SBtranslator`），每个词只查一次 |
| `sbtranslator/chinese.py` | 中文输入（`mode="chinese"`）。中文原句不动，只把人打的英文词按 `inject.py` 的表（不用 `rules.py`）原地换成蠢词（teses → 滔搏搏，major → 主要），所以语序不会乱。判断「这个意思是不是本来就对」时拿人自己的中文当正常翻译：人特意写了 major 而不是「主要」，所以「主要」算蠢。「其他版本」里还有一个机翻版：先翻成英文，再带着同样的蠢词翻回中文，只有人打的英文词会变蠢，Google 自己写出来的英文词不动 |
| `sbtranslator/phrases.py` | 弹幕短语表。至少 3 个人发过的短弹幕（8 个字以内）切成词，每个词找英文：先查外号表（载物 → zywoo），再看英文意思里有没有选手 ID（设备 → device），都没有就用最常见的意思（生命 → life），拼成 life game → 生命游戏 这样的候选。`py listen.py --review` 逐个确认，确认的进 `phrases.json` |
| `sbtranslator/check.py` | 本地模型（`--check`）。默认傻瓜模式里由它造句（见第 4 节）；wordy 和 plain 模式里是校对。傻瓜模式一次生成 4 个版本（共用同一批查询，不多花请求），交给本机 Ollama 里的 DeepSeek-R1 14b，让它挑最好笑、但还读得通的一个，只准增删「的、了、在」这类虚词。程序会核对：去掉虚词和标点后，句子必须和它挑的那个一模一样，否则就不用它的修改。连不上 Ollama 就退回普通结果，`options()` 的 `checked` 和 `check_error` 告诉悬浮窗 AI 有没有用上、为什么没用上。这里从不自己启动 Ollama：悬浮窗在勾上「AI 校对」时（或翻译时发现它停了）先问人，同意了才调用 `start_ollama()` 在后台（不开窗口）启动它 |
| `sbtranslator/server.py` | HTTP 接口。Python 自带的 `ThreadingHTTPServer` 每来一个请求就开一个线程，交给 `Handler`；`Handler` 只负责把请求转成 `translate()` 调用，再把结果写成 JSON。`memes=` 是玩梗程度，`/modes` 列出能用的值 |
| `sbtranslator/overlay.py` | 悬浮窗。tkinter 只允许主线程碰窗口，所以翻译在工作线程里做，热键在热键线程里等；两者都把结果放进队列 `events`，主线程每 50 毫秒用 `_poll()` 取出来显示。稀有度滑块的值停下 0.6 秒后存进设置；「AI 校对」旁边的「梗：适量 ▾」是玩梗程度，只在 Stupid 模式能点，改了马上存。结果里的梗是蓝色的按钮，菜单里能换梗、不用梗，或者跳到 ⚙ 的「机器人的梗」（这时没有「加进我的词表…」）；梗模型超时写在状态栏，没有模型写在结果下面。exe 第一次打开时在窗口底部问要不要放桌面快捷方式（`_offer_shortcut()`），记住是哪个 exe 问过的，所以每份 exe 最多问一次，新下载的放在别处的 exe 会问要不要把旧快捷方式改成打开它 |
| `sbtranslator/settings_window.py` | ⚙ 设置窗口。上面是稀有度和玩梗程度（都和悬浮窗用同一个变量，一起动），中间是词表（梗和名字、日常意思、缩写、短语、外号，一次看一张，列出内置的和你的，点一行可以改或删）和最后一个按钮「机器人的梗」（`memes_page.py`），下面是导入/导出、恢复默认和放桌面快捷方式。每次改动立刻存盘、下次翻译就用上 |
| `sbtranslator/settings.py` | 你自己的设置，存在 `%LOCALAPPDATA%\SBtranslator\settings.json`（不在程序文件夹里，所以下载新版 exe 不会丢）。只存你的改动：`words` 是你的词条（盖过内置的），`removed` 是你删掉的内置词条，`rarity` 是稀有度，`meme_level` 是玩梗程度，`bot_folder` 是你选的机器人的文件夹，`bot_memes` 是你关掉的梗和你改的说法。读表的地方（`_load_memes()`、`inject.tables()`、`inject.phrases()`、`phrases.nicknames()`）都把内置的表交给 `merged()` 合上你的改动；每次改动后清掉这些缓存，所以不用重启。设置只整个替换、不就地修改，翻译线程读到的永远是完整的一份。`translate()` 每次先看文件的修改时间（`refresh()`），别的程序（比如开着的 HTTP 服务器）改过就重新读。导出不带机器人的文件夹（只在这台电脑上对）。导入认得导出的文件，也认得以前手改的 `stupid_words.json` 和 `memes.json`/`phrases.json`/`nicknames.json` 这种平的表 |
| `sbtranslator/shortcut.py` | 桌面快捷方式。用 Windows 自己的快捷方式对象（IShellLinkW，资源管理器「创建快捷方式」用的就是它），通过 ctypes 按虚函数表的序号调用，不用装包，也不去启动 PowerShell（exe 启动 PowerShell 容易被杀毒软件当成病毒）。桌面位置用 `SHGetFolderPathW` 问 Windows，桌面被 OneDrive 挪走了也找得到。exe 的快捷方式打开 exe 本身；从源码运行时打开 `pythonw overlay.py`，不弹黑窗口 |
| `build_exe.py` | 用 PyInstaller 把 Python、代码和 data 打成一个文件夹再压缩成 zip（不用单文件 exe，因为它容易被杀毒软件误报）。打包时还把梗机器人当时的 `memes.json` 和外号表放进 exe 的 `data/bot`（先找本机机器人的文件夹，没有就从 GitHub 下），没网也有梗可用 |

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
| `data/meme_cues.json` | 程序自带的梗机器人的梗的英文说法：`{"野距": {"from": 意思的指纹, "cues": [{"en": "jungle gap", "confirm": false}], ...}}` | `py -m sbtranslator.meme_cues --into` 写，meme_cues.py 读 |
| `data/esports_names.txt` | `{X}` 认得的战队和选手名（LoL、无畏契约），一行一个 | 你写，meme_pick.py 读 |
| `data/bot/`（只在 exe 里） | 打包时梗机器人的 `memes.json` 和 `nicknames.txt` | build_exe.py 放进去，bot_memes.py 读 |
| `data/words/common_english.txt` | 最常见的 1 万个英文词，按频率排序 | 复合词、往返查词、梗词判断「是不是普通词」都用它 |
| `data/opencc/*.txt` | 简体 → 繁体对照表 | 第 2 部分读 |
| `.cache/chat/*.tsv` | 录下来的弹幕，每行「用户哈希 + 内容」 | learn_chat.py 读写，不进 git |
| `.cache/round_trip.json` | 往返查词的缓存（exe 里放在 %LOCALAPPDATA%\SBtranslator） | 第 6 部分读写，git 不管它 |
| `%LOCALAPPDATA%\SBtranslator\settings.json` | 你在 ⚙ 窗口里的设置：你的词条、删掉的内置词条、稀有度、玩梗程度、机器人的文件夹、关掉的梗和你改的说法（别的系统在 `~/.config/sbtranslator/`，环境变量 `SBTRANSLATOR_SETTINGS` 可以指定别的文件） | settings.py 读写，盖过上面的内置表 |
| `%LOCALAPPDATA%\SBtranslator\meme_cues.json` | 这台电脑上后台写的说法（新梗、改了意思的梗） | meme_cues.py 读写 |
| `%LOCALAPPDATA%\SBtranslator\bot\` | GitHub 上梗机器人的 `memes.json` 和 `nicknames.txt`，最多 6 小时下载一次 | bot_memes.py 读写 |

## 7. 为什么这样设计

- **函数为主，不用类。** 翻译的每一步都是「输入一个词或句子，输出结果」，不需要保存状态，用函数最简单。要保存状态的地方（HTTP 请求、窗口）才用类。
- **门面。** 外部只依赖 `sbtranslator.translate()`，内部怎么改都不影响服务器、悬浮窗和别人的程序。
- **用到才加载，加载一次。** 词表、OpenCC 表、梗词典第一次用到时才读，存在以 `_` 开头的模块变量里，之后直接用。往返查词的结果还存到文件，下次运行也不用再查。
- **每个网络请求都有备用方案。** Google 两个接口轮流试；Bing 的会话过期就重新拿；往返查词或词典查询失败，就跳过这个「额外」步骤，不让整句翻译失败。
- **并行查词。** 每个词要查好几次，所以用 4 个线程同时查。缓存被多个线程共用，用锁保护。
- **优先级明确。** 你在 ⚙ 里的词条 > 手写的梗 > 学到的梗 > 过去式规则 > 稀有度分配。复合词拆出来的部分保持自然意思，因为拆开本身已经够傻了。
- **你的设置和程序的表分开放。** 程序自带的表在 data 文件夹里，跟着新版本更新；你的改动单独存在程序文件夹外面，只记「加了什么、改了什么、删了什么」，所以换新版本既不丢你的改动，也能拿到新版本加的词条。
- **可调的东西集中放。** 想改效果只需要改第 3 部分的设置和 data 文件夹里的文件，不用动逻辑。
- **梗宁可不用，不能用错。** 梗只在英文和它意思、语气都一样时才换；只在某些句子里对的说法要模型确认，模型没答、太慢或者说不是，这句就不用这个梗。骂人的梗只在英文也在骂时用。
- **说法提前写好，模型只管少数。** 每句话都让模型从两百多个梗里挑，又慢又贵，直播弹幕等不起。所以每个梗的英文说法提前写好，翻译时只是查表；只有要确认的说法和「尽量多」才问模型，而且和 Google 同时跑、限时 3 秒、答案记住。
- **翻译器直接读机器人的文件。** 机器人和翻译器是两个仓库，但不用手动同步：翻译器读机器人的 `memes.json`（本机的文件夹，或者 GitHub 上的那份），文件变了就重新读；新梗的说法也在后台自动补。

## 8. 想改效果，改哪里

| 想要 | 改哪里 |
|---|---|
| 整体更傻或更正常（逐词模式） | 悬浮窗 ⚙ 里的稀有度；默认值是 `TARGET_RARITY`（第 3 部分）；运行时也可以加 `--rarity` |
| 加一个梗 | 悬浮窗 ⚙ →「梗和名字」；要随程序一起发布的写进 `data/memes.json`，比如 `"off": "关"` |
| 加蠢词、梗名、缩写 | 悬浮窗 ⚙ →「日常意思」「缩写」；要随程序发布的写进 `data/stupid_words.json` |
| 加选手外号或短语 | 悬浮窗 ⚙ →「外号」「短语」；或 `data/nicknames.json`、`data/phrases.json`，或 `py listen.py --review` 确认弹幕里的候选 |
| 把设置带到别的电脑 | ⚙ →「导出设置…」，那边「导入设置…」 |
| 翻译时多用或少用梗 | 悬浮窗「梗：适量 ▾」或 ⚙ 的「玩梗程度」；命令行 `--memes none\|some\|max`；每档几个梗是 meme_pick.py 的 `PER_SENTENCE`、`PER_CLAUSE` |
| 某个梗用错了、不想要 | 结果里点这个梗 →「改「…」的说法或关掉它…」，或 ⚙ →「机器人的梗」：改说法、关掉 |
| exe 用本机机器人的梗 | ⚙ →「机器人的梗」→「选机器人的文件夹…」 |
| 马上给新梗写说法 | `py -m sbtranslator.meme_cues`（`--show` 列出所有说法，`--all` 全部重写） |
| 换问梗的模型、等它多久 | 环境变量 `SBTRANSLATOR_MEME_MODEL`、`SBTRANSLATOR_MEME_LOCAL_MODEL`；DeepSeek 的 key 在 `DEEPSEEK_API_KEY`；限时是 meme_pick.py 的 `DEADLINE` |
| `{X}` 认得更多战队和选手 | `data/esports_names.txt` 加一行，或者在机器人的外号表里加 |
| 让 AI 造句或挑版本 | 加 `--check`；换模型设环境变量 `SBTRANSLATOR_MODEL`；版本数是 check.py 里的 `VARIANTS` |
| 从直播间学梗 | 直播时运行 `py listen.py douyu 6657`，学到的越积越多 |
| 让爬虫学新的页面 | `data/meme_seeds.txt` 加一行，然后运行 `py learn.py` |
| 单字换成完整的词（次 → 次数） | `STANDALONE_FORMS`（第 3 部分） |
| 补充 Google 词典没有的意思 | `EXTRA_MEANINGS`（第 3 部分） |
| 某些词不要拆开 | `MIN_SPLIT_LETTERS`、`NOT_PARTS`（第 5 部分） |

## 9. 梗机器人

读 B 站找最新游戏梗的梗机器人（以前的 `surf.py` 和 `bilibili.py`）2026 年 11 月搬到了单独的仓库 [MemeLearnerBot](https://github.com/HHCreator/MemeLearnerBot)，两边各自开发，不用再来回合并分支。它的设计说明在那边的 `docs/DESIGN.md`。翻译器直接读它的 `memes.json` 和外号表（`bot_memes.py`，见第 4 节「用上梗机器人的梗」），只读不写；别的程序也可以用它给的入口：`import memelearner`、命令行加 `--json`。

## 10. 测试

```
py -m unittest discover tests
```

`tests/` 里都是离线测试：Google、DeepSeek、Ollama、GitHub 都是假的（`tests/helpers.py` 的 `Offline` 让任何联网都马上失败，要用的测试自己造一个假的），设置文件和机器人的文件夹也是临时的，所以不会动你的设置。`test_bot_memes.py` 测从哪读梗，`test_meme_cues.py` 测写说法、存说法，`test_meme_pick.py` 和 `test_meme_model_answers.py` 测找梗、挑梗、模型确认和超时，`test_meme_settings.py` 测导入导出、⚙ 的梗列表、HTTP 的 `memes=` 和 exe 自带的梗，`test_windows.py` 真的建出悬浮窗和 ⚙ 窗口（不显示）测开关和「机器人的梗」一页，没有 tkinter 或屏幕时跳过（Linux 上用 `xvfb-run`）。GitHub 每次推送和每个 PR 都跑一遍（`.github/workflows/tests.yml`：Windows 上用 Python 3.12，Linux 上用最老支持的 Python 3.8）。
