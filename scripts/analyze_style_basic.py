#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""622 篇长文语料风格测量: 技术文 vs 人文文。

用法: py -3 scripts/analyze_style_basic.py [--base-dir DIR]
输出: <BASE_DIR>/reports/style_stats.json 与 style_report.md
"""
import argparse
import json
import math
import re
import statistics as st
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fff]")
IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
HEAD = re.compile(r"^\s*#{1,6}\s")
QUOTE = re.compile(r"^\s*>")
CODE_FENCE = re.compile(r"^\s*```")

TECH_KW = ["API", "SDK", "Prompt", "prompt", "token", "Token", "模型", "大模型", "部署", "代码",
           "参数", "开源", "GitHub", "Agent", "Claude", "GPT", "Gemini", "Cursor", "MCP",
           "微调", "训练", "推理", "教程", "步骤", "实测", "评测", "保姆", "工作流", "插件",
           "命令", "接口", "数据集", "模型权重", "上下文", "算力", "显卡", "本地部署",
           "安装", "配置", "调用", "框架", "编程", "开发者", "代码库", "知识库", "RAG"]
HUMAN_KW = ["故事", "人生", "情绪", "焦虑", "感动", "破防", "采访", "创业", "父母", "孩子",
            "青春", "回忆", "孤独", "命运", "遗憾", "告别", "深夜", "眼泪", "热爱", "朋友",
            "年轻人", "时代", "说实话", "感受", "经历", "那年", "想起", "我们这一代"]
TECH_TITLE = ["教程", "实测", "评测", "保姆", "从0到1", "从 0 到 1", "上手", "怎么", "如何",
              "开源", "安装", "部署", "工作流", "Prompt", "Agent", "模型", "工具", "插件",
              "API", "代码", "skill", "Skill", "GPT", "Claude", "Cursor", "MCP"]
HUMAN_TITLE = ["故事", "人生", "回忆", "告别", "时代", "真相", "为什么", "我们", "我", "思考",
               "心得", "感受", "对话", "采访", "年轻人", "组织", "创业", "AI组织"]


def strip_md(s):
    s = IMG.sub("", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[`*_>#\-\[\]()]", "", s)
    return s.strip()


def paragraphs_and_features(body):
    paras, prose_lens, sentences_in_prose = [], [], []
    in_code = False
    counts = {"headings": 0, "list_items": 0, "images": 0, "code_lines": 0, "quotes": 0, "table_lines": 0}
    for raw in body.splitlines():
        line = raw.rstrip()
        if CODE_FENCE.match(line):
            in_code = not in_code
            counts["code_lines"] += 1
            continue
        if in_code:
            counts["code_lines"] += 1
            continue
        if not line.strip():
            continue
        counts["images"] += len(IMG.findall(line))
        if HEAD.match(line):
            counts["headings"] += 1
            continue
        if LIST.match(line):
            counts["list_items"] += 1
            continue
        if QUOTE.match(line):
            counts["quotes"] += 1
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            counts["table_lines"] += 1
            continue
        if not CJK.search(line):
            continue
        text = strip_md(line)
        if len(text) < 2:
            continue
        paras.append(text)
        prose_lens.append(len(text))
        n_sent = len([x for x in re.split(r"[。！？!?…；;]+", text) if len(x.strip()) >= 2])
        sentences_in_prose.append(max(n_sent, 1))
    return paras, prose_lens, sentences_in_prose, counts


def score_keywords(text, kws, weight=1.0):
    return sum(text.count(k) for k in kws) * weight


def load_articles(base_dir):
    index = json.loads((base_dir / "titles.json").read_text(encoding="utf-8"))
    meta = {str(a["id"]): a for a in index["articles"]}
    rows = []
    for fp in sorted((base_dir / "contents").glob("*.md")):
        m = re.match(r"^(\d{3})_(\d+)_", fp.name)
        if not m:
            continue
        aid = m.group(2)
        text = fp.read_text(encoding="utf-8")
        lines = text.splitlines()
        title = (lines[0] if lines else "").strip()
        body = "\n".join(lines[1:])
        paras, prose_lens, sent_counts, counts = paragraphs_and_features(body)
        body_chars = sum(prose_lens)
        if not prose_lens:
            continue
        tech = score_keywords(body, TECH_KW) + score_keywords(title, TECH_TITLE, 1.5)
        hum = score_keywords(body, HUMAN_KW) + score_keywords(title, HUMAN_TITLE, 0.5)
        rows.append({
            "file": fp.name, "id": aid, "num": int(m.group(1)), "title": title,
            "chars": body_chars, "n_prose_paras": len(prose_lens),
            "para_med": st.median(prose_lens), "para_mean": sum(prose_lens) / len(prose_lens),
            "para_p25": sorted(prose_lens)[len(prose_lens) // 4],
            "para_p75": sorted(prose_lens)[(3 * len(prose_lens)) // 4],
            "sent_per_para": sum(sent_counts) / len(sent_counts),
            "tech_kw": tech, "human_kw": hum,
            "tech_density": tech / body_chars * 1000, "human_density": hum / body_chars * 1000,
            **{k: counts[k] for k in counts},
            "created": meta.get(aid, {}).get("created"),
            "voteup": meta.get(aid, {}).get("voteup_count"),
            "matched": meta.get(aid, {}).get("matched"),
        })
    return rows


def classify(rows):
    for r in rows:
        # 结构信号: 代码块/清单/小标题越多越偏技术
        tech_struct = r["code_lines"] * 3 + r["list_items"] * 0.6 + r["headings"] * 0.8
        hum_struct = r["quotes"] * 0.2
        r["tech_score"] = r["tech_kw"] + tech_struct
        r["human_score"] = r["human_kw"] + hum_struct
        t = r["tech_kw"] + tech_struct
        h = r["human_kw"] + hum_struct
        margin = (t - h) / max(r["chars"], 1) * 1000
        r["margin"] = margin
        if r["chars"] < 800:
            r["label"] = "短动态"
        elif r["code_lines"] >= 2 or (t >= 8 and t >= 2 * max(h, 1)):
            r["label"] = "技术"
        elif h >= 6 and h >= 2 * max(t, 1) and r["code_lines"] == 0 and r["list_items"] <= 2:
            r["label"] = "人文"
        else:
            r["label"] = "混合"
    return rows


def desc(vals):
    if not vals:
        return {}
    vals = sorted(vals)
    return {"n": len(vals), "mean": round(sum(vals) / len(vals), 1), "med": round(st.median(vals), 1),
            "p25": round(vals[len(vals) // 4], 1), "p75": round(vals[(3 * len(vals)) // 4], 1),
            "p10": round(vals[len(vals) // 10], 1), "p90": round(vals[(9 * len(vals)) // 10], 1)}


def cliffs_delta(a, b):
    """效果量: P(a>b)-P(a<b), 范围 [-1,1]。"""
    if not a or not b:
        return 0.0
    gt = lt = 0
    for x in a:
        for y in b:
            if x > y:
                gt += 1
            elif x < y:
                lt += 1
    return (gt - lt) / (len(a) * len(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default=str(Path(__file__).resolve().parent.parent.parent / "writing-corpus"))
    args = ap.parse_args()
    base = Path(args.base_dir)
    rows = classify(load_articles(base))

    groups = {}
    for lab in ["技术", "人文", "混合", "短动态"]:
        g = [r for r in rows if r["label"] == lab]
        groups[lab] = {
            "count": len(g),
            "chars": desc([r["chars"] for r in g]),
            "para_med": desc([r["para_med"] for r in g]),
            "sent_per_para": desc([r["sent_per_para"] for r in g]),
            "headings_per_1k": desc([r["headings"] / max(r["chars"], 1) * 1000 for r in g]),
            "list_per_1k": desc([r["list_items"] / max(r["chars"], 1) * 1000 for r in g]),
            "images_per_1k": desc([r["images"] / max(r["chars"], 1) * 1000 for r in g]),
            "quotes_per_1k": desc([r["quotes"] / max(r["chars"], 1) * 1000 for r in g]),
            "paras_per_1k": desc([r["n_prose_paras"] / max(r["chars"], 1) * 1000 for r in g]),
        }

    tech = [r for r in rows if r["label"] == "技术"]
    hum = [r for r in rows if r["label"] == "人文"]
    features = ["para_med", "para_mean", "sent_per_para", "chars", "n_prose_paras"]
    deltas = {f: round(cliffs_delta([r[f] for r in tech], [r[f] for r in hum]), 3) for f in features}
    densities = {
        "headings_per_1k": round(cliffs_delta([r["headings"] / max(r["chars"], 1) * 1000 for r in tech],
                                             [r["headings"] / max(r["chars"], 1) * 1000 for r in hum]), 3),
        "list_per_1k": round(cliffs_delta([r["list_items"] / max(r["chars"], 1) * 1000 for r in tech],
                                          [r["list_items"] / max(r["chars"], 1) * 1000 for r in hum]), 3),
        "images_per_1k": round(cliffs_delta([r["images"] / max(r["chars"], 1) * 1000 for r in tech],
                                            [r["images"] / max(r["chars"], 1) * 1000 for r in hum]), 3),
        "quotes_per_1k": round(cliffs_delta([r["quotes"] / max(r["chars"], 1) * 1000 for r in tech],
                                            [r["quotes"] / max(r["chars"], 1) * 1000 for r in hum]), 3),
    }

    out_dir = base / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"groups": groups, "cliffs_delta_tech_vs_human": deltas, "density_deltas": densities,
               "articles": rows}
    (out_dir / "style_stats.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 长文语料风格测量报告", "",
             f"样本: {len(rows)} 篇(来自 contents/, 明细见 style_stats.json)", ""]
    lines.append("## 一、分组规模")
    for lab, g in groups.items():
        lines.append(f"- {lab}: {g['count']} 篇")
    lines.append("")
    lines.append("## 二、各组关键指标(中位数 / p25-p75)")
    lines.append("")
    lines.append("| 组 | 篇数 | 正文中文字数 | 散文段落中位长度 | 段内句数 | 段落密度(每千字段数) | 小标题/千字 | 列表项/千字 | 配图/千字 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for lab, g in groups.items():
        if not g["count"]:
            continue
        lines.append("| {lab} | {n} | {chars} | {para} | {sent} | {ppk} | {h} | {l} | {img} |".format(
            lab=lab, n=g["count"],
            chars=f"{g['chars']['med']:.0f} ({g['chars']['p25']:.0f}-{g['chars']['p90']:.0f})",
            para=f"{g['para_med']['med']:.0f} ({g['para_med']['p25']:.0f}-{g['para_med']['p75']:.0f})",
            sent=f"{g['sent_per_para']['med']:.1f}",
            ppk=f"{g['paras_per_1k']['med']:.1f}",
            h=f"{g['headings_per_1k']['med']:.1f}", l=f"{g['list_per_1k']['med']:.1f}",
            img=f"{g['images_per_1k']['med']:.1f}"))
    lines += ["", "## 三、技术 vs 人文 的区分度(Cliff's delta, |值| 越大区分越强)", ""]
    for k, v in sorted({**deltas, **densities}.items(), key=lambda kv: -abs(kv[1])):
        lines.append(f"- {k}: {v}")
    lines += ["", "## 四、抽样标题(每类 8 条, 供人工核对分类质量)", ""]
    for lab in ["技术", "人文", "混合", "短动态"]:
        lines.append(f"### {lab}")
        for r in [x for x in rows if x["label"] == lab][:8]:
            lines.append(f"- ({r['para_med']:.0f}字/段) {r['title']}")
        lines.append("")
    (out_dir / "style_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"rows={len(rows)}")
    print("labels=" + json.dumps({k: v["count"] for k, v in groups.items()}, ensure_ascii=False))
    print("deltas=" + json.dumps({**deltas, **densities}, ensure_ascii=False))
    print(f"report={out_dir / 'style_report.md'}")


if __name__ == "__main__":
    main()
