#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""段落节奏与高频用词测量: 长段/短段交替、结尾节拍、口语标记频率。"""
import json
import re
import statistics as st
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parent.parent.parent / "writing-corpus"
IMPORT_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
STEP = re.compile(r"(?:^\s*\*\*\d+[.、]|^\s*\d+[.、]\s|第[一二三四五六七八九十]步)")
TECH_TITLE = re.compile(r"教程|保姆|实测|评测|从0开始|从0到1|从零|怎么|如何|上手|安装|部署|"
                        r"工作流|插件|Prompt|skill|Skill|开源|工具|API|Agent|模型|编程|代码|解析|盘点|对比")
HUMAN_TITLE = re.compile(r"故事|导演|研究员|辞职|去世|破防|回忆|告别|时代|组织|创业|年轻人|"
                         r"为什么|聊聊|心得|思考|真相|感受|经历|朋友|孩子|父母|人物")
MARKERS = ["其实", "直接", "就是", "居然", "真的", "反正", "说白了", "讲道理", "所以呢",
           "然后呢", "毕竟", "但是", "所以", "然后", "这玩意", "这货", "哥们", "大家",
           "咱们", "我觉得", "我认为", "说实话", "离谱", "绝了", "牛逼", "崩溃", "爽"]
PARTICLES = ["吧", "呢", "嘛", "啊", "呀", "哦", "哈", "了"]


def parse_paras(fp):
    lines = fp.read_text(encoding="utf-8").splitlines()
    title = lines[0].strip()
    prose, in_code = [], False
    for raw in lines[1:]:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip():
            continue
        if line.lstrip().startswith("#") or line.lstrip().startswith(">") or line.strip().startswith("|"):
            continue
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s", line):
            continue
        line = IMPORT_RE.sub("", line)
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        t = re.sub(r"[`*_\[\]()]", "", line).strip()
        if re.search(r"[\u4e00-\u9fff]", t) and len(t) >= 2:
            prose.append(t)
    return title, prose


def main():
    tech, human, allp = [], [], []
    marker_counts, particle_counts = Counter(), Counter()
    for fp in sorted((BASE / "contents").glob("*.md")):
        title, prose = parse_paras(fp)
        if not prose:
            continue
        text = "".join(prose)
        for k in MARKERS:
            marker_counts[k] += text.count(k)
        for k in PARTICLES:
            particle_counts[k] += text.count(k)
        lens = [len(p) for p in prose]
        short_ratio = sum(1 for x in lens if x <= 20) / len(lens)
        long_ratio = sum(1 for x in lens if x >= 60) / len(lens)
        # 长段(>=60字)后紧跟短段(<=25字)的比例
        long_idx = [i for i, x in enumerate(lens) if x >= 60]
        after_short = sum(1 for i in long_idx if i + 1 < len(lens) and lens[i + 1] <= 25)
        rhythm = after_short / len(long_idx) if long_idx else 0
        # 连续短段的平均长度(节拍感)
        runs, cur = [], 0
        for x in lens:
            if x <= 25:
                cur += 1
            else:
                if cur:
                    runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        rec = {"lens": lens, "rhythm": rhythm, "mean_short_run": sum(runs) / len(runs) if runs else 0,
               "short_ratio": short_ratio, "long_ratio": long_ratio,
               "p90": sorted(lens)[int(len(lens) * 0.9)], "p95": sorted(lens)[min(len(lens) - 1, int(len(lens) * 0.95))],
               "max": max(lens), "first": lens[0], "last": lens[-1]}
        allp.append(rec)
        if (len([1 for raw in fp.read_text(encoding="utf-8").splitlines() if STEP.search(raw)]) >= 3) and TECH_TITLE.search(title):
            tech.append(rec)
        elif HUMAN_TITLE.search(title) and not STEP.search(fp.read_text(encoding="utf-8")):
            human.append(rec)

    def agg(group, key):
        vals = [r[key] for r in group]
        return round(st.median(vals), 1) if vals else None

    out = {"n_all": len(allp), "n_tech": len(tech), "n_human": len(human),
           "median_p90": {"all": agg(allp, "p90"), "tech": agg(tech, "p90"), "human": agg(human, "p90")},
           "median_p95": {"all": agg(allp, "p95"), "tech": agg(tech, "p95"), "human": agg(human, "p95")},
           "median_max": {"all": agg(allp, "max"), "tech": agg(tech, "max"), "human": agg(human, "max")},
           "rhythm_long_then_short": {"all": agg(allp, "rhythm"), "tech": agg(tech, "rhythm"), "human": agg(human, "rhythm")},
           "mean_short_run": {"all": agg(allp, "mean_short_run"), "tech": agg(tech, "mean_short_run"), "human": agg(human, "mean_short_run")},
           "long_ratio": {"all": agg(allp, "long_ratio"), "tech": agg(tech, "long_ratio"), "human": agg(human, "long_ratio")},
           "first_para": {"all": agg(allp, "first"), "tech": agg(tech, "first"), "human": agg(human, "first")},
           "last_para": {"all": agg(allp, "last"), "tech": agg(tech, "last"), "human": agg(human, "last")},
           "markers_top30": marker_counts.most_common(30),
           "particles_top10": particle_counts.most_common(10)}
    (BASE / "reports").mkdir(parents=True, exist_ok=True)
    (BASE / "reports" / "rhythm_metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("markers_top30", "particles_top10")}, ensure_ascii=False))
    print("markers=" + json.dumps(marker_counts.most_common(15), ensure_ascii=False))
    print("particles=" + json.dumps(particle_counts.most_common(8), ensure_ascii=False))


if __name__ == "__main__":
    main()
