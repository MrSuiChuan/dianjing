#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标题语料分析: 长度/疑问/数字/冲突词/公式覆盖度, 有赞数时做分位与相关性。

用法:
  py -3 scripts/analyze_titles.py --index <title_index.md> [--votes <votes.json>]
"""
import argparse
import json
import re
import statistics as st
from pathlib import Path

CONFLICT = ["战争", "杀死", "摧毁", "揭露", "干掉", "崩塌", "灭绝", "毁掉", "绞杀", "撕开", "掀翻"]
VERBS = ["搓", "喂", "速通", "拆解", "揭秘", "挖出", "潜伏", "偷", "蒸馏", "还原", "复刻"]
TIME_ANCHORS = ["今天", "昨天", "最近", "这两天", "上周", "刚刚", "前几天", "前两天", "今年"]
FIRST_PERSON = ["我", "我们", "咱"]

# 5 类公式的可判定特征(用于测算覆盖度)
CATEGORY_RULES = {
    "①玩梗体验": ["我用", "我把", "我把我的", "喂给", "坏了我成", "伪装", "潜伏", "偷", "整活", "亲手", "假装"],
    "②测评首发": ["实测", "测评", "评测", "试完", "上手", "一手", "首发", "对比", "横评", "体验了"],
    "③工具实操": ["教程", "保姆", "从0", "从 0", "从零", "速通", "步", "怎么", "如何", "教你", "攻略", "指南"],
    "④开源分享": ["开源", "分享", "免费", "白嫖", "送你", "整理", "合集", "盘点"],
    "⑤思考心得": ["真相", "我觉得", "在我看来", "心得", "观察", "思考", "为什么", "聊聊", "反思", "真相是"],
    "⑥批判冲突金句": ["战争", "杀死", "绞杀", "摧毁", "毁灭", "崩塌", "消亡", "垃圾场", "谄媚", "投毒",
                       "漏洞", "黑暗森林", "照妖镜", "泡沫", "骗局", "危机", "灭绝", "反常识",
                       "最正确", "最伟大", "最大的 Bug", "正在杀死", "正在摧毁"],
}
CATEGORY_REGEX = {
    "⑥批判冲突金句": r"也.{0,8}(绞杀|杀死|摧毁|终结|毁掉|撕开)|正在(杀死|摧毁|毁掉)",
}


def parse_index(path):
    sections, current, top = {}, None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## "):
            current = s[3:].strip()
            sections.setdefault(current, [])
            continue
        if s.startswith("- ") and current:
            title = s[2:].strip()
            if title:
                sections[current].append(title)
    for name, items in sections.items():
        if "top" in name.lower():
            top = items
    all_titles, seen = [], set()
    for name, items in sections.items():
        for t in items:
            k = re.sub(r"[\s，。！？；：、,\.!?;:]+", "", t)
            if k in seen:
                continue
            seen.add(k)
            all_titles.append(t)
    return sections, top, all_titles


def feats(title):
    digits = len(re.findall(r"\d", title))
    return {
        "len": len(title),
        "question": bool(re.search(r"[?？]", title)),
        "digit": digits > 0,
        "digit_n": digits,
        "conflict": any(w in title for w in CONFLICT),
        "verb": any(w in title for w in VERBS),
        "time_anchor": any(title.startswith(w) for w in TIME_ANCHORS),
        "first_person": any(w in title for w in FIRST_PERSON),
        "quote": bool(re.search(r"[「『\"“]", title)),
        "colon_dash": bool(re.search(r"[:：—\-]", title)),
        "no_period_end": not title.rstrip().endswith("。"),
    }


def summarize(rows):
    n = len(rows)
    if not n:
        return {}
    lens = sorted(r["len"] for r in rows)
    def share(key):
        return round(sum(1 for r in rows if r[key]) / n, 3)
    return {
        "n": n,
        "len_mean": round(sum(lens) / n, 1),
        "len_med": st.median(lens),
        "len_p10": lens[int(n * 0.1)], "len_p90": lens[min(n - 1, int(n * 0.9))],
        "share_le26": round(sum(1 for x in lens if x <= 26) / n, 3),
        "share_question": share("question"), "share_digit": share("digit"),
        "share_conflict": share("conflict"), "share_verb": share("verb"),
        "share_time_anchor": share("time_anchor"), "share_first_person": share("first_person"),
        "share_quote": share("quote"), "share_colon_dash": share("colon_dash"),
    }


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
    ap.add_argument("--index", default=str(Path(__file__).resolve().parent.parent / "references" / "title_index.md"))
    ap.add_argument("--votes", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    index_path = Path(args.index)
    sections, top, all_titles = parse_index(index_path)
    print(f"索引文件: {index_path}")
    print(f"章节: {[(k, len(v)) for k, v in sections.items()]}")

    rows = [{"title": t, **feats(t)} for t in all_titles]
    for r in rows:
        hits = [c for c, kws in CATEGORY_RULES.items() if any(k in r["title"] for k in kws)]
        hits += [c for c, pat in CATEGORY_REGEX.items() if re.search(pat, r["title"])]
        r["categories"] = hits
    covered = [r for r in rows if r["categories"]]
    multi = [r for r in rows if len(r["categories"]) > 1]
    report = {"index": str(index_path), "total": len(rows), "top_section": len(top),
              "overall": summarize(rows), "top_section_feats": summarize([{"title": t, **feats(t)} for t in top]),
              "coverage": {"covered": len(covered), "coverage_rate": round(len(covered) / len(rows), 3),
                           "multi_label": len(multi),
                           "per_category": {c: sum(1 for r in rows if c in r["categories"]) for c in CATEGORY_RULES}},
              "uncovered_titles": [r["title"] for r in rows if not r["categories"]][:30]}

    if args.votes and Path(args.votes).exists():
        votes = json.loads(Path(args.votes).read_text(encoding="utf-8"))
        by_title = {}
        for aid, v in votes.items():
            if v.get("title"):
                by_title[re.sub(r"[\s，。！？；：、,\.!?;:]+", "", v["title"])] = v
        joined = []
        for r in rows:
            key = re.sub(r"[\s，。！？；：、,\.!?;:]+", "", r["title"])
            v = by_title.get(key)
            if v and v.get("voteup") is not None:
                joined.append({**r, "voteup": v["voteup"], "comment": v.get("comment")})
        if joined:
            joined.sort(key=lambda x: -x["voteup"])
            n = len(joined)
            deciles = {}
            for i in range(10):
                seg = joined[int(n * i / 10): int(n * (i + 1) / 10)] or []
                deciles[f"D{i+1}"] = {"n": len(seg), **summarize(seg),
                                      "voteup_med": st.median([s["voteup"] for s in seg]) if seg else 0}
            import math
            corr = {k: spearman([math.log10(r["voteup"] + 10) for r in joined],
                                [float(r[k]) for r in joined])
                    for k in ["len", "digit_n", "question", "conflict", "verb", "first_person", "time_anchor"]}
            report["vote_analysis"] = {"joined": len(joined), "deciles": deciles, "spearman_log_vote": corr,
                                       "top20": [{"title": j["title"], "voteup": j["voteup"], "len": j["len"],
                                                  "digit": j["digit_n"], "question": j["question"],
                                                  "conflict": j["conflict"]} for j in joined[:20]]}
            report["overall_with_votes"] = summarize(joined)

    print(json.dumps({k: v for k, v in report.items() if k not in ("deciles",)}, ensure_ascii=False)[:1200])
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("report ->", args.out)


if __name__ == "__main__":
    main()
