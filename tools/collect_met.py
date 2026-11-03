#!/usr/bin/env python3
"""Collect public-domain (CC0) reference images from The Met Open Access API.

Usage: python3 collect_met.py <topic> <target_count> <out_dir> [--download]

Every kept object is Public Domain (isPublicDomain == True). Metadata goes to
catalog.csv; with --download a ~800px "web-large" image is saved per object.
"""
import csv, json, os, sys, time, urllib.parse, urllib.request

BASE = "https://collectionapi.metmuseum.org/public/collection"
UA = "RefCollector/1.1 (educational reference collection)"

TOPICS = {
    "katana": {
        "queries": ["katana", "tachi", "wakizashi", "tanto", "Japanese sword blade",
                    "tsuba", "koshirae", "sword mounting Japanese", "habaki", "menuki",
                    "kozuka", "fuchi kashira", "kogai", "sword scabbard Japanese", "naginata"],
        "keep": lambda d: d.get("culture", "").startswith("Japan") and any(
            k in (d.get("classification", "") + d.get("objectName", "") + d.get("title", "")).lower()
            for k in ["sword", "blade", "tsuba", "katana", "tachi", "wakizashi", "tant", "koshirae",
                      "habaki", "menuki", "kozuka", "fuchi", "kashira", "kogai", "scabbard", "saya", "naginata"]),
    },
    "samurai_clothing": {
        "queries": ["Japanese armor", "gusoku", "yoroi", "domaru", "haramaki armor", "kabuto helmet",
                    "menpo mask", "sode shoulder guard", "kote sleeve", "suneate", "haidate",
                    "jinbaori", "kamishimo", "kataginu", "hakama", "haori", "kosode", "samurai",
                    "dofuku", "warrior Japanese print"],
        "keep": lambda d: d.get("culture", "").startswith("Japan"),
    },
}


def get(url):
    for attempt in range(4):
        try:
            time.sleep(0.25)
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(3 * (attempt + 1))
    return {}


def search(q, limit=80):
    url = f"{BASE}/v1.1/search?" + urllib.parse.urlencode(
        {"hasImages": "true", "q": q, "limit": limit, "offset": 0})
    return get(url).get("objectIDs") or []


def main():
    topic, target, out_dir = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    cfg = TOPICS[topic]
    pools = [search(q) for q in cfg["queries"]]
    order, seen = [], set()
    for k in range(max(map(len, pools))):  # round-robin for variety
        for p in pools:
            if k < len(p) and p[k] not in seen:
                seen.add(p[k]); order.append(p[k])
    rows = []
    for oid in order:
        if len(rows) >= target:
            break
        d = get(f"{BASE}/v1/objects/{oid}")
        if not d or not d.get("isPublicDomain") or not d.get("primaryImageSmall"):
            continue
        if not cfg["keep"](d):
            continue
        rows.append({
            "id": f"{len(rows) + 1:03d}", "objectID": oid, "title": d.get("title", ""),
            "objectName": d.get("objectName", ""), "classification": d.get("classification", ""),
            "date": d.get("objectDate", ""), "artist": d.get("artistDisplayName", ""),
            "medium": (d.get("medium") or "")[:200], "dimensions": (d.get("dimensions") or "")[:200],
            "image": d.get("primaryImageSmall"), "page": d.get("objectURL", ""), "license": "CC0 (Met Open Access)",
        })
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "catalog.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    if "--download" in sys.argv:
        img_dir = os.path.join(out_dir, "images"); os.makedirs(img_dir, exist_ok=True)
        for r in rows:
            dst = os.path.join(img_dir, f"{r['id']}.jpg")
            if os.path.exists(dst):
                continue
            try:
                req = urllib.request.Request(urllib.parse.quote(r["image"], safe=":/"), headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as resp, open(dst, "wb") as f:
                    f.write(resp.read())
            except Exception as e:
                print("fail", r["objectID"], e, file=sys.stderr)
            time.sleep(0.2)
    print(f"{topic}: candidates={len(order)} kept={len(rows)}")


if __name__ == "__main__":
    main()
