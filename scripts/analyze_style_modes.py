#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""长文语料: 技术文 vs 人文文 的段落节奏测量(锚定样本版)。

策略: 不追求给 622 篇都贴标签, 而是用可解释规则圈出高置信"技术锚"与"人文锚",
      在锚定样本上比较段落节奏, 并做时间混淆检验。
输出: <BASE_DIR>/reports/mode_metrics.json 与 mode_report.md
"""
import argparse
import json
import re
import statistics as st
from pathlib import Path

IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
BOLD_LINE = re.compile(r"^\s*(?:\*\*|__)")
STEP = re.compile(r"(?:^\s*\*\*\d+[.、]|^\s*\d+[.、]\s|第[一二三四五六七八九十]步)")
TECH_TITLE = re.compile(r"教程|保姆|实测|评测|从0开始|从0到1|从零|怎么|如何|上手|安装|部署|"
                        r"工作流|插件|Prompt|skill|Skill|开源|工具|API|Agent|模型|编程|代码|解析|盘点|对比")
HUMAN_TITLE = re.compile(r"故事|导演|研究员|辞职|去世|破防|回忆|告别|时代|组织|创业|年轻人|"
                         r"为什么|聊聊|心得|思考|真相|感受|经历|朋友|孩子|父母|某个人|人物")
NARRATIVE = ["他说", "她说", "我记得", "当时", "后来", "那天", "有一天", "朋友", "眼泪",
             "哭", "笑", "感慨", "破防", "情绪", "命运", "孤独", "遗憾", "告别"]
COLLOQUIAL = ["其实", "直接", "就是", "居然", "真的", "反正", "说白了", "讲道理", "所以呢",
              "然后呢", "你", "大家", "咱们", "啊", "吧", "嘛", "呢"]


def strip_md(s):
    s = IMG.sub("", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return re.sub(r"[`*_>#\[\]()]", "", s).strip()


def parse(path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""
    body = lines[1:]
    prose, struct = [], {"headings": 0, "lists": 0, "images": 0, "code": 0, "steps": 0,
                         "bold": 0, "quotes": 0, "tables": 0}
    in_code = False
    for raw in body:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            struct["code"] += 1
            continue
        if in_code:
            continue
        if not line.strip():
            continue
        struct["images"] += len(IMG.findall(line))
        if line.lstrip().startswith("#"):
            struct["headings"] += 1
            continue
        if STEP.search(line):
            struct["steps"] += 1
        if BOLD_LINE.match(line):
            struct["bold"] += 1
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s", line):
            struct["lists"] += 1
            continue
        if line.lstrip().startswith(">"):
            continue
        if line.strip().startswith("|"):
            struct["tables"] += 1
            continue
        if not re.search(r"[\u4e00-\u9fff]", line):
            continue
        t = strip_md(line)
        if len(t) >= 2:
            prose.append(t)
    struct["quotes"] = len(re.findall(r"[「“][^」”]{4,}[」”]", "\n".join(body)))
    return title, prose, struct


def metrics(title, prose, struct):
    lens = [len(p) for p in prose]
    if not lens:
        return None
    n = len(lens)
    head = lens[:5]
    tail = lens[-3:]
    mid = lens[5:max(5, n - 3)] or lens
    sents = [len([x for x in re.split(r"[。！？!?…]+", p) if len(x.strip()) >= 2]) for p in prose]
    all_text = "".join(prose)
    chars = len(all_text)
    return {
        "title": title, "chars": chars, "n_paras": n,
        "para_med": st.median(lens), "para_mean": sum(lens) / n,
        "head_med": st.median(head), "mid_med": st.median(mid), "tail_med": st.median(tail),
        "short_ratio": sum(1 for x in lens if x <= 20) / n,
        "mid_ratio": sum(1 for x in lens if 21 <= x <= 60) / n,
        "long_ratio": sum(1 for x in lens if x > 60) / n,
        "sents_per_para": sum(sents) / n,
        "sentence_len": chars / max(sum(sents), 1),
        "colloquial_per_1k": sum(all_text.count(k) for k in COLLOQUIAL) / max(chars, 1) * 1000,
        "digits_per_1k": len(re.findall(r"\d", all_text)) / max(chars, 1) * 1000,
        "ellipsis_per_1k": (all_text.count("。。。") + all_text.count("…")) / max(chars, 1) * 1000,
        "images_per_1k": struct["images"] / max(chars, 1) * 1000,
        "steps": struct["steps"], "bold_per_1k": struct["bold"] / max(chars, 1) * 1000,
        "headings": struct["headings"], "lists": struct["lists"], "quotes": struct["quotes"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default=str(Path(__file__).resolve().parent.parent.parent / "writing-corpus"))
    args = ap.parse_args()
    base = Path(args.base_dir)
    index = json.loads((base / "titles.json").read_text(encoding="utf-8"))
    created = {str(a["id"]): a.get("created") for a in index["articles"]}

    rows = []
    for fp in sorted((base / "contents").glob("*.md")):
        m = re.match(r"^(\d{3})_(\d+)_", fp.name)
        if not m:
            continue
        title, prose, struct = parse(fp)
        mm = metrics(title, prose, struct)
        if mm:
            mm["id"] = m.group(2)
            mm["num"] = int(m.group(1))
            mm["created"] = created.get(m.group(2))
            rows.append(mm)

    tech = [r for r in rows if (r["steps"] >= 3 or r["headings"] >= 2) and TECH_TITLE.search(r["title"])]
    human = [r for r in rows if r["steps"] == 0 and r["headings"] == 0 and
             HUMAN_TITLE.search(r["title"]) and sum(r["title"].count(k) for k in []) == 0]
    human = [r for r in human if sum(1 for k in NARRATIVE if k in r["title"]) >= 0]

    keys = ["chars", "n_paras", "para_med", "para_mean", "head_med", "mid_med", "tail_med",
            "short_ratio", "mid_ratio", "long_ratio", "sents_per_para", "sentence_len",
            "colloquial_per_1k", "digits_per_1k", "ellipsis_per_1k", "images_per_1k",
            "bold_per_1k", "steps", "headings"]

    def summarise(group):
        out = {}
        for k in keys:
            vals = sorted(r[k] for r in group)
            if not vals:
                continue
            out[k] = {"med": round(st.median(vals), 2),
                      "p25": round(vals[len(vals) // 4], 2),
                      "p75": round(vals[(3 * len(vals)) // 4], 2)}
        return out

    report = {"n_total": len(rows), "n_tech": len(tech), "n_human": len(human),
              "all": summarise(rows), "tech": summarise(tech), "human": summarise(human),
              "tech_titles": [r["title"] for r in tech[:12]],
              "human_titles": [r["title"] for r in human[:12]]}

    # 时间混淆: 按 created 年份看段落中位长度
    by_year = {}
    for r in rows:
        if not r["created"]:
            continue
        import datetime
        y = datetime.datetime.fromtimestamp(r["created"]).year
        by_year.setdefault(y, []).append(r["para_med"])
    report["para_med_by_year"] = {y: round(st.median(v), 1) for y, v in sorted(by_year.items())}

    out_dir = base / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mode_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# 技术文 / 人文文 段落节奏测量", "",
         f"全量样本 {len(rows)} 篇; 技术锚 {len(tech)} 篇; 人文锚 {len(human)} 篇", "",
         "| 指标 | 全量 | 技术锚 | 人文锚 |", "| --- | --- | --- | --- |"]
    for k in keys:
        def fmt(g):
            d = report[g].get(k)
            return "-" if not d else f"{d['med']} ({d['p25']}-{d['p75']})"
        L.append(f"| {k} | {fmt('all')} | {fmt('tech')} | {fmt('human')} |")
    L += ["", "## 技术锚示例", ""] + [f"- {t}" for t in report["tech_titles"]]
    L += ["", "## 人文锚示例", ""] + [f"- {t}" for t in report["human_titles"]]
    L += ["", "## 按年份的段落中位长度", ""] + [f"- {y}: {v}" for y, v in report["para_med_by_year"].items()]
    (out_dir / "mode_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"rows={len(rows)} tech_anchor={len(tech)} human_anchor={len(human)}")
    print(f"report={out_dir / 'mode_report.md'}")


if __name__ == "__main__":
    main()
