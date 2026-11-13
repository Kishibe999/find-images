---
name: find-images
description: Find images for slides, reports, documents and web pages - real photos (products, places, events, people), free-to-use stock photos, official product images and icons. Compares many candidates on one numbered contact sheet, downloads the chosen originals, records source and licence, and builds a credits page. Use when the user asks for pictures, images or icons for a deck or document, or when a deck being built is text-heavy with few images. 用于配图、找图、搜图、下载图片或图标，或者 PPT 文字多、图片少时。
---

# find-images: find, screen, download and credit images

The script is `scripts/imgs.py` in this skill's directory. In the commands below, replace `<skill-dir>` with the full path of the directory that contains this SKILL.md (for example `C:/Users/<name>/.claude/skills/find-images`).
Keys come from environment variables or `~/.config/image-search/keys.env` (SERPER_API_KEY, PIXABAY_API_KEY, optional EXA_API_KEY). The script reads them itself: never print them or look for them anywhere else. If a key is missing, the script says which source it skipped; carry on with the other sources and tell the user to set the key up as described in this skill's README.md.
Script messages, sheet labels and credits.md follow the system language (Chinese or English); `FIND_IMAGES_LANG=zh|en` overrides it.
Output goes to `images/` in the current project: `_work/<tag>/` holds candidates and contact sheets, `assets/` the chosen images, `manifest.json` the source record of every image, and `credits.md` the credits page.

## First decide whether the slide needs a found image

| Content | What to do |
|---|---|
| Data, comparisons, trends | Don't search; use native pptx charts or matplotlib |
| Processes, structures, relationships | Don't search; draw with shapes or SVG |
| Concepts, abstract illustration | Try icons (`icons`) first; in Codex you can also generate one with imagegen |
| Specific products, places, people, events, organisations | Use this skill to find real photos |
| Mood images, cover backgrounds | Use this skill with Pixabay or Commons as the source |

## Choosing sources

| Source (`src` / `mode`) | Good for | Query language | Licence |
|---|---|---|---|
| `web` (Serper, i.e. Google Images) | Specific products, news events, people, Chinese-language subjects | Any. For Chinese subjects, adding 官方图 (official image), 高清 (HD) or 新闻图 (news photo) helps | **Unknown rights**: internal presentations and coursework only, with the source cited |
| `commons` (Wikimedia Commons) | Landmarks, cities, architecture, history, science, public figures, organisation logos | **English only, 2–4 words** (Chinese queries return almost nothing) | CC0 is free to use; CC BY / BY-SA need attribution |
| `pixabay` | Mood shots and generic scenes (office, teamwork, city, nature, industry) | Chinese or English | Free to use, attribution optional; **1280px max** |
| `mode: site` (official page) | Official images from a product or company page | Give the page URL | Official site image; cite the source |
| `mode: icons` (Iconify) | Icons from open-source sets (MIT, Apache, …) | **English only**, 1–2 words (`drone`, `battery`). With fewer than 6 results the script also searches each word separately | The default sets are free to use without attribution; `color` is applied to both SVG and PNG |

For a specific subject use `src` `web` or `web,commons`. When the images must be free to use, use `commons,pixabay` and leave out `web`.

## Workflow

### 1. Write the image plan (plan.json, UTF-8)

One item per slide; name each `tag` after the slide number and purpose:

```json
[
 {"tag": "s01_cover", "q": "car carrier ship at port", "q_en": "car carrier ship",
  "src": "commons,pixabay", "orient": "landscape", "min_side": 1600, "n": 12},
 {"tag": "s04_product", "q": "比亚迪 海豹07 官方图", "src": "web", "orient": "landscape", "min_side": 1200, "n": 9},
 {"tag": "s05_official", "mode": "site", "url": "https://www.byd.com/cn/", "n": 9},
 {"tag": "s07_icon", "mode": "icons", "q": "battery", "color": "#1F4E79", "n": 16}
]
```

- `q`: main query, used by `web` and `pixabay`. It can be in Chinese for Chinese subjects, as in `s04_product`. `q_en`: English query used by `commons`; defaults to `q`.
- `orient`: `landscape` / `portrait` / `square` / `any`.
- `min_side`: minimum length of the long side in pixels. Full-screen background 1600, half a slide 1000, small illustration 600. Pixabay's free API serves at most 1280px, so the script lowers the requirement to 1280 for Pixabay. That is enough for a full-screen background on a projector or an ordinary monitor, slightly soft on a 4K screen. If a full-screen image must be very sharp, prefer the Commons candidates.
- `n`: number of candidates on the sheet, 16 at most.

### 2. Search and build contact sheets

```bash
python <skill-dir>/scripts/imgs.py search --plan plan.json --out images
```

Single items work too: `search --tag s04_product --q "..." --src web`, or `site --tag .. --url ..`, `icons --tag .. --q ..`.
If non-ASCII arguments come out garbled in the shell (for example Chinese in Git Bash on Windows), put them in plan.json instead.

Each item produces a numbered contact sheet `images/_work/<tag>/sheet.jpg` and a text list with one line per candidate (size, source domain, licence).
**Searching the same tag again overwrites its candidates and numbers**, so pick from a sheet before you search that tag again.

### 3. Look at the sheet and choose

- Open the sheet image: Read in Claude Code, view_image in Codex. One sheet costs about 1,600 tokens. **Do not open candidates one by one.**
- Check that the subject is right (model, place), the composition leaves room for text, there is no watermark or large block of text, the style matches the rest of the deck, and the resolution is enough.
- If nothing fits, search again. After the first search, re-search at most twice, each time from a different angle rather than with synonyms: a more specific or broader subject, another source, or the other language. If that still fails, fall back to icons or a text-only layout, or tell the user.
- When topic fit and licence conflict: if the request says free-to-use images are *preferred*, search `commons,pixabay` first; if re-searching still finds nothing on topic, use a `web` image and label it "unknown rights" in your report. If the request says the images *must* be free to use or will be published, **never** use `web`; fall back instead.
- Sheet labels show size, licence (Commons shows the exact licence, such as CC BY-SA 4.0) and source domain; the text list shows the same information.

### 4. Download the chosen images

```bash
python <skill-dir>/scripts/imgs.py pick --tag s04_product --ids 6 --out images
```

The script downloads the original image (Commons through its 1920px standard thumbnail; long sides over 2560px are scaled down; webp/avif become jpg/png) and records it in `manifest.json`.
If pick reports a degraded download (`"degraded": true` in the manifest: hotlink protection blocked the original and only a thumbnail came through), choose another candidate.

### 5. Insert the images and build the credits page

- When inserting, go by `file`, `width` and `height` in `manifest.json`; crop to fit the layout and never stretch. Icons come as both PNG and SVG (the `svg` field).
- Run `credits --out images` to write `credits.md` and put its slide-credits section on the last (sources) slide. If it has a note section, pass that on to the user.
- When the whole deck is finished, render it and check screenshots as usual. That is the only time the main agent needs to look at images.

## Saving context: hand three or more images to a subagent

The main agent only writes plan.json and reads the manifest. Viewing sheets, choosing and downloading go to a subagent, so candidate images never enter the main context. Subagent prompt template:

```
Read <skill-dir>/SKILL.md and follow it to find images for the deck in <project path>.
Image plan: <path to plan.json> (tag, purpose and slide context for each item below).
<For each item: what the slide says, where the image goes, landscape or portrait, style>
For each item, look at the sheet once and choose 1 image (at most 1 backup); pick into <project>/images. If nothing fits, re-search with different words, at most two more rounds.
Return for each tag: the chosen id, file path, size, licence class and a one-line reason; list tags with no suitable image and why. Do not return the images themselves.
```

## Licence rules

- **Free to use** (CC0, Pixabay, open-source icons): any use. Crediting CC0 and Pixabay images is a courtesy, not a requirement.
- **Attribution required** (CC BY / BY-SA): credit the author and licence on the sources slide. A modified BY-SA image must be shared under the same licence.
- **Official / unknown rights** (`site`, `web`): internal presentations, coursework and academic talks only, with the source cited. Before anything is published or used commercially, tell the user and swap in free-to-use images.
- Photos of people: public figures in a news context are fine; do not use photos of private individuals as decoration.

## Quotas and limits

- Serper: 2,500 free queries on sign-up. A search for 20 results (when `n` > 6) costs 2 queries, 10 results cost 1. After that you top up, from $50 for 50,000 queries, and top-ups expire after 6 months. The remaining balance is on the serper.dev dashboard.
- Pixabay: 100 requests per minute; images must not be hotlinked (the script downloads them).
- Commons: only standard thumbnail widths (960/1280/1920/3840) can be fetched; search in English.
- Iconify: free, no key. Converting SVG to PNG needs Node.js with sharp. If it is missing the script says so; use another approach, or ask the user to run `npm install -g sharp`.
- Exa: used only when `site` mode cannot find images on the page itself; it uses Exa credits.
