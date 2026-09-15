#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成标题速查文件: Top100 + 按传播机制精选 + 按公式类别速查。

数据来源两处:
  - references/title_index.md 里的"按原赞数排序"章节(历史头部, 权威)
  - <corpus>/reports/votes.json(实时赞数快照, 覆盖 442/623 篇)

用法: py -3 scripts/build_title_index.py [--corpus DIR] [--out FILE]
"""
import argparse
import json
import re
from pathlib import Path

import analyze_titles as at

ROOT = Path(__file__).resolve().parent.parent

MECHANISM_RULES = [
    ("立场", ["真相", "劝你", "别急着", "最正确", "最伟大", "正在摧毁", "正在杀死", "该不该", "不值得",
              "我觉得", "我认为", "居然", "反而", "这事", "最大的"]),
    ("情绪", ["杀死", "绞杀", "摧毁", "毁灭", "崩塌", "消亡", "破防", "再见", "告别", "焦虑", "绝望",
              "崩溃", "心疼", "黑暗森林", "垃圾场", "谄媚", "投毒", "战争", "魔幻", "离谱", "死了", "凉了"]),
    ("信息差", ["实测", "一手", "试完", "我发现", "揭秘", "盘点", "整理", "评测", "教程", "攻略",
                "研究", "报告", "数据", "拆解", "对比", "深度", "全解析", "看懂", "扫盲", "实测"]),
    ("利益", ["免费", "白嫖", "省", "便宜", "价格", "多少钱", "成本", "效率", "保姆", "零基础",
              "上手", "速通", "神器", "必备", "好用", "推荐", "替代", "省钱", "打包", "合集"]),
    ("身份共鸣", ["我们", "打工人", "程序员", "年轻人", "博主", "创业者", "普通人", "斜杠青年",
                  "开发者", "上班人", "小白", "新手", "所有人", "每个"]),
]


def pick_mechanism(title):
    for name, kws in MECHANISM_RULES:
        if any(k in title for k in kws):
            return name
    return "其他"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT.parent / "writing-corpus"))
    ap.add_argument("--index", default=str(ROOT / "references" / "title_index.md"))
    ap.add_argument("--out", default=str(ROOT / "references" / "title_index_top100.md"))
    args = ap.parse_args()

    sections, top_section, all_titles = at.parse_index(Path(args.index))
    votes_path = Path(args.corpus) / "reports" / "votes.json"
    votes = json.loads(votes_path.read_text(encoding="utf-8")) if votes_path.exists() else {}
    ranked = sorted([v for v in votes.values() if v.get("voteup") is not None],
                    key=lambda v: -v["voteup"])

    def norm(t):
        return re.sub(r"[\s，。！？；：、,\.!?;:]+", "", t or "")

    seen = {norm(t) for t in top_section}
    merged = list(top_section)
    for v in ranked:
        t = (v.get("title") or "").strip()
        if not t or norm(t) in seen:
            continue
        seen.add(norm(t))
        merged.append(t)
        if len(merged) >= 100:
            break
    top100 = merged[:100]

    by_mech = {}
    for t in all_titles:
        by_mech.setdefault(pick_mechanism(t), []).append(t)
    by_cat = {c: [] for c in at.CATEGORY_RULES}
    for t in all_titles:
        hits = [c for c, kws in at.CATEGORY_RULES.items() if any(k in t for k in kws)]
        hits += [c for c, pat in at.CATEGORY_REGEX.items() if re.search(pat, t)]
        for c in hits:
            by_cat.setdefault(c, []).append(t)

    L = ["# 标题速查(Top100 + 分类精选)", "",
         "> 生成标题时**默认只读本文件**;需要核对更多真实措辞时,再 grep 全量索引 `title_index.md`(610 条)。", "",
         f"> 数据:第一部分 = 原赞数头部 ∪ 实时赞数快照(覆盖 {len(votes)}/{len(all_titles) + 13} 篇,快照时间 2026-09);",
         "> 第二、三部分按关键词规则从 610 条全量里筛选,每类只给代表性样本,不是全集。", "",
         "## 一、按赞数 Top100", ""]
    for i, t in enumerate(top100, 1):
        L.append(f"{i}. {t}")
    L += ["", "## 二、按传播机制精选", "",
          "机制决定读者为什么点开。配额是 5 种机制各 2 条,从这里找同一机制的真实措辞。", ""]
    for name in ["信息差", "身份共鸣", "利益", "情绪", "立场"]:
        items = by_mech.get(name, [])[:10]
        L.append(f"### {name}(共 {len(by_mech.get(name, []))} 条)")
        L.append("")
        L += [f"- {t}" for t in items] or ["- (无)"]
        L.append("")
    L += ["## 三、按公式类别速查", ""]
    for c in at.CATEGORY_RULES:
        items = by_cat.get(c, [])[:10]
        L.append(f"### {c}(共 {len(by_cat.get(c, []))} 条)")
        L.append("")
        L += [f"- {t}" for t in items] or ["- (无)"]
        L.append("")

    out = Path(args.out)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Top100: {len(top100)} 条(原榜 {len(top_section)} + 快照补 {len(top100) - len(top_section)})")
    print("机制分布: " + json.dumps({k: len(v) for k, v in by_mech.items()}, ensure_ascii=False))
    print("类别分布: " + json.dumps({k: len(v) for k, v in by_cat.items()}, ensure_ascii=False))
    print(f"输出: {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
