#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取语料里每篇文章的赞数/评论数, 供标题效果分析使用。

用法:
  py -3 scripts/fetch_votes.py [--corpus DIR] [--workers 3]

依赖环境变量 ZHIHU_COOKIE。结果写入 <corpus>/reports/votes.json, 可断点续跑。
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ARTICLE_API = "https://zhuanlan.zhihu.com/api/articles/{aid}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.zhihu.com/",
}
LOCK = threading.Lock()


def fetch_one(aid, retries=4):
    for attempt in range(retries):
        try:
            r = requests.get(ARTICLE_API.format(aid=aid), headers=HEADERS, timeout=30)
            if r.status_code == 200:
                j = r.json()
                return {"voteup": j.get("voteup_count"), "comment": j.get("comment_count"),
                        "title": j.get("title"), "created": j.get("created"),
                        "updated": j.get("updated")}
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.environ.get("CORPUS_DIR", ""))
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    if not args.corpus:
        print("[错误] 需要 --corpus 或环境变量 CORPUS_DIR")
        sys.exit(2)
    cookie = os.environ.get("ZHIHU_COOKIE", "")
    if not cookie:
        print("[错误] 缺少 ZHIHU_COOKIE")
        sys.exit(2)
    HEADERS["Cookie"] = cookie

    corpus = Path(args.corpus)
    index = json.loads((corpus / "titles.json").read_text(encoding="utf-8"))
    out_path = corpus / "reports" / "votes.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    todo = [str(a["id"]) for a in index["articles"] if str(a["id"]) not in done]
    print(f"总数 {len(index['articles'])}, 已有 {len(done)}, 待抓 {len(todo)}")

    def save():
        out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, aid): aid for aid in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            aid = futures[fut]
            res = fut.result()
            with LOCK:
                if res and res.get("voteup") is not None:
                    done[aid] = res
                    ok += 1
                else:
                    fail += 1
                if i % 25 == 0:
                    save()
                    print(f"  进度 {i}/{len(todo)}, 成功 {ok}, 失败 {fail}")
            time.sleep(0.7 / max(args.workers, 1))
    save()
    print(f"完成: 成功 {ok}, 失败 {fail}, 累计 {len(done)} 条 -> {out_path}")


if __name__ == "__main__":
    main()
