#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标题查重: 检查候选标题与标题索引里的已有标题是否过度重合。

用法:
  py -3 scripts/title_overlap_check.py "候选标题一" "候选标题二" --index references/title_index.md
  py -3 scripts/title_overlap_check.py --file candidates.txt --index references/title_index.md

判定: 连续重合 >=10 字 FAIL, 6-9 字 WARN。标题很短, 阈值比长文更严。
"""
import argparse
import json
import re
import sys
from pathlib import Path

FAIL_LEN = 10
WARN_LEN = 6

PUNCT_MAP = str.maketrans({
    "，": ",", "。": ".", "！": "!", "？": "?", "；": ";", "：": ":",
    "（": "(", "）": ")", "「": "[", "」": "]", "《": "<", "》": ">",
    "“": '"', "”": '"', "‘": "'", "’": "'", "、": ",", "—": "-", "－": "-",
    "【": "[", "】": "]", "…": ".", "　": "", " ": "",
})


def normalize(text):
    t = re.sub(r"\s+", "", text or "")
    return t.translate(PUNCT_MAP)


def load_index(path):
    titles = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("- "):
            t = s[2:].strip()
            if t:
                titles.append(t)
    seen, out = set(), []
    for t in titles:
        k = normalize(t)
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def longest_common(cand, other):
    """返回候选标题与已有标题的最长连续公共片段。"""
    best = ""
    for i in range(len(cand)):
        for j in range(len(cand), i + len(best), -1):
            frag = cand[i:j]
            if len(frag) <= len(best):
                break
            if frag in other:
                best = frag
                break
    return best


def check(cand, index_titles):
    c = normalize(cand)
    worst = {"title": "", "span": "", "length": 0}
    for t in index_titles:
        span = longest_common(c, normalize(t))
        if len(span) > worst["length"]:
            worst = {"title": t, "span": span, "length": len(span)}
    verdict = "FAIL" if worst["length"] >= FAIL_LEN else ("WARN" if worst["length"] >= WARN_LEN else "PASS")
    return {**worst, "verdict": verdict, "candidate": cand}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", help="候选标题")
    ap.add_argument("--file", help="每行一条候选标题的文件")
    ap.add_argument("--index", default=str(Path(__file__).resolve().parent.parent / "references" / "title_index.md"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    candidates = list(args.titles)
    if args.file:
        candidates += [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not candidates:
        print("[错误] 没有候选标题")
        sys.exit(2)

    index_titles = load_index(args.index)
    if not index_titles:
        print(f"[错误] 索引里没有任何标题: {args.index}")
        print("       路径写错或文件为空时,查重会全部放行,所以这里直接报错退出。")
        sys.exit(2)
    results = [check(c, index_titles) for c in candidates]
    worst = max(results, key=lambda r: r["length"])

    if args.json:
        print(json.dumps({"index": args.index, "index_size": len(index_titles),
                          "results": results, "verdict": worst["verdict"]}, ensure_ascii=False, indent=2))
        sys.exit(0 if worst["verdict"] == "PASS" else 1)

    print(f"# 标题查重(索引 {len(index_titles)} 条)")
    print()
    print("| 候选标题 | 结果 | 最长重合 | 撞车标题 |")
    print("| --- | --- | --- | --- |")
    for r in results:
        print(f"| {r['candidate'][:30]} | {r['verdict']} | {r['length']} | {(r['title'] or '-')[:30]} |")
    if any(r["verdict"] != "PASS" for r in results):
        print("\n重合片段必须换句式或换角度重写:")
        for r in results:
            if r["verdict"] != "PASS":
                print(f"- 「{r['span']}」 撞上「{r['title']}」")
    sys.exit(0 if worst["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
