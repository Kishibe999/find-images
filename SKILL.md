---
name: find-images
description: 为 PPT、报告、文档、网页找图：搜真实照片（产品、地点、事件、人物）、可商用图库照片、官网图片和图标，用拼板一次比较多张候选，下载选中的原图，并记录来源和授权、生成图片来源页。用户要配图、找图、搜图、下载图片或图标，或者正在做的 PPT 文字多、图片少时使用。Use for finding, screening and downloading images or icons for slides and documents.
---

# find-images：找图、筛图、下载、记录来源

脚本是本 skill 目录下的 `scripts/imgs.py`。下文命令里的 `<skill目录>` 换成本 SKILL.md 所在目录的完整路径（例如 `C:/Users/<用户名>/.claude/skills/find-images`）。
key 从环境变量或 `~/.config/image-search/keys.env` 读取（SERPER_API_KEY、PIXABAY_API_KEY，可选 EXA_API_KEY），脚本自己读，不要打印，也不要去别处翻找。缺哪个 key，脚本会提示跳过对应来源：照常用其余来源，并告诉用户按本 skill 目录的 README.md 配置。
输出默认写到当前项目的 `images/`：`_work/<tag>/` 放候选和拼板，`assets/` 放选中的图，`manifest.json` 记录每张图的来源，`credits.md` 是来源页。

## 先判断：这页该不该用找来的图

| 内容 | 做法 |
|---|---|
| 数据、对比、趋势 | 不找图，用 pptx 原生图表或 matplotlib 生成 |
| 流程、结构、关系 | 不找图，用形状或 SVG 画 |
| 概念、抽象配图 | 先试图标（`icons`）；Codex 里也可以用 imagegen 生成 |
| 具体的产品、地点、人物、事件、机构 | 用本 skill 找真实图片 |
| 氛围图、封面背景 | 用本 skill，来源选 Pixabay 或 Commons |

## 来源怎么选

| 来源（`src`/`mode`） | 适合 | 查询语言 | 授权 |
|---|---|---|---|
| `web`（Serper，即 Google 图片） | 具体产品、新闻事件、人物、中文语境的东西 | 中文或英文都行，中文加"官方图""高清""新闻图"效果更好 | **版权未知**，只适合内部汇报、课程作业，并注明来源 |
| `commons`（Wikimedia Commons） | 地标、城市、建筑、历史、科学、公众人物、机构 Logo | **必须英文，2–4 个词**（中文几乎搜不到） | CC0 可商用；CC BY / BY-SA 需署名 |
| `pixabay` | 氛围图、通用场景（办公、团队、城市、自然、工业） | 中文可以 | 可商用，不强制署名；**最大 1280px** |
| `mode: site`（官网页面） | 某个产品或公司官网上的官方图 | 给具体页面 URL | 官网图片，注明来源 |
| `mode: icons`（Iconify） | 图标（MIT / Apache 等开源图标集） | **只支持英文**，用 1–2 个词（`drone`、`battery`）；结果不到 6 个时，脚本会自动按单词拆开补充 | 默认图标集都可商用、不需署名；`color` 会写进 SVG 和 PNG |

搜具体对象时 `src` 用 `web` 或 `web,commons`；要可商用的图时用 `commons,pixabay`，别加 `web`。

## 流程

### 1. 写图片需求清单（plan.json，UTF-8）

每页一个条目，`tag` 用"页码_用途"命名：

```json
[
 {"tag": "s01_cover", "q": "新能源汽车 出口 港口 滚装船", "q_en": "car carrier ship",
  "src": "commons,pixabay", "orient": "landscape", "min_side": 1600, "n": 12},
 {"tag": "s04_product", "q": "比亚迪 海豹07 官方图", "src": "web", "orient": "landscape", "min_side": 1200, "n": 9},
 {"tag": "s05_official", "mode": "site", "url": "https://www.byd.com/cn/", "n": 9},
 {"tag": "s07_icon", "mode": "icons", "q": "battery", "color": "#1F4E79", "n": 16}
]
```

- `q`：主查询（`web`、`pixabay` 用）；`q_en`：英文查询（`commons` 用，不写就用 `q`）。
- `orient`：`landscape` / `portrait` / `square` / `any`。
- `min_side`：长边最少多少像素。全屏背景 1600，半屏 1000，小插图 600。Pixabay 的免费接口最大只给 1280px，脚本对它自动把要求降到 1280：投影和普通屏幕上做全屏背景够用，只是在 4K 屏上略软。如果全屏图必须非常清晰，就优先选 Commons 的候选。
- `n`：拼板上放几张，最多 16。

### 2. 搜索，生成拼板

```bash
python <skill目录>/scripts/imgs.py search --plan plan.json --out images
```

也可以单条运行：`search --tag s04_product --q "..." --src web`，或者 `site --tag .. --url ..`、`icons --tag .. --q ..`。
中文参数如果在 shell 里变成乱码，就写进 plan.json 再跑。

每条需求会输出一张带编号的拼板 `images/_work/<tag>/sheet.jpg`，同时输出一行一张的文字清单（尺寸、来源域名、授权）。
**同一个 tag 重新搜索会覆盖候选和编号**，所以看完拼板就选，别隔着重搜。

### 3. 看拼板，选图

- 打开拼板图片：Claude Code 用 Read，Codex 用 view_image。一张拼板约 1,600 token，**不要逐张打开候选图**。
- 选图时看：主体是否正确（型号、地点对不对）、构图能不能给文字留位置、有没有水印或大段文字、风格和整套 PPT 是否一致、清晰度是否够用。
- 都不合适就重搜。初次搜索之后最多再重搜 2 次，每次要换角度，不要只换同义词：换更具体或更宽泛的主体、换来源、中英文互换。还不行就降级：改用图标、改用文字版式，或者跟用户说明。
- 主题贴合和授权冲突时：需求写的是"最好可商用"，就先在 `commons,pixabay` 里找；重搜后仍然没有贴题的，再用 `web` 的图，并在返回结果里标明"版权未知"。需求写的是"必须可商用 / 要对外发布"，就**不用** `web`，宁可降级。
- 拼板标签显示尺寸、授权（Commons 显示具体协议，例如 CC BY-SA 4.0）和来源域名；文字清单里也有同样的信息。

### 4. 下载选中的图

```bash
python <skill目录>/scripts/imgs.py pick --tag s04_product --ids 6 --out images
```

脚本会下载原图（Commons 用 1920px 标准缩略图，长边超过 2560 自动缩小，webp/avif 转成 jpg/png），并写入 `manifest.json`。
输出里出现"只拿到缩略图"，说明原图被防盗链挡住了，换一张。

### 5. 插图、做来源页

- 插图时以 `manifest.json` 里的 `file`、`width`、`height` 为准，按版式裁切，不要拉伸变形。图标同时有 PNG 和 SVG（`svg` 字段）。
- 跑 `credits --out images` 生成 `credits.md`，把"幻灯片署名"那段放到最后的来源页；有"注意"段落时要转告用户。
- 做完整套 PPT 后照常渲染截图检查，这是主 Agent 唯一需要看图的时候。

## 控制上下文：三张图以上交给子代理

主 Agent 只负责写 plan.json 和读 manifest。看拼板、选图、下载交给子代理，候选图就不会进入主上下文。子代理的 prompt 模板：

```
读 <skill目录>/SKILL.md，按流程为 <项目路径> 的 PPT 配图。
需求清单：<plan.json 路径>（每条的 tag、用途、页面上下文见下方）。
<逐条说明这页讲什么、图放在哪、要横图还是竖图、风格>
每条看一次拼板后选 1 张（备选最多 1 张），pick 到 <项目>/images；不合适就换词重搜，最多两轮。
返回：每个 tag 选了哪张、文件路径、尺寸、授权等级、一句理由；没找到合适图的 tag 和原因。不要返回图片本身。
```

## 授权规则

- **可商用**（CC0、Pixabay、开源图标）：怎么用都行。CC0 和 Pixabay 署名属于礼貌，不是义务。
- **需署名**（CC BY / BY-SA）：来源页写上作者和协议。BY-SA 的图修改后，修改版要用同样的协议。
- **官网 / 版权未知**（`site`、`web`）：只用于内部汇报、课程作业、学术展示，注明来源；要对外发布或商用时，先告诉用户，并换成可商用的图。
- 人物照片：公众人物在新闻语境下可以用；不要用普通人的照片做装饰。

## 额度与限制

- Serper：注册送 2,500 次。一次搜索要 20 条结果扣 2 次（`n` > 6 时），要 10 条扣 1 次。用完要充值，最低 $50 / 5 万次，6 个月过期。剩余额度在 serper.dev 后台查看。
- Pixabay：每分钟 100 次，不能直接引用它的图片链接（脚本会下载到本地）。
- Commons：只能取标准宽度的缩略图（960/1280/1920/3840），搜索要用英文。
- Iconify：免费，不需要 key。SVG 转 PNG 要用 Node.js 的 sharp；没装时脚本会提示，这时改用其他做法，或请用户执行 `npm install -g sharp`。
- Exa：只在 `site` 模式本地抓不到图时才用，扣 Exa 额度。
