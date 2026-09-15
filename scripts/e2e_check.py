#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端回归: 一次跑完正文与标题的全部检查, 并和基线对比。

用法:
  py -3 scripts/e2e_check.py --update-baseline   # 首次记录基线
  py -3 scripts/e2e_check.py                     # 日常回归(有回归会返回非零)

夹具: tests/fixtures/*.md(首行标题, 其余正文)+ tests/fixtures.json(模式与平台)
依赖: 本机装有 hualong 与 dianjing 两个 skill(或用 HUALONG_SKILL_DIR / DIANJING_SKILL_DIR 指定)
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HUALONG = os.environ.get("HUALONG_SKILL_DIR") or Path.home() / ".codex" / "skills" / "hualong"
DEFAULT_DIANJING = os.environ.get("DIANJING_SKILL_DIR") or Path.home() / ".codex" / "skills" / "dianjing"


def load_modules(hualong_dir, dianjing_dir):
    for d, name in [(hualong_dir, "hualong"), (dianjing_dir, "dianjing")]:
        if not Path(d).exists():
            print(f"[错误] 找不到 {name} skill 目录: {d}")
            print("       用 HUALONG_SKILL_DIR / DIANJING_SKILL_DIR 指定,或先安装另一个 skill。")
            sys.exit(2)
    sys.path.insert(0, str(Path(hualong_dir) / "scripts"))
    sys.path.insert(0, str(Path(dianjing_dir) / "scripts"))
    try:
        import style_check
        import overlap_check
        import promise_check
        import title_overlap_check
    except ImportError as e:
        print(f"[错误] 加载检查模块失败: {e}")
        print("       端到端回归需要同时装好 hualong 与 dianjing 两个 skill。")
        sys.exit(2)
    return style_check, overlap_check, promise_check, title_overlap_check


def run_case(fixture, manifest, mods, corpus, index):
    style_check, overlap_check, promise_check, title_overlap_check = mods
    text = Path(fixture).read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].strip()
    body = "\n".join(lines[1:])
    mode = manifest.get("mode", "tech")

    prose, steps = style_check.parse(Path(fixture))
    metrics = style_check.measure(prose, steps)
    score, reasons = style_check.human_score(metrics, mode)
    style_fail = [name for name, s, _, _ in style_check.check(metrics, mode) if s == "FAIL"]

    max_len, _, _ = overlap_check.scan(body, corpus)
    overlap_verdict = overlap_check.verdict_for(max_len, len(overlap_check.normalize(body)))

    p = promise_check.check(title, body)

    index_titles = title_overlap_check.load_index(index)
    t = title_overlap_check.check(title, index_titles)

    return {
        "fixture": Path(fixture).name, "title": title, "mode": mode,
        "style": {"verdict": "FAIL" if style_fail else "PASS", "score": score,
                  "fail_items": style_fail, "notes": reasons},
        "overlap": {"verdict": overlap_verdict, "max_match": max_len},
        "promise": {"verdict": p["verdict"], "cover_all": p["cover_all"],
                    "num_cover": p["num_cover"], "reasons": p["reasons"]},
        "title_overlap": {"verdict": t["verdict"], "max_match": t["length"]},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_DIR", str(ROOT.parent / "writing-corpus")))
    ap.add_argument("--index", default=str(DEFAULT_DIANJING / "references" / "title_index.md"))
    args = ap.parse_args()

    manifest_path = ROOT / "tests" / "fixtures.json"
    baseline_path = ROOT / "tests" / "baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mods = load_modules(DEFAULT_HUALONG, DEFAULT_DIANJING)

    results = []
    for item in manifest["fixtures"]:
        fp = ROOT / "tests" / "fixtures" / item["file"]
        if not fp.exists():
            print(f"[跳过] 找不到夹具 {fp}")
            continue
        results.append(run_case(fp, item, mods, args.corpus, args.index))

    payload = {"corpus": args.corpus, "index": args.index, "results": results}

    if args.update_baseline:
        baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"基线已更新: {baseline_path}")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    old = {r["fixture"]: r for r in (baseline or {}).get("results", [])}

    print("| 夹具 | 模式 | 人味分 | 风格 | 重合 | 承诺兑现 | 标题查重 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    regressions, mismatches = [], []
    for r in results:
        print(f"| {r['fixture']} | {r['mode']} | {r['style']['score']} | {r['style']['verdict']} "
              f"| {r['overlap']['verdict']}({r['overlap']['max_match']}字) "
              f"| {r['promise']['verdict']}({r['promise']['cover_all']:.0%}) | {r['title_overlap']['verdict']} |")
        expect = item_expect = None
        for item in manifest["fixtures"]:
            if item["file"] == r["fixture"]:
                item_expect = item.get("expect") or {}
        for key in ["style", "overlap", "promise", "title_overlap"]:
            want = (item_expect or {}).get(key)
            if want and r[key]["verdict"] != want:
                mismatches.append(f"{r['fixture']} / {key}: 期望 {want},实际 {r[key]['verdict']}")
        o = old.get(r["fixture"])
        if o:
            for key in ["style", "overlap", "promise", "title_overlap"]:
                if o[key]["verdict"] != r[key]["verdict"]:
                    regressions.append(f"{r['fixture']} / {key}: {o[key]['verdict']} → {r[key]['verdict']}")
            if r["style"]["score"] < o["style"]["score"] - 3:
                regressions.append(f"{r['fixture']} / 人味分: {o['style']['score']} → {r['style']['score']}")
            if abs(r["promise"]["cover_all"] - o["promise"]["cover_all"]) > 0.05:
                regressions.append(f"{r['fixture']} / 覆盖率: {o['promise']['cover_all']:.0%} → {r['promise']['cover_all']:.0%}")

    print()
    if mismatches:
        print("## 不符合预期")
        for f in mismatches:
            print(f"- {f}")
    if regressions:
        print("## 回归(与基线相比变差)")
        for x in regressions:
            print(f"- {x}")
    if not mismatches and not regressions:
        print("全部通过,与基线一致。")
    sys.exit(1 if (mismatches or regressions) else 0)


if __name__ == "__main__":
    main()
