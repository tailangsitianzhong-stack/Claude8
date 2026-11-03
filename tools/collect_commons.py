#!/usr/bin/env python3
"""Collect reference images (metadata + thumbnails) from Wikimedia Commons.

Usage: python3 collect_commons.py <topic> <target_count> <out_dir> [--download]
Topics are defined in TOPICS below. Only freely licensed Commons files are used,
and the license/author of every image is recorded in catalog.csv.
"""
import csv, json, os, re, sys, time, urllib.parse, urllib.request, html

API = "https://commons.wikimedia.org/w/api.php"
UA = "RefCollector/1.1 (https://www.mediawiki.org/wiki/API:Etiquette; low-rate educational use) python-urllib"

TOPICS = {
    "katana": {
        "categories": [
            "Category:Katana", "Category:Japanese swords", "Category:Tachi",
            "Category:Wakizashi", "Category:Tantō", "Category:Tsuba",
            "Category:Hamon (swords)", "Category:Koshirae", "Category:Nihonto in the Tokyo National Museum",
            "Category:Japanese swords in the Metropolitan Museum of Art",
        ],
        "searches": ["katana sword blade", "japanese sword tachi", "nihonto hamon",
                     "tsuba sword guard", "katana koshirae scabbard", "wakizashi blade"],
    },
    "samurai_clothing": {
        "categories": [
            "Category:Samurai armour", "Category:Yoroi", "Category:Ō-yoroi", "Category:Dō-maru",
            "Category:Tōsei gusoku", "Category:Kabuto", "Category:Kamishimo", "Category:Hakama",
            "Category:Haori", "Category:Kataginu", "Category:Menpō", "Category:Jinbaori",
            "Category:Samurai armour in the Metropolitan Museum of Art", "Category:Photographs of samurai",
        ],
        "searches": ["samurai armor yoroi", "samurai kamishimo", "samurai photograph 1860s",
                     "hakama haori samurai", "kabuto helmet", "gusoku armour", "samurai Beato"],
    },
}

def api(params):
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            time.sleep(1.5)  # be polite: well under rate limits
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            if body.lstrip().startswith(b"{"):
                return json.loads(body)
            time.sleep(30 * (attempt + 1))  # rate-limited (non-JSON reply)
        except Exception as e:
            time.sleep(10 * (attempt + 1))
    return {}

def cat_files(cat, limit=200):
    titles, cont = [], {}
    while len(titles) < limit:
        d = api({"action": "query", "list": "categorymembers", "cmtitle": cat,
                 "cmtype": "file", "cmlimit": 100, **cont})
        titles += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        if "continue" not in d: break
        cont = {"cmcontinue": d["continue"]["cmcontinue"]}
    return titles

def search_files(q, limit=100):
    d = api({"action": "query", "list": "search", "srsearch": q, "srnamespace": 6, "srlimit": limit})
    return [s["title"] for s in d.get("query", {}).get("search", [])]

def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

def info(titles):
    out = []
    for i in range(0, len(titles), 50):
        d = api({"action": "query", "titles": "|".join(titles[i:i+50]), "prop": "imageinfo",
                 "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 640})
        for p in d.get("query", {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [None])[0]
            if not ii or ii.get("mime") not in ("image/jpeg", "image/png"): continue
            if ii.get("width", 0) < 400: continue
            m = ii.get("extmetadata", {})
            out.append({
                "title": p["title"], "page": ii.get("descriptionurl"), "url": ii.get("url"),
                "thumb": ii.get("thumburl"), "width": ii.get("width"), "height": ii.get("height"),
                "license": strip(m.get("LicenseShortName", {}).get("value")),
                "artist": strip(m.get("Artist", {}).get("value"))[:120],
                "description": strip(m.get("ImageDescription", {}).get("value"))[:300].replace("\n", " "),
            })
    return out

def main():
    topic, target, out_dir = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    download = "--download" in sys.argv
    cfg = TOPICS[topic]
    seen, titles = set(), []
    pools = [cat_files(c, 60) for c in cfg["categories"]] + [search_files(q, 60) for q in cfg["searches"]]
    # round-robin across sources for variety
    for k in range(max(map(len, pools)) if pools else 0):
        for pool in pools:
            if k < len(pool) and pool[k] not in seen:
                seen.add(pool[k]); titles.append(pool[k])
    rows = info(titles)
    ok = [r for r in rows if r["license"] and r["license"].lower() not in ("", "copyrighted")]
    # keep round-robin order
    order = {t: i for i, t in enumerate(titles)}
    ok.sort(key=lambda r: order.get(r["title"], 1e9))
    ok = ok[:target]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "catalog.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", *ok[0].keys()] if ok else ["id"])
        w.writeheader()
        for i, r in enumerate(ok, 1):
            w.writerow({"id": f"{i:03d}", **r})
    if download:
        img_dir = os.path.join(out_dir, "thumbs"); os.makedirs(img_dir, exist_ok=True)
        for i, r in enumerate(ok, 1):
            dst = os.path.join(img_dir, f"{i:03d}.jpg")
            if os.path.exists(dst): continue
            try:
                req = urllib.request.Request(r["thumb"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as resp, open(dst, "wb") as f:
                    f.write(resp.read())
            except Exception as e:
                print("fail", r["title"], e, file=sys.stderr)
            time.sleep(1.0)
    print(f"{topic}: candidates={len(titles)} usable={len(rows)} kept={len(ok)}")

if __name__ == "__main__":
    main()
