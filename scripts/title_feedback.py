#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章级效果回填与复盘: 标题机制 + 正文模式一起记, 才能算出组合效果。

用法:
  # 回填一条(发布 3 天后填一次即可)
  py -3 scripts/title_feedback.py --add --title "标题原文" --platform 公众号 \
      --category "⑥批判冲突金句" --mechanism 立场 --body-mode tech \
      --draft 草稿.md \
      --impressions 12000 --clicks 900 --likes 120 --read-through 0.42

  # 复盘: 按机制 / 正文模式 / 机制×模式 分组
  py -3 scripts/title_feedback.py --report

  # 看全部记录
  py -3 scripts/title_feedback.py --list

存储: 环境变量 TITLE_FEEDBACK_FILE, 默认 <CORPUS_DIR>/reports/title_feedback.jsonl
人味分: 给了 --draft 就自动算(需要本机装有 hualong skill), 也可以直接用 --human-score 指定。
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
BODY_MODES = ["tech", "human"]


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
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def auto_human_score(draft_path, mode=""):
    """调用 hualong 的体检器算人味分。给了 --body-mode 就按该模式算, 否则两模式取高(会偏高)。

    交付时的口径是"按声明的模式算", 所以回填也要用同一个口径, 否则记录会失真。
    """
    candidates = [os.environ.get("HUALONG_SKILL_DIR"),
                  Path.home() / ".codex" / "skills" / "hualong",
                  Path.home() / ".codex" / "skills" / "hualong" / "1.0.0"]
    for c in candidates:
        if not c:
            continue
        script = Path(c) / "scripts" / "style_check.py"
        if not script.exists():
            continue
        try:
            sys.path.insert(0, str(script.parent))
            import style_check as sc
            prose, steps = sc.parse(Path(draft_path))
            if not prose:
                return None
            m = sc.measure(prose, steps)
            if mode in ("tech", "human"):
                return sc.human_score(m, mode)[0]
            return max(sc.human_score(m, "tech")[0], sc.human_score(m, "human")[0])
        except Exception:
            return None
    return None


def add(path, args):
    # 数据合理性: 不合理的数据会污染复盘, 直接拒绝
    problems = []
    if args.impressions < 0 or args.clicks < 0 or args.likes < 0:
        problems.append("曝光/点击/点赞不能是负数")
    if args.impressions and args.clicks > args.impressions:
        problems.append(f"点击数({args.clicks})大于曝光数({args.impressions})")
    if args.read_through is not None and not (0 <= args.read_through <= 1):
        problems.append(f"完读率应在 0–1 之间,当前 {args.read_through}")
    if problems and not args.force:
        print("[拒绝记录] 数据不合理:")
        for p in problems:
            print(f"  - {p}")
        print("  确认数据无误可以加 --force 强制记录。")
        sys.exit(2)

    score = args.human_score
    if score is None and args.draft:
        score = auto_human_score(args.draft, args.body_mode)
        if score is None:
            print("[提示] 没能自动算人味分(缺 --draft 或本机没有 hualong),可手动加 --human-score")
    row = {
        "date": args.date or date.today().isoformat(),
        "platform": args.platform or "",
        "title": args.title,
        "category": args.category or "",
        "mechanism": args.mechanism or "",
        "body_mode": args.body_mode or "",
        "human_score": score,
        "impressions": args.impressions,
        "clicks": args.clicks,
        "likes": args.likes,
        "comments": args.comments,
        "read_through": args.read_through,
        "notes": args.notes or "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    ctr = f"{row['clicks'] / row['impressions'] * 100:.2f}%" if row["impressions"] else "-"
    print(f"已记录: {row['title'][:30]} | 曝光 {row['impressions']} 点击率 {ctr} 赞 {row['likes']}"
          + (f" 人味分 {score}" if score is not None else ""))
    print(f"文件: {path}")


def ctr_of(r):
    imp, clk = r.get("impressions") or 0, r.get("clicks") or 0
    return clk / imp if imp else None


def group_stats(rows, key_fn):
    groups = defaultdict(list)
    for r in rows:
        groups[key_fn(r) or "未标注"].append(r)
    out = []
    for k, g in groups.items():
        ctrs = [c for c in (ctr_of(r) for r in g) if c is not None]
        rts = [r["read_through"] for r in g if r.get("read_through")]
        out.append({"key": k, "n": len(g),
                    "ctr_med": round(st.median(ctrs), 4) if ctrs else None,
                    "likes_med": st.median([r.get("likes") or 0 for r in g]) if g else 0,
                    "read_med": round(st.median(rts), 3) if rts else None,
                    "score_med": st.median([r["human_score"] for r in g if r.get("human_score")]) if any(r.get("human_score") for r in g) else None})
    return sorted(out, key=lambda x: -(x["ctr_med"] or 0))


def fmt_table(groups, extra=False):
    head = "| 分组 | 条数 | 点击率中位 | 点赞中位 |" + (" 完读率中位 | 人味分中位 |" if extra else "")
    lines = [head, "| --- | --- | --- | --- |" + (" --- | --- |" if extra else "")]
    for g in groups:
        ctr = f"{g['ctr_med']*100:.2f}%" if g["ctr_med"] is not None else "-"
        row = f"| {g['key']} | {g['n']} | {ctr} | {g['likes_med']:.0f} |"
        if extra:
            rt = f"{g['read_med']*100:.1f}%" if g["read_med"] is not None else "-"
            sc_ = f"{g['score_med']:.0f}" if g["score_med"] is not None else "-"
            row += f" {rt} | {sc_} |"
        lines.append(row)
    return lines


def report(path, as_json=False):
    rows = load(path)
    if not rows:
        print("还没有回填记录。发一篇之后这样记:")
        print('  py -3 scripts/title_feedback.py --add --title "标题" --platform 公众号 \\')
        print('      --category "⑥批判冲突金句" --mechanism 立场 --body-mode tech --draft 草稿.md \\')
        print('      --impressions 12000 --clicks 900 --likes 120 --read-through 0.42')
        return 0

    payload = {
        "n": len(rows), "file": str(path),
        "by_mechanism": group_stats(rows, lambda r: r.get("mechanism")),
        "by_body_mode": group_stats(rows, lambda r: r.get("body_mode")),
        "by_category": group_stats(rows, lambda r: r.get("category")),
        "by_combo": group_stats(rows, lambda r: (f"{r.get('mechanism') or '未标注'} × {r.get('body_mode') or '未标注'}")),
    }
    ranked = sorted([r for r in rows if ctr_of(r) is not None], key=lambda r: -ctr_of(r))
    payload["top_by_ctr"] = [{"title": r["title"], "ctr": round(ctr_of(r), 4), "likes": r.get("likes")}
                             for r in ranked[:5]]

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"# 文章效果复盘(共 {len(rows)} 条)")
    print()
    for title, key in [("按传播机制", "by_mechanism"), ("按正文模式", "by_body_mode"),
                       ("按公式类别", "by_category")]:
        print(f"## {title}")
        print()
        print("\n".join(fmt_table(payload[key])))
        print()
    combos = [g for g in payload["by_combo"] if g["n"] >= 2]
    print("## 机制 × 正文模式(只显示 ≥2 条的组合)")
    print()
    print("\n".join(fmt_table(combos, extra=True)) if combos else "样本还不够,至少每个组合 2 条。")
    print()
    if payload["top_by_ctr"]:
        print("## 点击率最高的 5 条")
        print()
        for r in payload["top_by_ctr"]:
            print(f"- {r['ctr']*100:.2f}% | {r['title'][:40]}")
        print()
    small = [g for g in payload["by_combo"] if g["n"] < 3]
    if small:
        print(f"> 提示:有 {len(small)} 个组合少于 3 条,先别据此下结论;攒到每条 3 条以上再调配额。")
    else:
        best = payload["by_combo"][0]
        print(f"> 目前最好的组合是「{best['key']}」({best['ctr_med']*100:.2f}%,n={best['n']}),"
              f"下一批可以向它倾斜。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--title")
    ap.add_argument("--platform", default="")
    ap.add_argument("--category", default="", help='公式类型, 如 "⑥批判冲突金句"')
    ap.add_argument("--mechanism", choices=MECHANISMS, default="")
    ap.add_argument("--body-mode", choices=BODY_MODES, default="", help="tech=技术文, human=人文文")
    ap.add_argument("--human-score", type=int, default=None)
    ap.add_argument("--draft", default="", help="草稿路径, 给了就自动算人味分")
    ap.add_argument("--impressions", type=int, default=0)
    ap.add_argument("--clicks", type=int, default=0)
    ap.add_argument("--likes", type=int, default=0)
    ap.add_argument("--comments", type=int, default=0)
    ap.add_argument("--read-through", type=float, default=None, help="完读率, 0–1")
    ap.add_argument("--date", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--force", action="store_true", help="数据被判定不合理时仍然记录")
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
                  f"{r.get('body_mode','')} | {r.get('category','')} | {r['title'][:40]}")
        return 0
    return report(path, args.json)


if __name__ == "__main__":
    sys.exit(main())
