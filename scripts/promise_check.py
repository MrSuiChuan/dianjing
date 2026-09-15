#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标题承诺兑现检测: 标题说的东西, 正文里到底有没有。

用法:
  py -3 scripts/promise_check.py --title "标题原文" --body 草稿.md
  py -3 scripts/promise_check.py --title "..." --body 草稿.md --json

判定线(来自语料实测):
  - 标题里的数字必须 100% 出现在正文(语料中位兑现率 1.0, 均值 0.958)→ 违反即 FAIL
  - 标题关键词全文覆盖率 >=0.65 为理想(语料中位), 0.45 为底线(语料 p10)→ 低于底线 FAIL
  - 正文前 1/4 的覆盖率不作要求(实测与点赞相关性 0.116, 低于全文 0.183)
"""
import argparse
import json
import re
import sys
from pathlib import Path

COVER_FAIL = 0.45
COVER_GOOD = 0.65
NUM_FAIL = 1.0

STOP = set("的了我你是在和与把被这那他她它们我们你们什么怎么为什么一个这个那个就是都还很最更会能要不对从到让给为以及或等中上下了里后前时天年月日第个种点次文章东西时候地方因为所以但是如果而且然后还是可以已经自己知道觉得可能真的这么一些这些那些")

MAP = str.maketrans({"「": "", "」": "", "“": "", "”": "", "，": "", "。": "", "！": "",
                     "？": "", "、": "", "：": "", "；": "", "「": ""})


def normalize(text):
    return re.sub(r"[\s\u3000]+", "", (text or "").translate(MAP))


def title_keys(title):
    t = normalize(title)
    grams = {t[i:i + 2] for i in range(len(t) - 1)}
    return {g for g in grams if not any(ch in STOP for ch in g)}


def check(title, body):
    body_n = normalize(body)
    head = body_n[:max(int(len(body_n) * 0.25), 1)]
    keys = title_keys(title)
    miss_all = sorted(g for g in keys if g not in body_n)
    miss_head = sorted(g for g in keys if g not in head)
    cover_all = 1 - len(miss_all) / len(keys) if keys else 1.0
    cover_head = 1 - len(miss_head) / len(keys) if keys else 1.0
    nums = re.findall(r"\d+", title)
    miss_nums = [n for n in nums if n not in body_n]
    num_cover = 1 - len(miss_nums) / len(nums) if nums else None

    verdict = "PASS"
    reasons = []
    if miss_nums:
        verdict = "FAIL"
        reasons.append(f"标题里的数字 {miss_nums} 正文里找不到")
    if cover_all < COVER_FAIL:
        verdict = "FAIL"
        reasons.append(f"标题关键词覆盖率 {cover_all:.0%} 低于底线 {COVER_FAIL:.0%}")
    elif cover_all < COVER_GOOD and verdict == "PASS":
        verdict = "WARN"
        reasons.append(f"覆盖率 {cover_all:.0%} 未到理想线 {COVER_GOOD:.0%}")
    return {"verdict": verdict, "reasons": reasons, "cover_all": round(cover_all, 3),
            "cover_head": round(cover_head, 3), "num_cover": (round(num_cover, 3) if num_cover is not None else None),
            "missing_keys": miss_all[:12], "missing_numbers": miss_nums}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", required=True, help="正文 markdown 路径, 或直接给正文文本片段")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    p = Path(args.body)
    body = p.read_text(encoding="utf-8") if p.exists() else args.body
    r = check(args.title, body)

    if args.json:
        print(json.dumps({**r, "title": args.title}, ensure_ascii=False, indent=2))
        sys.exit(0 if r["verdict"] == "PASS" else 1)

    print("# 标题承诺兑现检测")
    print()
    print(f"- 标题: {args.title}")
    print(f"- 关键词全文覆盖率: {r['cover_all']:.0%}(理想 ≥{COVER_GOOD:.0%},底线 ≥{COVER_FAIL:.0%})")
    print(f"- 关键词开头覆盖率: {r['cover_head']:.0%}(不作要求,仅供参考)")
    if r["num_cover"] is not None:
        print(f"- 数字兑现率: {r['num_cover']:.0%}(必须 100%)")
    print(f"- 结论: {r['verdict']}")
    if r["missing_keys"]:
        print(f"- 正文里没出现的关键词片段: {' / '.join(r['missing_keys'])}")
    if r["reasons"]:
        print()
        print("## 需要处理")
        for x in r["reasons"]:
            print(f"- {x}")
        print()
        print("处理原则:要么改标题(删掉正文兑现不了的部分),要么补正文(把承诺讲到位),不许两边都不动。")
    sys.exit(0 if r["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
