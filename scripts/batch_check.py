#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次体检: 校验一批标题是否满足配额、有没有互相重复、有没有撞语料。

用法:
  py -3 scripts/batch_check.py 批次.md --platform 公众号 --index references/title_index.md

输入格式(二选一):
  1) markdown 表格, 表头含 标题 / 传播机制 / 公式类型(推荐, 能查配额)
     | 标题 | 传播机制 | 公式类型 | 钩子解读 |
  2) 纯文本, 每行一条标题(只能查数量、长度和重复)

判定:
  - 条数 = 10
  - 5 种传播机制各 2 条(有机制列时)
  - ⑥批判冲突金句 ≥2 条(有公式列时)
  - 标题长度不超过平台上限
  - 批次内部两两 4-gram 相似度 ≥0.40 判重复
  - 与索引的最长连续重合 ≥10 字判撞车
"""
import argparse
import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import title_overlap_check as toc  # noqa: E402

MECHANISMS = ["信息差", "身份共鸣", "利益", "情绪", "立场"]
PLATFORM_LIMITS = {"公众号": 24, "知乎": 30, "小红书": 20, "b站": 25, "B站": 25}
DUP_THRESHOLD = 0.40
EXPECTED_COUNT = 10


def parse_batch(text):
    rows = []
    header = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set(cells) >= {"标题"}:
                header = cells
                continue
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if header:
                rows.append({header[i]: cells[i] for i in range(min(len(header), len(cells)))})
        elif s and not s.startswith("#"):
            rows.append({"标题": s})
    return rows


def similarity(a, b):
    norm = lambda t: re.sub(r"[\s，。！？；：、,\.!?;:]+", "", t)
    ga = {norm(a)[i:i + 4] for i in range(max(len(norm(a)) - 3, 0))}
    gb = {norm(b)[i:i + 4] for i in range(max(len(norm(b)) - 3, 0))}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", help="批次文件(markdown 表格或每行一条标题)")
    ap.add_argument("--platform", default="公众号")
    ap.add_argument("--index", default=str(Path(__file__).resolve().parent.parent / "references" / "title_index.md"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = parse_batch(Path(args.batch).read_text(encoding="utf-8"))
    titles = [r["标题"] for r in rows if r.get("标题")]
    problems, warnings = [], []

    if len(titles) != EXPECTED_COUNT:
        problems.append(f"条数是 {len(titles)},要求 {EXPECTED_COUNT} 条")

    limit = PLATFORM_LIMITS.get(args.platform)
    if limit:
        for t in titles:
            if len(t) > limit:
                problems.append(f"超长({len(t)}字>{limit}): {t[:24]}")

    mech_counts = {}
    for r in rows:
        m = (r.get("传播机制") or "").strip()
        if m:
            mech_counts[m] = mech_counts.get(m, 0) + 1
    if mech_counts:
        for m in MECHANISMS:
            if mech_counts.get(m, 0) != 2:
                problems.append(f"机制「{m}」有 {mech_counts.get(m, 0)} 条,要求 2 条")
        extra = {k: v for k, v in mech_counts.items() if k not in MECHANISMS}
        if extra:
            warnings.append(f"出现了未定义的机制: {extra}")

    formula_cells = [r.get("公式类型", "") for r in rows]
    if any(formula_cells):
        conflict = sum(1 for c in formula_cells if "⑥" in c or "批判" in c or "冲突" in c)
        if conflict < 2:
            problems.append(f"⑥批判冲突金句只有 {conflict} 条,要求 ≥2 条")

    dup_pairs = []
    for a, b in itertools.combinations(titles, 2):
        s = similarity(a, b)
        if s >= DUP_THRESHOLD:
            dup_pairs.append({"a": a, "b": b, "similarity": round(s, 2)})
    if dup_pairs:
        problems.append(f"批次内有 {len(dup_pairs)} 对高度重复")

    index_titles = toc.load_index(args.index) if Path(args.index).exists() else []
    collisions = []
    if index_titles:
        for t in titles:
            r = toc.check(t, index_titles)
            if r["verdict"] != "PASS":
                collisions.append({"title": t, "verdict": r["verdict"], "hit": r["title"], "span": r["span"]})
        if collisions:
            problems.append(f"有 {len(collisions)} 条与索引撞车")
    else:
        warnings.append("没找到索引,跳过了撞车检查")

    payload = {"n": len(titles), "platform": args.platform, "limit": limit,
               "mechanisms": mech_counts, "duplicates": dup_pairs, "collisions": collisions,
               "problems": problems, "warnings": warnings}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.exit(1 if problems else 0)

    print(f"# 批次体检({args.platform},共 {len(titles)} 条)")
    print()
    print("| 检查 | 结果 |")
    print("| --- | --- |")
    print(f"| 条数 = {EXPECTED_COUNT} | {'OK' if len(titles) == EXPECTED_COUNT else 'X'} |")
    if limit:
        over = [t for t in titles if len(t) > limit]
        print(f"| 字数 ≤ {limit} | {'OK' if not over else f'X({len(over)} 条超长)'} |")
    if mech_counts:
        ok = all(mech_counts.get(m, 0) == 2 for m in MECHANISMS)
        print(f"| 5 机制各 2 条 | {'OK' if ok else 'X'} |")
    if any(formula_cells):
        print(f"| ⑥批判冲突 ≥2 | {'OK' if sum(1 for c in formula_cells if '⑥' in c or '批判' in c or '冲突' in c) >= 2 else 'X'} |")
    print(f"| 批次内不重复 | {'OK' if not dup_pairs else f'X({len(dup_pairs)} 对)'} |")
    print(f"| 不与索引撞车 | {'OK' if index_titles and not collisions else ('X' if collisions else '跳过')} |")
    if dup_pairs:
        print()
        print("## 批次内重复")
        for d in dup_pairs:
            print(f"- {d['similarity']} | {d['a'][:26]} || {d['b'][:26]}")
    if collisions:
        print()
        print("## 与索引撞车")
        for c in collisions:
            print(f"- {c['verdict']} | 「{c['span']}」撞上「{c['hit'][:26]}」")
    if warnings:
        print()
        for w in warnings:
            print(f"> 提示:{w}")
    print()
    print("结论: " + ("不合格,先修上面的问题" if problems else "通过"))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
