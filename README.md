# find-images

给 Claude Code、Codex 等 AI Agent 用的找图 skill，用来给 PPT、报告和文档配图。它同时搜几个图源，把候选图拼成一张带编号的拼板让 Agent 挑选，然后下载选中的原图，并记录每张图的来源和授权。

An agent skill for Claude Code and Codex that finds images for slides and documents. It searches Google Images (via Serper), Wikimedia Commons, Pixabay, a product's own web page and Iconify, shows the candidates on one numbered contact sheet, downloads the picks and records source and licence for each. Instructions and script output are in Chinese.

## 解决什么问题

- Claude Code 的 WebSearch 等内置搜索工具只返回文字，搜不到图片。
- 让 Agent 自己去网页上扒图，常拿到带水印的图库预览图、小缩略图，或者被防盗链挡住；逐张打开候选图来检查，每张图都要占用上下文。
- 图下载下来以后不知道出处和授权，最后做来源页时补不回来。

## 工作方式

```
plan.json（每页要什么图）
   │
   ▼  search：几个图源一起搜；去掉水印图库、尺寸不够、方向不对的图，再去重
_work/<tag>/sheet.jpg（最多 16 张候选，标上编号、尺寸、授权、来源网站）
   │
   ▼  Agent 看这一张拼板，选出编号
pick：下载原图到 assets/，写入 manifest.json（来源页、作者、协议）
   │
   ▼
credits：生成 credits.md，直接放进 PPT 的来源页
```

- 一张拼板约 1,600 token，16 张候选只占一张图的上下文。
- 配三张图以上时，SKILL.md 让主 Agent 把看拼板、选图、下载交给子代理，主 Agent 只读 `manifest.json` 里的文字。
- 每张图分为四个授权等级：可商用、需署名、官网图片、版权未知。

## 图源

| 图源 | 适合找什么 | 授权 | 要不要 key | 费用 |
|---|---|---|---|---|
| Google 图片（通过 Serper API） | 具体产品、新闻事件、人物、中文内容 | 版权未知 | 要 | 注册送 2,500 次，用完再充值 |
| Wikimedia Commons | 地标、建筑、历史、科学、机构 | CC0、CC BY、CC BY-SA 等，脚本记下每张图的具体协议 | 不要 | 免费 |
| Pixabay | 氛围图、办公、城市、自然等通用场景 | Pixabay Content License，可商用，不强制署名 | 要 | 免费 |
| 官网页面（`site` 模式） | 某个产品或公司的官方图 | 版权归官网 | 不要（解析不到图时可用 Exa 补充） | 免费 |
| Iconify 图标（`icons` 模式） | 概念配图 | 开源图标集（MIT、Apache 2.0 等） | 不要 | 免费 |

数据图表、流程图不在这个 skill 的范围里，SKILL.md 会让 Agent 自己画。

## 安装

### 1. 依赖

- Python 3.9 或更新版本：`pip install -r requirements.txt`（requests、Pillow、beautifulsoup4、lxml）
- 图标模式还需要 Node.js 和 sharp：`npm install -g sharp`。不用图标的话可以不装。

### 2. 放进 skill 目录

Claude Code：

```bash
git clone https://github.com/Kishibe999/find-images.git ~/.claude/skills/find-images
```

Codex 读取 `~/.codex/skills/`（新版也读 `~/.agents/skills/`）。两个都用时只克隆一份，另一边建一个目录链接，以后改一处就行：

```powershell
# Windows（PowerShell）
New-Item -ItemType Junction -Path "$HOME\.codex\skills\find-images" -Target "$HOME\.claude\skills\find-images"
```

```bash
# macOS / Linux
ln -s ~/.claude/skills/find-images ~/.codex/skills/find-images
```

装好后重开会话，Agent 的 skill 列表里应该能看到 `find-images`。

### 3. 配置 key

把 [keys.env.example](keys.env.example) 复制到 `~/.config/image-search/keys.env`，填上 key。也可以改用同名的环境变量。不要把 key 放进 skill 目录，免得被提交到 git。

缺哪个 key，脚本就跳过对应图源，其他图源照常用。

**Serper（Google 图片）**
- 注册：在 [serper.dev](https://serper.dev) 注册账号，登录后在后台的 API Key 页面复制 key。注册送 2,500 次查询，不用绑卡。
- 扣费：每次图片搜索，要 10 条结果扣 1 次，要 20 条扣 2 次。脚本在拼板张数 `n` 大于 6 时要 20 条。所以送的 2,500 次额度能搜 1,250 到 2,500 次。
- 用完以后要充值，没有每月免费额度。档位：$50 买 5 万次（每千次 $1），$375 买 50 万次，$1,250 买 250 万次。充值的额度 6 个月后过期。
- 付款经 Paddle，支持 Visa、Mastercard、American Express、Discover 和 PayPal。

**Pixabay**
- 注册：在 [pixabay.com](https://pixabay.com) 注册账号，登录后打开 [pixabay.com/api/docs](https://pixabay.com/api/docs/)，参数表里 `key` 那一行显示的就是你的 key。
- 免费，每分钟最多 100 次请求。
- 免费接口给的图最大 1280px，更大的尺寸要向 Pixabay 申请完整 API 权限。
- Pixabay 要求把图下载到本地使用，不能直接引用它的图片链接。脚本本来就会下载。

**Exa（可选）**
- 只在 `site` 模式本地解析不到页面图片时用到，用来提取页面上的图片链接。
- 注册：在 [dashboard.exa.ai](https://dashboard.exa.ai) 注册，在 API Keys 页面创建 key。每月有 $10 免费额度，这个用途按每千页 $1 计费。

## 使用

在 Claude Code 或 Codex 里直接提需求就行，比如"给这份 PPT 第 3、5、8 页配图""找一张港口滚装船的横图，要可商用"。Agent 会按 SKILL.md 写需求清单、搜索、看拼板、下载、生成来源页。

也可以手动运行脚本：

```bash
python scripts/imgs.py search --plan examples/plan.json --out images    # 按清单批量搜索
python scripts/imgs.py search --tag s03 --q-en "car carrier ship" --q "滚装船" --src commons,pixabay
python scripts/imgs.py site   --tag s05 --url https://www.example.com/product
python scripts/imgs.py icons  --tag s07 --q battery --color "#1F4E79"
python scripts/imgs.py pick   --tag s03 --ids 2,5                       # 下载拼板上的 2 号和 5 号
python scripts/imgs.py credits                                          # 生成 credits.md
```

需求清单的写法见 [examples/plan.json](examples/plan.json) 和 [SKILL.md](SKILL.md)。在 Windows 的 Git Bash 里，中文命令行参数可能会变成乱码，这时把查询写进 plan.json（UTF-8）再运行。

输出目录：

```
images/
├── _work/<tag>/        候选图和拼板 sheet.jpg、candidates.json
├── assets/             选中的图（<tag>_<编号>.jpg / .png，图标另有 .svg）
├── manifest.json       每张图的文件路径、尺寸、来源页、作者、协议
└── credits.md          图片来源页
```

## 授权说明

- 授权等级是按图源提供的元数据判断的。Commons 以文件页上标注的协议为准。
- 可商用：CC0、Pixabay、开源图标，怎么用都行。
- 需署名：CC BY、CC BY-SA，来源页要写上作者和协议；CC BY-SA 的图改过以后，改后的版本也要用同样的协议。
- 官网图片和版权未知的图，只适合内部汇报、课程作业、学术展示，并要注明来源。对外发布或商用前，请换成可商用的图或取得授权。
- 脚本只负责记录来源，不做法律判断，重要场合请自己再核实一遍。

## 为什么选这几个图源

2026 年 11 月调研时的情况：

- Bing Image Search API 已在 2025 年 8 月停用。Google Custom Search JSON API 不再接受新用户，2027 年 1 月 1 日停止服务。要拿到 Google 图片结果，Serper 是注册就能用、不用绑卡的方案之一。
- Brave Search API 也能搜图，但免费档也要绑信用卡，按每千次 $5 计费，所以没有用。
- Pexels 暂停发放新的 API key；Openverse 测试时接口超时（HTTP 504）。
- Wikimedia Commons 只能取标准宽度的缩略图（960、1280、1920、3840px），脚本下载时用 1920px。

## 已知限制

- Commons 和 Iconify 只认英文查询；Commons 用 2 到 4 个英文词效果最好。
- Pixabay 免费接口最大 1280px，在 4K 屏上做全屏背景会略软。
- 部分网站有防盗链，下载原图失败时会退回缩略图，脚本会提示换一张。
- 访问 Wikimedia 时用通用的 User-Agent。如果被限流，可以把环境变量 `FIND_IMAGES_UA` 设成带你自己联系方式的 User-Agent。
- 拼板上的中文标签需要系统里有中文字体（Windows、macOS 自带；Linux 要装 Noto Sans CJK 或文泉驿），也可以用 `FIND_IMAGES_FONT` 指定字体文件。

## License

代码使用 [MIT](LICENSE) 协议。搜到的图片版权归各自作者，请按 `manifest.json` 里记录的协议使用。
