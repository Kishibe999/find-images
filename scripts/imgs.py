#!/usr/bin/env python3
"""find-images: search candidate images, build numbered contact sheets, download picks
with source/licence records. Keys come from env vars or ~/.config/image-search/keys.env.

  python imgs.py search  --tag s03 --q "比亚迪 海豹 官方图" [--q-en "..."] [--src web,commons,pixabay]
                         [--orient landscape|portrait|square|any] [--min-side 1000] [--n 12]
  python imgs.py search  --plan plan.json          # batch; items may set "mode": search|icons|site
  python imgs.py site    --tag s04 --url https://www.example.com/product
  python imgs.py icons   --tag s05 --q "battery" [--color "#1F4E79"]
  python imgs.py pick    --tag s03 --ids 3,7
  python imgs.py credits
All commands take --out DIR (default ./images).
Icons need Node.js with sharp installed (npm install -g sharp).
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
# Wikimedia asks API clients for a descriptive User-Agent; set FIND_IMAGES_UA to add your own contact.
WIKI_UA = os.environ.get("FIND_IMAGES_UA") or "find-images/1.0 (agent skill; low-volume)"
SHEET_SIDE = 1092          # ~1.6K image tokens for a whole sheet
MAX_SIDE = 2560            # downscale downloads beyond this (keeps decks small)

# Stock sites whose previews carry watermarks, plus social sites with unclear rights.
BLOCKED = (
    "dreamstime.com", "shutterstock.com", "istockphoto.com", "gettyimages", "alamy.com",
    "123rf.com", "depositphotos.com", "stock.adobe.com", "canstockphoto", "bigstockphoto",
    "vcg.com", "ooopic.com", "58pic.com", "ibaotu.com", "699pic.com", "nipic.com",
    "huitu.com", "vjshi.com", "quanjing.com", "veer.com", "stock.tuchong.com", "pngtree.com",
    "lovepik.com", "pond5.com", "storyblocks.com", "freepik.com", "vecteezy.com",
    "instagram.com", "tiktok.com", "douyin.com", "facebook.com", "fbsbx.com", "pinimg.com",
    "pinterest.", "xiaohongshu.com", "xhscdn.com",
)
ICON_PREFIXES = "material-symbols,mdi,tabler,lucide,ph,fluent,carbon,ri,heroicons"
LIC_LABEL = {"free": "可商用", "attribution": "需署名", "official": "官网", "unknown": "版权?", "check": "需核实"}


# ---------------------------------------------------------------- utilities
def load_keys():
    keys = {}
    p = Path.home() / ".config" / "image-search" / "keys.env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
    for k in ("SERPER_API_KEY", "PIXABAY_API_KEY", "EXA_API_KEY"):
        if os.environ.get(k):
            keys[k] = os.environ[k]
    return keys


KEYS = load_keys()
S = requests.Session()
# Retry GETs on dropped connections and 5xx; POSTs (Serper, Exa) are billed, so they are not retried.
_retry = Retry(total=2, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504),
               allowed_methods=frozenset({"GET"}), raise_on_status=False)
S.mount("https://", HTTPAdapter(max_retries=_retry))
S.mount("http://", HTTPAdapter(max_retries=_retry))


def has_cjk(s):
    return bool(re.search(r"[\u3400-\u9fff]", s or ""))


def domain_of(u):
    return urlparse(u or "").netloc.lower().removeprefix("www.")


def blocked(dom):
    return any(b in dom for b in BLOCKED)


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def orient_ok(w, h, orient):
    if not w or not h or orient == "any":
        return True
    r = w / h
    return {"landscape": r >= 1.2, "portrait": r <= 0.85, "square": 0.85 < r < 1.2}.get(orient, True)


CJK_FONTS = (
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",                         # Windows
    "/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",  # macOS
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",                            # Debian/Ubuntu
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",                                 # Arch/Fedora
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)


def font(size):
    for f in (os.environ.get("FIND_IMAGES_FONT"), *CJK_FONTS):
        if f and os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)   # Pillow >= 10.1; no CJK glyphs
    except TypeError:
        return ImageFont.load_default()


def get_image(url, referer=None, wiki=False, timeout=20):
    h = {"User-Agent": WIKI_UA if wiki else BROWSER_UA}
    if referer:
        h["Referer"] = referer
    r = S.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content))
    im.load()
    return im, r.content


def ahash(im):
    if im.mode in ("RGBA", "LA", "P"):
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im.convert("RGBA"))
    g = im.convert("L").resize((8, 8))
    px = list(g.tobytes())
    avg = sum(px) / 64
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def workdir(out, tag):
    d = Path(out) / "_work" / tag
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- providers
def p_web(q, n):
    key = KEYS.get("SERPER_API_KEY")
    if not key:
        print("  [web] 跳过：没有 SERPER_API_KEY")
        return []
    body = {"q": q, "num": 20 if n > 6 else 10}   # 20 results = 2 credits, 10 = 1 credit
    if has_cjk(q):
        body.update(gl="cn", hl="zh-cn")
    r = S.post("https://google.serper.dev/images", headers={"X-API-KEY": key}, json=body, timeout=30)
    d = r.json()
    print(f"  [web] Serper 返回 {len(d.get('images', []))} 条，扣 {d.get('credits')} 次额度")
    out = []
    for x in d.get("images", []):
        page = x.get("link", "")
        out.append(dict(provider="web", title=x.get("title", ""), width=x.get("imageWidth") or 0,
                        height=x.get("imageHeight") or 0, thumb=x.get("thumbnailUrl"),
                        urls=[x.get("imageUrl")], page=page,
                        domain=domain_of(x.get("imageUrl")) or x.get("domain", ""),
                        page_domain=x.get("domain") or domain_of(page),
                        license="unknown", license_class="unknown", author=""))
    return out


def commons_class(lic):
    l = (lic or "").lower()
    if l.startswith("cc0") or "public domain" in l or l.startswith("pd"):
        return "free"
    if l.startswith("cc by"):
        return "attribution"
    return "check"


def p_commons(q, n):
    r = S.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": WIKI_UA}, timeout=30, params={
        "action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6,
        "gsrlimit": min(max(n * 3, 20), 50), "prop": "imageinfo", "iiprop": "url|size|extmetadata",
        "iiurlwidth": 360, "format": "json"})
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    print(f"  [commons] 返回 {len(pages)} 条" + ("（Commons 以英文为主，中文查询结果通常很少）" if has_cjk(q) and len(pages) < 5 else ""))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii.get("thumburl"):
            continue
        em = ii.get("extmetadata", {})
        lic = em.get("LicenseShortName", {}).get("value", "")
        w, h, orig = ii.get("width", 0), ii.get("height", 0), ii.get("url", "")
        # Commons only renders standard thumbnail widths (e.g. 960/1280/1920/3840; 2560 -> HTTP 400)
        urls = []
        if w > 1920 or not re.search(r"\.(jpe?g|png|webp)(\?|$)", orig, re.I):
            std = next((s for s in (1920, 1280, 960) if s <= w), None)
            if std:
                urls.append(re.sub(r"/\d+px-", f"/{std}px-", ii["thumburl"], count=1))
        urls.append(orig)
        out.append(dict(provider="commons", title=p.get("title", "").removeprefix("File:"), width=w, height=h,
                        thumb=ii["thumburl"], urls=urls, page=ii.get("descriptionurl", ""),
                        domain="commons.wikimedia.org", page_domain="commons.wikimedia.org",
                        license=lic, license_class=commons_class(lic),
                        author=strip_html(em.get("Artist", {}).get("value", ""))[:80]))
    return out


def p_pixabay(q, n, orient):
    key = KEYS.get("PIXABAY_API_KEY")
    if not key:
        print("  [pixabay] 跳过：没有 PIXABAY_API_KEY")
        return []
    o = {"landscape": "horizontal", "portrait": "vertical"}.get(orient, "all")
    r = S.get("https://pixabay.com/api/", timeout=30, params={
        "key": key, "q": q[:100], "lang": "zh" if has_cjk(q) else "en", "image_type": "photo",
        "orientation": o, "per_page": min(max(n * 2, 10), 50), "safesearch": "true"})
    d = r.json()
    print(f"  [pixabay] 命中 {d.get('totalHits')}，取 {len(d.get('hits', []))} 条")
    out = []
    for x in d.get("hits", []):
        w, h = x["imageWidth"], x["imageHeight"]
        s = 1280 / max(w, h) if max(w, h) > 1280 else 1   # API serves at most 1280px
        out.append(dict(provider="pixabay", title=x.get("tags", ""), width=round(w * s), height=round(h * s),
                        thumb=x["webformatURL"].replace("_640", "_340"), urls=[x["largeImageURL"]],
                        page=x.get("pageURL", ""), domain="pixabay.com", page_domain="pixabay.com",
                        license="Pixabay Content License", license_class="free", author=x.get("user", "")))
    return out


# ---------------------------------------------------------------- sheet + candidates
def fetch_thumbs(cands, workers=8):
    def one(c):
        try:
            if c.get("local"):
                im = Image.open(c["local"])
                im.load()
                return im
            im, _ = get_image(c["thumb"], referer=c.get("page"), wiki=c["provider"] == "commons", timeout=15)
            return im
        except Exception:
            return None
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, cands))


def build_sheet(cands, imgs, path):
    n = len(cands)
    cols = 2 if n <= 4 else 3 if n <= 9 else 4
    rows = (n + cols - 1) // cols
    cell = SHEET_SIDE // cols
    strip = min(30, max(22, cell // 10))
    sheet = Image.new("RGB", (cell * cols, cell * rows), (238, 238, 238))
    d = ImageDraw.Draw(sheet)
    f_small, f_big = font(strip - 7), font(int(strip * 1.2))
    for i, (c, im) in enumerate(zip(cands, imgs)):
        x, y = (i % cols) * cell, (i // cols) * cell
        if im is not None:
            im = im.copy()
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                im = Image.alpha_composite(bg, im)
            im = im.convert("RGB")
            box_w, box_h = cell - 6, cell - strip - 6
            s = min(box_w / im.width, box_h / im.height)   # fit (also upscales small thumbs)
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
            sheet.paste(im, (x + (cell - im.width) // 2, y + 3 + (box_h - im.height) // 2))
        prov = c["provider"]
        if prov == "commons":
            tail = f"{c['license'] or '授权需核实'} Commons"      # e.g. "CC BY-SA 4.0" stays visible
        elif prov == "pixabay":
            tail = "可商用 Pixabay"
        elif prov == "iconify":
            tail = f"{c['license']} {c['title'].split(':')[0]}"
        else:
            tail = f"{LIC_LABEL.get(c['license_class'], '')} {c.get('page_domain') or c.get('domain') or ''}"
        label = f"{c['width']}x{c['height']} {tail}"
        while label and d.textlength(label, font=f_small) > cell - 12:
            label = label[:-1]
        d.rectangle([x + 2, y + cell - strip - 2, x + cell - 2, y + cell - 2], fill=(20, 20, 20))
        d.text((x + 6, y + cell - strip), label, fill="white", font=f_small)
        d.rectangle([x + 2, y + 2, x + 2 + int(strip * 1.6), y + 2 + int(strip * 1.45)], fill=(200, 30, 30))
        d.text((x + 6, y + 2), str(c["id"]), fill="white", font=f_big)
    sheet.save(path, quality=85)


def finalize(cands, n, out, tag, query):
    """Fetch thumbs, drop failures and near-duplicates, number, save sheet + json, print summary."""
    imgs = fetch_thumbs(cands)
    kept, kimgs, hashes = [], [], []
    for c, im in zip(cands, imgs):
        if im is None:
            continue
        if c["provider"] != "iconify":  # icon variants (rounded/sharp) look alike but are all valid
            h = ahash(im)
            if any(bin(h ^ o).count("1") <= 5 for o in hashes):
                continue
            hashes.append(h)
        kept.append(c)
        kimgs.append(im)
        if len(kept) >= n:
            break
    wd = workdir(out, tag)
    for i, c in enumerate(kept, 1):
        c["id"] = i
        c["query"] = query
    (wd / "candidates.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    if not kept:
        print(f"[{tag}] 没有可用候选。换个查询词（更具体 / 换英文 / 换来源）再试。")
        return
    sheet = wd / "sheet.jpg"
    build_sheet(kept, kimgs, sheet)
    print(f"[{tag}] {len(kept)} 个候选 → 拼板 {sheet.resolve()}")
    for c in kept:
        src = c.get("page_domain") or c["provider"]
        lic = LIC_LABEL.get(c["license_class"], "")
        if c["provider"] in ("commons", "iconify") and c.get("license"):
            lic += f" {c['license']}"
        print(f"  #{c['id']:>2} {c['width']}x{c['height']} {c['provider']}/{src} [{lic}] {c['title'][:36]}")


def interleave(lists):
    out, i = [], 0
    while any(i < len(l) for l in lists):
        for l in lists:
            if i < len(l):
                out.append(l[i])
        i += 1
    return out


def cmd_search(item, out):
    tag, q = item["tag"], item.get("q") or item.get("q_en")
    q_en = item.get("q_en") or q
    src =[s.strip() for s in item.get("src", "web,commons,pixabay").split(",") if s.strip()]
    orient, n = item.get("orient", "any"), int(item.get("n", 12))
    min_side = int(item.get("min_side", 1000))
    print(f"[{tag}] 搜索：{q}" + (f" / {q_en}" if q_en != q else "") + f"  来源={','.join(src)}")
    lists = []
    for s in src:
        try:
            if s == "web":
                lists.append(p_web(q, n))
            elif s == "commons":
                lists.append(p_commons(q_en, n))
            elif s == "pixabay":
                lists.append(p_pixabay(q if has_cjk(q) else q_en, n, orient))
        except Exception as e:
            print(f"  [{s}] 出错：{e!r:.120}")
    seen, cands, dropped = set(), [], {"blocked": 0, "small": 0, "orient": 0}
    for c in interleave(lists):
        u = (c["urls"] or [""])[0]
        if not u or u in seen or not c.get("thumb"):
            continue
        seen.add(u)
        if c["provider"] == "web" and (blocked(c["domain"]) or blocked(c.get("page_domain", ""))
                                       or u.lower().split("?")[0].endswith((".svg", ".gif"))):
            dropped["blocked"] += 1
            continue
        # Pixabay's free API tops out at 1280px, so cap the requirement for it
        need = min(min_side, 1280) if c["provider"] == "pixabay" else min_side
        if max(c["width"], c["height"]) < need:
            dropped["small"] += 1
            continue
        if not orient_ok(c["width"], c["height"], orient):
            dropped["orient"] += 1
            continue
        cands.append(c)
    print(f"  过滤：水印图库/社交平台 {dropped['blocked']}，尺寸不足 {dropped['small']}，方向不符 {dropped['orient']}")
    finalize(cands[: int(n * 1.6)], n, out, tag, q)


# ---------------------------------------------------------------- site images
def page_image_urls(url):
    from bs4 import BeautifulSoup
    r = S.get(url, headers={"User-Agent": BROWSER_UA}, timeout=30)
    r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
    soup = BeautifulSoup(r.text, "lxml")
    found = []
    for sel, attr in (('meta[property="og:image"]', "content"), ('meta[name="twitter:image"]', "content"),
                      ('link[rel="image_src"]', "href")):
        for t in soup.select(sel):
            found.append(str(t.get(attr) or ""))
    for t in soup.find_all(["img", "source"]):
        srcset = str(t.get("srcset") or t.get("data-srcset") or "")
        if srcset:
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            if parts:
                found.append(parts[-1])
        for a in ("data-src", "data-original", "data-lazy-src", "src"):
            if t.get(a):
                found.append(str(t.get(a)))
                break
    out, seen = [], set()
    for u in found:
        if not u or u.startswith("data:"):
            continue
        u = urljoin(url, u)
        if u not in seen and not u.lower().split("?")[0].endswith((".svg", ".gif", ".ico")):
            seen.add(u)
            out.append(u)
    return out


def exa_image_urls(url):
    key = KEYS.get("EXA_API_KEY")
    if not key:
        return []
    r = S.post("https://api.exa.ai/contents", headers={"x-api-key": key}, timeout=60,
               json={"urls": [url], "extras": {"imageLinks": 60}, "livecrawl": "fallback"})
    res = r.json().get("results", [])
    if not res:
        return []
    urls = list(res[0].get("extras", {}).get("imageLinks", []))
    if res[0].get("image"):
        urls.insert(0, res[0]["image"])
    return urls


def cmd_site(item, out):
    tag, url = item["tag"], item["url"]
    min_side, n = int(item.get("min_side", 600)), int(item.get("n", 12))
    print(f"[{tag}] 抓取页面图片：{url}")
    try:
        urls = page_image_urls(url)
    except Exception as e:
        print(f"  本地抓取失败：{e!r:.100}")
        urls = []
    if len(urls) < 3:
        print("  本地抓到的图太少，改用 Exa 提取页面图片链接")
        urls = list(dict.fromkeys(urls + exa_image_urls(url)))
    print(f"  页面图片链接 {len(urls)} 个，下载测量尺寸……")
    wd = workdir(out, tag)

    def one(iu):
        try:
            im, raw = get_image(iu, referer=url, timeout=20)
            return iu, im, raw
        except Exception:
            return iu, None, None
    with ThreadPoolExecutor(8) as ex:
        got = list(ex.map(one, urls[:50]))
    cands = []
    for k, (iu, im, raw) in enumerate(got):
        if im is None or max(im.size) < min_side:
            continue
        ext = (im.format or "jpg").lower().replace("jpeg", "jpg")
        local = wd / f"orig_{k}.{ext}"
        local.write_bytes(raw)
        cands.append(dict(provider="site", title=Path(urlparse(iu).path).name[:60], width=im.width,
                          height=im.height, thumb=iu, local=str(local), urls=[iu], page=url,
                          domain=domain_of(iu), page_domain=domain_of(url), license="官网图片",
                          license_class="official", author=domain_of(url)))
    cands.sort(key=lambda c: -c["width"] * c["height"])
    finalize(cands, n, out, tag, url)


# ---------------------------------------------------------------- icons
# Rasterise SVG -> 512px PNG with sharp; falls back to the global npm root when NODE_PATH is not set.
SVG2PNG_JS = r"""
const fs = require('fs'), path = require('path');
let sharp;
try { sharp = require('sharp'); } catch (e) {
  const root = require('child_process').execSync('npm root -g', {encoding: 'utf8'}).trim();
  sharp = require(path.join(root, 'sharp'));
}
(async () => {
  for (const f of JSON.parse(process.argv[1])) {
    await sharp(fs.readFileSync(f), {density: 300})
      .resize(512, 512, {fit: 'contain', background: {r: 0, g: 0, b: 0, alpha: 0}})
      .png().toFile(f.replace(/\.svg$/, '.png'));
  }
})().catch(e => { console.error(e.message); process.exit(1); });
"""


def svg_to_png(svgs):
    if not shutil.which("node"):
        print("  图标模式需要 Node.js（再执行 npm install -g sharp），本机没找到 node")
        return False
    r = subprocess.run(["node", "-e", SVG2PNG_JS, json.dumps([str(p) for p in svgs])],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"  SVG 转 PNG 失败，确认已执行 npm install -g sharp：{r.stderr.strip()[-200:]}")
        return False
    return True


def cmd_icons(item, out):
    tag, q = item["tag"], item["q"]
    n, color = int(item.get("n", 16)), item.get("color", "#1F2937")
    prefixes = item.get("prefixes", ICON_PREFIXES)
    print(f"[{tag}] 图标：{q}（Iconify，只支持英文关键词）")
    def iconify_search(query):
        return S.get("https://api.iconify.design/search", timeout=30,
                     params={"query": query, "limit": 64, "prefixes": prefixes}).json()
    d = iconify_search(q)
    names, cols = list(d.get("icons", [])), dict(d.get("collections", {}))
    if len(names) < 6 and " " in q.strip():   # multi-word queries are strict; widen with each word
        for word in q.split():
            extra = iconify_search(word)
            names += [x for x in extra.get("icons", []) if x not in names]
            cols.update(extra.get("collections", {}))
        print(f"  原查询结果太少，已追加单词 {q.split()} 的结果")
    names = names[:n]
    if not names:
        print(f"[{tag}] 没有匹配的图标，换个英文词试试。")
        return
    wd = workdir(out, tag)
    svgs = []
    for nm in names:
        pre, ic = nm.split(":", 1)
        svg = S.get(f"https://api.iconify.design/{pre}/{ic}.svg", params={"color": color, "height": 512},
                    timeout=20).text
        p = wd / f"{pre}__{ic}.svg"
        p.write_text(svg, encoding="utf-8")
        svgs.append(p)
    if not svg_to_png(svgs):
        print(f"[{tag}] SVG 已保存在 {wd.resolve()}，但没生成拼板。")
        return
    cands = []
    for nm, p in zip(names, svgs):
        pre = nm.split(":")[0]
        lic = cols.get(pre, {}).get("license", {})
        spdx = lic.get("spdx", "")
        cands.append(dict(provider="iconify", title=nm, width=512, height=512, thumb="",
                          local=str(p.with_suffix(".png")), svg=str(p), urls=[], page=f"https://icon-sets.iconify.design/{pre}/",
                          domain="iconify.design", page_domain=cols.get(pre, {}).get("name", pre),
                          license=spdx or lic.get("title", ""),
                          license_class="attribution" if spdx.startswith("CC-BY") else "free",
                          author=cols.get(pre, {}).get("author", {}).get("name", "")))
    finalize(cands, n, out, tag, q)


# ---------------------------------------------------------------- pick + credits
def save_image(im, dest_noext):
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        ext, kw = ".png", {}
    else:
        im = im.convert("RGB")
        ext, kw = ".jpg", {"quality": 90}
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    path = Path(str(dest_noext) + ext)
    im.save(path, **kw)
    return path, im.size


def cmd_pick(tag, ids, out, note=""):
    wd = Path(out) / "_work" / tag
    if not (wd / "candidates.json").exists():
        print(f"没有 {wd / 'candidates.json'}：先对 tag {tag} 运行 search（--out 要和 search 时一致）")
        return
    cands = {c["id"]: c for c in json.loads((wd / "candidates.json").read_text(encoding="utf-8"))}
    assets = Path(out) / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    mpath = Path(out) / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else []
    for i in ids:
        c = cands.get(i)
        if not c:
            print(f"  #{i} 不存在")
            continue
        im, degraded = None, False
        if c.get("local"):
            im = Image.open(c["local"])
            im.load()
        else:
            for u in c["urls"]:
                try:
                    im, _ = get_image(u, referer=c.get("page"), wiki=c["provider"] == "commons", timeout=40)
                    break
                except Exception:
                    continue
            if im is None and c.get("thumb"):
                try:
                    im, _ = get_image(c["thumb"], referer=c.get("page"), wiki=c["provider"] == "commons")
                    degraded = True
                except Exception:
                    pass
        if im is None:
            print(f"  #{i} 下载失败（原图和缩略图都拿不到），换一张")
            continue
        if max(im.size) < min(1000, 0.6 * max(c["width"], c["height"])):
            degraded = True   # got something much smaller than advertised
        path, size = save_image(im, assets / f"{tag}_{i}")
        extra = {}
        if c["provider"] == "iconify":
            svg_dest = assets / f"{tag}_{i}.svg"
            svg_dest.write_text(Path(c["svg"]).read_text(encoding="utf-8"), encoding="utf-8")
            extra["svg"] = str(svg_dest.resolve())
        entry = dict(tag=tag, id=i, file=str(path.resolve()), width=size[0], height=size[1],
                     degraded=degraded, provider=c["provider"], title=c["title"], source_page=c.get("page"),
                     image_url=(c["urls"] or [None])[0], license=c["license"],
                     license_class=c["license_class"], author=c.get("author", ""), query=c.get("query"),
                     note=note, **extra)
        manifest = [m for m in manifest if not (m["tag"] == tag and m["id"] == i)] + [entry]
        flag = "（只拿到缩略图，清晰度不够，建议换一张）" if degraded else ""
        print(f"  #{i} → {path.resolve()}  {size[0]}x{size[1]}  [{LIC_LABEL[c['license_class']]}]{flag}")
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest: {mpath.resolve()}（共 {len(manifest)} 张）")


def cmd_credits(out):
    mpath = Path(out) / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    rows = ["| 文件 | 来源 | 作者 | 授权 | 链接 |", "|---|---|---|---|---|"]
    short = []
    for m in manifest:
        src = {"commons": "Wikimedia Commons", "pixabay": "Pixabay", "iconify": "Iconify"}.get(
            m["provider"], domain_of(m.get("source_page")))
        rows.append(f"| {Path(m['file']).name} | {src} | {m.get('author') or ''} | {m['license']} | {m.get('source_page') or ''} |")
        if m["provider"] == "iconify" and m["license_class"] == "free":
            continue  # permissive icon sets: no per-icon credit needed
        who = f" / {m['author']}" if m.get("author") and m["provider"] in ("commons", "pixabay") else ""
        lic = "" if m["license_class"] in ("unknown", "official") else f" / {m['license']}"
        short.append(f"- {Path(m['file']).name}：{src}{who}{lic}")
    unknown = [m for m in manifest if m["license_class"] in ("unknown", "official", "check")]
    text = "# 图片来源\n\n" + "\n".join(rows) + "\n\n## 幻灯片署名（可直接放到致谢/来源页）\n\n" + "\n".join(short) + "\n"
    if unknown:
        text += ("\n## 注意\n\n以下图片来自普通网页或官网，版权归原作者，只适合内部汇报、课程作业等非公开用途，"
                 "且要注明来源；对外发布前请替换成可商用图片或取得授权：\n\n"
                 + "\n".join(f"- {Path(m['file']).name}（{m.get('source_page')}）" for m in unknown) + "\n")
    p = Path(out) / "credits.md"
    p.write_text(text, encoding="utf-8")
    print(f"credits: {p.resolve()}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("--plan")
    s.add_argument("--tag")
    s.add_argument("--q")
    s.add_argument("--q-en", dest="q_en")
    s.add_argument("--src", default="web,commons,pixabay")
    s.add_argument("--orient", default="any", choices=["any", "landscape", "portrait", "square"])
    s.add_argument("--min-side", dest="min_side", type=int, default=1000)
    s.add_argument("--n", type=int, default=12)
    t = sub.add_parser("site")
    t.add_argument("--tag", required=True)
    t.add_argument("--url", required=True)
    t.add_argument("--min-side", dest="min_side", type=int, default=600)
    t.add_argument("--n", type=int, default=12)
    i = sub.add_parser("icons")
    i.add_argument("--tag", required=True)
    i.add_argument("--q", required=True)
    i.add_argument("--color", default="#1F2937")
    i.add_argument("--n", type=int, default=16)
    i.add_argument("--prefixes", default=ICON_PREFIXES)
    p = sub.add_parser("pick")
    p.add_argument("--tag", required=True)
    p.add_argument("--ids", required=True)
    p.add_argument("--note", default="")
    sub.add_parser("credits")
    for sp in (s, t, i, p, sub.choices["credits"]):
        sp.add_argument("--out", default="images")
    a = ap.parse_args()

    if a.cmd == "search" and a.plan:
        items = json.loads(Path(a.plan).read_text(encoding="utf-8"))
        for it in items:
            mode = it.get("mode", "search")
            try:
                {"search": cmd_search, "site": cmd_site, "icons": cmd_icons}[mode](it, a.out)
            except Exception as e:
                print(f"[{it.get('tag')}] 出错：{e!r:.200}")
            print()
    elif a.cmd == "search":
        if not (a.tag and (a.q or a.q_en)):
            ap.error("search 需要 --tag 和 --q / --q-en（或用 --plan）")
        cmd_search(vars(a), a.out)
    elif a.cmd == "site":
        cmd_site(vars(a), a.out)
    elif a.cmd == "icons":
        cmd_icons(vars(a), a.out)
    elif a.cmd == "pick":
        cmd_pick(a.tag, [int(x) for x in a.ids.split(",") if x.strip()], a.out, a.note)
    elif a.cmd == "credits":
        cmd_credits(a.out)


if __name__ == "__main__":
    main()
