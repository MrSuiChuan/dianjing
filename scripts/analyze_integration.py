#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hualong × dianjing 接口测量:
1) 正文风格指标(人味分/段长/长段占比/口语密度)与点赞的关系;
2) 标题的关键信息在正文里兑现得多早(承诺兑现率)。

用法: py -3 scripts/analyze_integration.py [--corpus DIR] [--votes FILE] [--out FILE]
"""
import argparse
import datetime
import json
import math
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HUALONG_SCRIPTS = Path(r"C:\Users\wuzongyun\Documents\ChatGPT\hualong\scripts")
sys.path.insert(0, str(HUALONG_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import style_check as sc  # noqa: E402  hualong 的体检器
import analyze_titles as at  # noqa: E402

STOP = set("的了我你是在和与把被这那他她它们我们你们什么怎么为什么一个这个那个就是都还很最更会能要不对从到让给为以及或等中上下了里后前时天年月日第个种点次文章东西时候地方因为所以但是如果而且然后还是可以已经自己知道觉得可能真的这个那么一些这些那些")


def normalize(text):
    t = re.sub(r"[\s\u3000]+", "", text or "")
    t = t.translate(str.maketrans({"「": "", "」": "", "“": "", "”": "", "，": "", "。": "",
                                   "！": "", "？": "", "、": "", "：": "", "；": ""}))
    return t


def title_keys(title):
    t = normalize(title)
    bigrams = {t[i:i + 2] for i in range(len(t) - 1)}
    return {g for g in bigrams if not any(ch in STOP for ch in g)}


def body_coverage(title, body):
    keys = title_keys(title)
    if not keys:
        return None
    norm_body = normalize(body)
    head = norm_body[:max(int(len(norm_body) * 0.25), 1)]
    hit_all = sum(1 for g in keys if g in norm_body)
    hit_head = sum(1 for g in keys if g in head)
    nums = re.findall(r"\d+", title)
    num_hit = sum(1 for n in nums if n in norm_body)
    return {"keys": len(keys), "cover_all": hit_all / len(keys), "cover_head": hit_head / len(keys),
            "numbers": len(nums), "num_cover": (num_hit / len(nums)) if nums else None}


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        for pos, i in enumerate(order):
            rk[i] = pos + 1
        return rk
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = (sum((rx[i] - mx) ** 2 for i in range(n)) * sum((ry[i] - my) ** 2 for i in range(n))) ** 0.5
    return round(num / den, 3) if den else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(Path(__file__).resolve().parent.parent.parent / "writing-corpus"))
    ap.add_argument("--votes", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    corpus = Path(args.corpus)
    votes_path = Path(args.votes) if args.votes else corpus / "reports" / "votes.json"

    votes = json.loads(votes_path.read_text(encoding="utf-8")) if votes_path.exists() else {}
    rows = []
    for fp in sorted((corpus / "contents").glob("*.md")):
        m = re.match(r"^(\d{3})_(\d+)_", fp.name)
        if not m:
            continue
        aid = m.group(2)
        raw = fp.read_text(encoding="utf-8")
        lines = raw.splitlines()
        title = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:])
        prose, steps = sc.parse(fp)
        if not prose:
            continue
        met = sc.measure(prose, steps)
        score = max(sc.human_score(met, "tech")[0], sc.human_score(met, "human")[0])
        cov = body_coverage(title, body)
        v = votes.get(aid)
        rows.append({"id": aid, "title": title, "score": score, **met, **(cov or {}),
                     "voteup": (v or {}).get("voteup"), "created": (v or {}).get("created")})

    # 同年百分位,消除时间累积偏差
    by_year = defaultdict(list)
    for r in rows:
        if r["voteup"] is not None and r["created"]:
            r["year"] = datetime.datetime.fromtimestamp(r["created"]).year
            by_year[r["year"]].append(r)
    for y, g in by_year.items():
        g.sort(key=lambda x: x["voteup"])
        for i, r in enumerate(g):
            r["pct"] = i / max(len(g) - 1, 1)
    joined = [r for r in rows if "pct" in r]

    body_feats = ["score", "para_med", "long_ratio", "colloquial_per_1k", "sentence_med",
                  "start_dup_rate", "abstract_per_1k", "images"]
    title_feats = ["cover_all", "cover_head", "num_cover"]
    corr_body = {k: spearman([float(r.get(k) or 0) for r in joined], [r["pct"] for r in joined])
                 for k in body_feats if k in joined[0]}
    corr_title = {k: spearman([float(r[k]) for r in joined if r.get(k) is not None],
                              [r["pct"] for r in joined if r.get(k) is not None])
                  for k in title_feats}

    def band(key, rows_):
        v = sorted(r[key] for r in rows_ if r.get(key) is not None)
        if not v:
            return None
        q = lambda p: round(v[min(len(v) - 1, int(len(v) * p))], 3)
        return {"n": len(v), "p10": q(.1), "p50": q(.5), "p90": q(.9), "mean": round(sum(v) / len(v), 3)}

    report = {
        "n_articles": len(rows), "n_with_votes": len(joined),
        "body_style_vs_likes": corr_body,
        "title_body_vs_likes": corr_title,
        "coverage_distribution": {k: band(k, rows) for k in ["cover_all", "cover_head", "num_cover"]},
        "human_score_distribution": band("score", rows),
        "head_delivery": {
            "share_cover_head_ge_60pct": round(sum(1 for r in rows if (r.get("cover_head") or 0) >= 0.6) / len(rows), 3),
            "share_cover_head_ge_80pct": round(sum(1 for r in rows if (r.get("cover_head") or 0) >= 0.8) / len(rows), 3),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2)[:2000])
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("report ->", args.out)


if __name__ == "__main__":
    main()
