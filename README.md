# find-images

**English** | [简体中文](README.zh-CN.md)

An agent skill for Claude Code and Codex that finds images for slides, reports and documents. It searches several image sources at once, puts the candidates on one numbered contact sheet for the agent to choose from, downloads the chosen originals, and records the source and licence of every image.

Script messages, sheet labels and the generated credits page follow your system language (English or Chinese). A Chinese version of the agent instructions is in [SKILL.zh-CN.md](SKILL.zh-CN.md).

## The problem

- Built-in search tools such as Claude Code's WebSearch return text only, no images.
- When an agent scrapes images from web pages on its own, it often ends up with watermarked stock previews, tiny thumbnails or hotlink-blocked files, and opening candidates one by one to check them fills up the context window.
- Once an image is downloaded, nobody remembers where it came from or under what licence, and the credits slide can't be written afterwards.

## How it works

```
plan.json (what each slide needs)
   │
   ▼  search: query several sources; drop watermarked stock sites, undersized
   │          and wrongly oriented images; remove near-duplicates
_work/<tag>/sheet.jpg (up to 16 candidates, labelled with number, size, licence, source site)
   │
   ▼  the agent looks at this one sheet and picks numbers
pick: download originals into assets/, record them in manifest.json (source page, author, licence)
   │
   ▼
credits: write credits.md, ready for the deck's sources slide
```

- One sheet costs about 1,600 tokens, so 16 candidates take the context of a single image.
- For three or more images, SKILL.md tells the main agent to hand sheet viewing, choosing and downloading to a subagent; the main agent only reads the text in `manifest.json`.
- Every image gets one of four licence classes: free to use, attribution required, official site image, unknown rights.

## Sources

| Source | Good for | Licence | Key needed | Cost |
|---|---|---|---|---|
| Google Images (via the Serper API) | Specific products, news events, people, Chinese-language subjects | Unknown rights | Yes | 2,500 free queries on sign-up, then paid top-ups |
| Wikimedia Commons | Landmarks, architecture, history, science, organisations | CC0, CC BY, CC BY-SA, etc.; the exact licence of each image is recorded | No | Free |
| Pixabay | Mood shots and generic scenes (office, city, nature) | Pixabay Content License: free to use, attribution optional | Yes | Free |
| Official web pages (`site` mode) | A product's or company's own images | Owned by the site | No (Exa can fill in when a page can't be parsed) | Free |
| Iconify icons (`icons` mode) | Illustrating concepts | Open-source icon sets (MIT, Apache 2.0, etc.) | No | Free |

Charts and diagrams are out of scope: SKILL.md tells the agent to draw those itself.

## Installation

### 1. Requirements

- Python 3.9 or later: `pip install -r requirements.txt` (requests, Pillow, beautifulsoup4, lxml)
- Icon mode also needs Node.js and sharp: `npm install -g sharp`. Skip this if you don't need icons.

### 2. Put it in your skills directory

Claude Code:

```bash
git clone https://github.com/Kishibe999/find-images.git ~/.claude/skills/find-images
```

Codex reads `~/.codex/skills/` (newer versions also read `~/.agents/skills/`). If you use both, clone once and link the other location, so there is only one copy to update:

```powershell
# Windows (PowerShell)
New-Item -ItemType Junction -Path "$HOME\.codex\skills\find-images" -Target "$HOME\.claude\skills\find-images"
```

```bash
# macOS / Linux
ln -s ~/.claude/skills/find-images ~/.codex/skills/find-images
```

Start a new session afterwards; `find-images` should appear in the agent's skill list.

### 3. Set up keys

Copy [keys.env.example](keys.env.example) to `~/.config/image-search/keys.env` and fill in your keys, or set environment variables with the same names. Keep keys out of the skill directory so they never get committed.

If a key is missing, the script skips that source and uses the others.

**Serper (Google Images)**
- Sign up at [serper.dev](https://serper.dev) and copy the key from the API Key page of the dashboard. You get 2,500 free queries on sign-up; no card needed.
- Cost per search: 10 results cost 1 query, 20 results cost 2. The script asks for 20 when the sheet size `n` is above 6, so the free 2,500 queries cover 1,250 to 2,500 searches.
- After that you top up; there is no monthly free allowance. Tiers: $50 for 50,000 queries ($1 per 1,000), $375 for 500,000, $1,250 for 2.5 million. Top-ups expire after 6 months.
- Payment goes through Paddle: Visa, Mastercard, American Express, Discover or PayPal.

**Pixabay**
- Create an account at [pixabay.com](https://pixabay.com), log in and open [pixabay.com/api/docs](https://pixabay.com/api/docs/); your key is shown in the `key` row of the parameter table.
- Free, up to 100 requests per minute.
- The free API serves images up to 1280px; larger sizes require applying to Pixabay for full API access.
- Pixabay requires images to be downloaded rather than hotlinked. The script downloads them anyway.

**Exa (optional)**
- Only used in `site` mode when the script cannot find images on a page by itself; Exa then extracts the page's image links.
- Sign up at [dashboard.exa.ai](https://dashboard.exa.ai) and create a key on the API Keys page. There is $10 of free credit per month; this use costs $1 per 1,000 pages.

## Usage

Just ask in Claude Code or Codex, for example "find images for slides 3, 5 and 8 of this deck" or "find a landscape photo of a car carrier ship at port, free to use". The agent follows SKILL.md: it writes the image plan, searches, reviews the sheets, downloads the picks and builds the credits page.

You can also run the script by hand:

```bash
python scripts/imgs.py search --plan examples/plan.json --out images    # batch search from a plan
python scripts/imgs.py search --tag s03 --q-en "car carrier ship" --src commons,pixabay
python scripts/imgs.py site   --tag s05 --url https://www.example.com/product
python scripts/imgs.py icons  --tag s07 --q battery --color "#1F4E79"
python scripts/imgs.py pick   --tag s03 --ids 2,5                       # download #2 and #5 from the sheet
python scripts/imgs.py credits                                          # write credits.md
```

See [examples/plan.json](examples/plan.json) and [SKILL.md](SKILL.md) for the plan format. If non-ASCII arguments get garbled in your shell (Chinese in Git Bash on Windows, for example), put the queries in plan.json (UTF-8) instead.

Output layout:

```
images/
├── _work/<tag>/        candidates, sheet.jpg, candidates.json
├── assets/             chosen images (<tag>_<id>.jpg / .png; icons also .svg)
├── manifest.json       file path, size, source page, author and licence of each image
└── credits.md          credits page
```

## About licences

- Licence classes come from the metadata each source provides. For Commons, the licence on the file page is authoritative.
- Free to use: CC0, Pixabay, open-source icons. Any use is fine.
- Attribution required: CC BY and CC BY-SA. Credit the author and licence on the sources slide; a modified CC BY-SA image must be shared under the same licence.
- Official site images and images with unknown rights are for internal presentations, coursework and academic talks only, with the source cited. Replace them with free-to-use images or get permission before publishing or commercial use.
- The script records sources; it does not give legal advice. Double-check anything that matters.

## Why these sources

As of November 2026:

- The Bing Image Search API was retired in August 2025. The Google Custom Search JSON API no longer accepts new customers and shuts down on 1 January 2027. Serper is one of the few ways to get Google Images results that works right after sign-up without a card.
- The Brave Search API can search images, but even its free tier requires a credit card, and it costs $5 per 1,000 queries, so it is not used.
- Pexels has paused issuing new API keys, and the Openverse API timed out (HTTP 504) in testing.
- Wikimedia Commons only serves standard thumbnail widths (960, 1280, 1920, 3840px); the script downloads the 1920px one.

## Known limitations

- Commons and Iconify only understand English queries; 2 to 4 English words work best on Commons.
- Pixabay's free API tops out at 1280px, which looks slightly soft as a full-screen background on a 4K screen.
- Some sites block hotlinking. When the original can't be downloaded, pick falls back to the thumbnail and tells you to choose another image.
- Requests to Wikimedia use a generic User-Agent. If you get rate-limited, set the environment variable `FIND_IMAGES_UA` to a User-Agent that includes your own contact details.
- Chinese text on sheet labels needs a CJK font (bundled with Windows and macOS; on Linux install Noto Sans CJK or WenQuanYi). `FIND_IMAGES_FONT` can point to a font file.
- The output language is detected from the system UI language; set `FIND_IMAGES_LANG=en` or `zh` if it guesses wrong.

## License

The code is under the [MIT](LICENSE) licence. Images found with it belong to their authors; use them under the licence recorded in `manifest.json`.
