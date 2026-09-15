#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标题效果回填与复盘: 把发布后的数据记下来, 让配额和 Top3 排序有据可依。

用法:
  # 回填一条(发布 3 天后填一次即可)
  py -3 scripts/title_feedback.py --add --title "标题原文" --platform 公众号 \
      --category "⑥批判冲突金句" --mechanism 立场 \
      --impressions 12000 --clicks 900 --likes 120

  # 看复盘
  py -3 scripts/title_feedback.py --report

  # 看全部记录
  py -3 scripts/title_feedback.py --list

存储位置: 环境变量 TITLE_FEEDBACK_FILE, 默认 <CORPUS_DIR>/reports/title_feedback.jsonl
"""
import argparse
import json
import os
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

MECHANISMS = ["信息差", "身份共鸣", "利益", "情绪", "立场"]


def store_path():
    explicit = os.environ.get("TITLE_FEEDBACK_FILE")
    if explicit:
        return Path(explicit)
    corpus = os.environ.get("CORPUS_DIR")
    base = Path(corpus) if corpus else Path(__file__).resolve().parent.parent.parent / "writing-corpus"
    return base / "reports" / "title_feedback.jsonl"


def load(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def add(path, args):
    row = {
        "date": args.date or date.today().isoformat(),
        "platform": args.platform or "",
        "title": args.title,
        "category": args.category or "",
        "mechanism": args.mechanism or "",
        "impressions": args.impressions,
        "clicks": args.clicks,
        "likes": args.likes,
        "comments": args.comments,
        "notes": args.notes or "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"已记录: {row['title'][:30]} | 曝光 {row['impressions']} 点击 {row['clicks']} 赞 {row['likes']}")
    print(f"文件: {path}")


def ctr_of(row):
    imp, clk = row.get("impressions") or 0, row.get("clicks") or 0
    return clk / imp if imp else None


def group_stats(rows, key):
    groups = defaultdict(list)
    for r in rows:
        k = r.get(key) or "未标注"
        groups[k].append(r)
    out = []
    for k, g in groups.items():
        ctrs = [c for c in (ctr_of(r) for r in g) if c is not None]
        likes = [r.get("likes") or 0 for r in g]
        out.append({"key": k, "n": len(g),
                    "ctr_med": round(st.median(ctrs), 4) if ctrs else None,
                    "likes_med": st.median(likes) if likes else 0})
    return sorted(out, key=lambda x: -(x["ctr_med"] or 0))


def report(path, as_json=False):
    rows = load(path)
    if not rows:
        print("还没有回填记录。发一篇之后这样记:")
        print('  py -3 scripts/title_feedback.py --add --title "标题" --platform 公众号 \\')
        print('      --category "⑥批判冲突金句" --mechanism 立场 --impressions 12000 --clicks 900 --likes 120')
        return 0

    payload = {"n": len(rows), "file": str(path),
               "by_category": group_stats(rows, "category"),
               "by_mechanism": group_stats(rows, "mechanism"),
               "by_platform": group_stats(rows, "platform")}
    ranked = sorted([r for r in rows if ctr_of(r) is not None], key=lambda r: -ctr_of(r))
    payload["top_by_ctr"] = [{"title": r["title"], "ctr": round(ctr_of(r), 4), "likes": r.get("likes")}
                             for r in ranked[:5]]

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"# 标题效果复盘(共 {len(rows)} 条)")
    print()
    for title, key in [("按公式类别", "by_category"), ("按传播机制", "by_mechanism"), ("按平台", "by_platform")]:
        print(f"## {title}")
        print()
        print("| 分组 | 条数 | 点击率中位 | 点赞中位 |")
        print("| --- | --- | --- | --- |")
        for g in payload[key]:
            ctr = f"{g['ctr_med']*100:.2f}%" if g["ctr_med"] is not None else "-"
            print(f"| {g['key']} | {g['n']} | {ctr} | {g['likes_med']:.0f} |")
        print()
    if payload["top_by_ctr"]:
        print("## 点击率最高的 5 条")
        print()
        for r in payload["top_by_ctr"]:
            print(f"- {r['ctr']*100:.2f}% | {r['title'][:40]}")
        print()
    small = [g for g in payload["by_mechanism"] if g["n"] < 3]
    if small:
        print(f"> 提示:有 {len(small)} 个机制的分组少于 3 条,先别据此下结论。")
    else:
        best = payload["by_mechanism"][0]
        print(f"> 目前点击率最高的机制是「{best['key']}」({best['ctr_med']*100:.2f}%,n={best['n']}),"
              f"下一批标题可以向它倾斜。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", action="store_true", help="回填一条记录")
    ap.add_argument("--report", action="store_true", help="按类别/机制/平台复盘")
    ap.add_argument("--list", action="store_true", help="列出全部记录")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出复盘")
    ap.add_argument("--title")
    ap.add_argument("--platform", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--mechanism", choices=MECHANISMS, default="")
    ap.add_argument("--impressions", type=int, default=0)
    ap.add_argument("--clicks", type=int, default=0)
    ap.add_argument("--likes", type=int, default=0)
    ap.add_argument("--comments", type=int, default=0)
    ap.add_argument("--date", default="")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    path = store_path()
    if args.add:
        if not args.title:
            print("[错误] --add 需要 --title")
            sys.exit(2)
        add(path, args)
        return 0
    if args.list:
        for r in load(path):
            print(f"{r['date']} | {r.get('platform','')} | {r.get('mechanism','')} | "
                  f"{r.get('category','')} | {r['title'][:40]}")
        return 0
    return report(path, args.json)


if __name__ == "__main__":
    sys.exit(main())
