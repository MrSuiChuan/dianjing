#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知乎专栏正文批量采集脚本
=========================
用途: 先用知乎 API 拉出指定账号的全部文章 id,
      标题对齐参考清单, 再批量采集正文到 contents/。

用法:
  # 首次: 拉取文章 id 列表, 生成 titles.json
  python3 crawl_articles.py --build-index

  # 查看当前状态和剩余数量
  python3 crawl_articles.py --status

  # 采集下一批 8 篇 (默认)
  python3 crawl_articles.py --batch

  # 采集指定批次大小
  python3 crawl_articles.py --batch --size 16

  # 采集所有剩余文章
  python3 crawl_articles.py --all

  # 验证已采集结果 (连续性/重复/覆盖率)
  python3 crawl_articles.py --verify

依赖:
  pip install requests markdownify

注意:
  - 需要登录态: 环境变量 ZHIHU_COOKIE
  - 采集目标: 环境变量 ZHIHU_MEMBER (知乎账号 token)
  - 数据目录: 环境变量 CORPUS_DIR (默认 <仓库同级>/writing-corpus)
  - 文件名格式: {3位编号}_{id}_{截断标题去Windows非法字符}.md
  - 编号从 001 起严格连续递增, 不跳号
  - 标题优先用参考清单里的写法
"""

import argparse
import json
import re
import os
import sys
import time
from pathlib import Path
from collections import Counter

# ============================================================
# 配置 (按需修改)
# ============================================================

BASE_DIR = Path(os.environ.get("CORPUS_DIR")
                or (Path(__file__).resolve().parent.parent.parent / "writing-corpus"))
TITLES_JSON = BASE_DIR / "titles.json"
CONTENTS_DIR = BASE_DIR / "contents"
REFERENCE_MD = Path(os.environ.get("CORPUS_TITLE_INDEX")
                    or (Path(__file__).resolve().parent.parent / "references" / "title_index.md"))
MEMBER_TOKEN = os.environ.get("ZHIHU_MEMBER", "")
MEMBER_ARTICLES_API = "https://www.zhihu.com/api/v4/members/{token}/articles"
ARTICLE_API = "https://zhuanlan.zhihu.com/api/articles/{aid}"
JSON_KEY = "articles"
TITLE_TRUNCATE = 38
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')
DEFAULT_BATCH_SIZE = 8

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.zhihu.com/",
}
if os.environ.get("ZHIHU_COOKIE"):
    REQUEST_HEADERS["Cookie"] = os.environ["ZHIHU_COOKIE"]
REQUEST_TIMEOUT = 30
RETRY_MAX = 3
RETRY_DELAY = 3


# ============================================================
# 工具函数
# ============================================================

def load_articles():
    with open(TITLES_JSON, encoding="utf-8") as f:
        return json.load(f)[JSON_KEY]


def get_unique_articles():
    articles = load_articles()
    seen, unique = set(), []
    for a in articles:
        aid = str(a["id"])
        if aid in seen:
            continue
        seen.add(aid)
        unique.append(a)
    return unique


def get_crawled_ids():
    crawled = set()
    if not CONTENTS_DIR.exists():
        return crawled
    for fp in CONTENTS_DIR.glob("*.md"):
        m = re.match(r"^(\d{3})_(\d+)_", fp.name)
        if m:
            crawled.add(m.group(2))
    return crawled


def get_crawled_nums():
    nums = []
    if not CONTENTS_DIR.exists():
        return nums
    for fp in CONTENTS_DIR.glob("*.md"):
        m = re.match(r"^(\d{3})_", fp.name)
        if m:
            nums.append(int(m.group(1)))
    nums.sort()
    return nums


def sanitize_title(title):
    t = title.replace("\n", " ").strip()
    t = ILLEGAL_CHARS.sub("", t)
    return t[:TITLE_TRUNCATE]


def make_filename(num, aid, title):
    return f"{num:03d}_{aid}_{sanitize_title(title)}.md"


def normalize_title(title):
    t = re.sub(r"\s+", "", title or "")
    t = re.sub(r"[「」《》\"'“”‘’,，。.!！?？:：;；()（）\[\]【】\-—_~、·|/\\]", "", t)
    return t.lower()


def load_reference_titles():
    """读取 references/title_index.md 的标题清单, 返回 {规范化标题: 原文标题}。"""
    if not REFERENCE_MD.exists():
        print(f"[警告] 找不到参考文件: {REFERENCE_MD}")
        return {}
    refs = {}
    for line in REFERENCE_MD.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("- "):
            continue
        s = s[2:].strip()
        if s:
            refs.setdefault(normalize_title(s), s)
    return refs


def format_markdown(article, body_text, url):
    title = article.get("title", "").replace("\n", " ").strip()
    return "\n".join([title, "", f"> 原文链接: {url}", "", body_text.strip(), ""])


# ============================================================
# 采集核心
# ============================================================

def api_get_json(url, quiet=False):
    import requests
    for attempt in range(RETRY_MAX):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (403, 429):
                if not quiet:
                    print(f"  [{resp.status_code}] 被限流, 重试 {attempt+1}/{RETRY_MAX}")
                time.sleep(RETRY_DELAY * (attempt + 1) * 2)
            else:
                if not quiet:
                    print(f"  [{resp.status_code}] HTTP 错误")
                time.sleep(RETRY_DELAY)
        except Exception as e:
            if not quiet:
                print(f"  [异常] {type(e).__name__}: {e}")
            time.sleep(RETRY_DELAY)
    return None


def html_to_markdown(html):
    from markdownify import markdownify
    return markdownify(html or "", heading_style="ATX").strip()


def build_index():
    """拉取指定账号的全部文章 id, 标题对齐参考清单后写入 titles.json。"""
    print(f"=== 拉取文章列表 (成员: {MEMBER_TOKEN}) ===")
    if not MEMBER_TOKEN:
        print("[错误] 请先用环境变量 ZHIHU_MEMBER 指定知乎账号 token")
        return 1
    all_articles, offset = [], 0
    while True:
        url = MEMBER_ARTICLES_API.format(token=MEMBER_TOKEN) + f"?limit=20&offset={offset}"
        data = api_get_json(url)
        if not data:
            print("[错误] 文章列表拉取失败 (检查 ZHIHU_COOKIE)")
            return 1
        items = data.get("data", [])
        if not items:
            break
        all_articles.extend(items)
        totals = (data.get("paging") or {}).get("totals")
        print(f"  已获取 {len(all_articles)}/{totals}")
        if (data.get("paging") or {}).get("is_end") or len(all_articles) >= (totals or 0):
            break
        offset += len(items)
        time.sleep(0.4)

    refs = load_reference_titles()
    seen, out, matched = set(), [], 0
    for a in all_articles:
        aid = str(a.get("id"))
        if not aid or aid in seen:
            continue
        seen.add(aid)
        zt = (a.get("title") or "").replace("\n", " ").strip()
        rt = refs.get(normalize_title(zt))
        if rt:
            matched += 1
        out.append({
            "id": aid,
            "title": rt or zt,
            "zhihu_title": zt,
            "matched": bool(rt),
            "url": f"https://zhuanlan.zhihu.com/p/{aid}",
            "created": a.get("created"),
            "updated": a.get("updated"),
            "voteup_count": a.get("voteup_count"),
            "comment_count": a.get("comment_count"),
        })

    payload = {"source": "zhihu.com/api/v4/members/{token}/articles",
               "reference": str(REFERENCE_MD),
               "count": len(out),
               "matched": matched,
               "articles": out}
    TITLES_JSON.parent.mkdir(parents=True, exist_ok=True)
    TITLES_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"唯一文章: {len(out)} 篇, 命中参考标题: {matched} 篇")
    print(f"已写入 {TITLES_JSON}")
    return 0


def fetch_and_save(article, num):
    aid = str(article["id"])
    url = f"https://zhuanlan.zhihu.com/p/{aid}"
    print(f"  [{num:03d}] 抓取 {url}")
    data = api_get_json(ARTICLE_API.format(aid=aid))
    if not data or not data.get("content"):
        print(f"  [{num:03d}] 正文获取失败")
        return False
    body = html_to_markdown(data["content"])
    if len(body) < 50:
        print(f"  [{num:03d}] 正文过短, 跳过")
        return False

    fname = make_filename(num, aid, article.get("title") or data.get("title", ""))
    (CONTENTS_DIR / fname).write_text(format_markdown(article, body, url), encoding="utf-8")
    print(f"  [{num:03d}] 已保存 {fname}")
    return True


def crawl_batch(size=DEFAULT_BATCH_SIZE):
    CONTENTS_DIR.mkdir(parents=True, exist_ok=True)
    crawled = get_crawled_ids()
    nums = get_crawled_nums()
    max_num = max(nums) if nums else 0

    seen, candidates = set(), []
    for a in get_unique_articles():
        aid = str(a["id"])
        if aid in crawled or aid in seen:
            continue
        seen.add(aid)
        candidates.append(a)
        if len(candidates) >= size:
            break

    if not candidates:
        print("全部文章已采集完毕!")
        return 0

    print(f"准备采集 {len(candidates)} 篇 (编号 {max_num+1} 起)")
    success = 0
    for i, article in enumerate(candidates):
        num = max_num + 1 + i
        if fetch_and_save(article, num):
            success += 1
        time.sleep(1.2)

    total = len(get_unique_articles())
    print(f"\n本轮: 成功 {success}/{len(candidates)}, 累计 {len(crawled) + success}/{total}")
    return success


def crawl_all():
    total = 0
    while True:
        n = crawl_batch(size=20)
        if n == 0:
            break
        total += n
        print("--- 等待 3 秒 ---\n")
        time.sleep(3)
    print(f"\n全部完成! 共采集 {total} 篇")


# ============================================================
# 状态与验证
# ============================================================

def show_status():
    crawled = get_crawled_ids()
    nums = get_crawled_nums()
    unique_count = len(get_unique_articles())

    print("=== 知乎专栏采集状态 ===")
    print(f"标题源: {TITLES_JSON}")
    print(f"正文目录: {CONTENTS_DIR}")
    print(f"已采集: {len(crawled)} / {unique_count}")
    if nums:
        print(f"编号范围: {nums[0]:03d} - {nums[-1]:03d}")
        gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in set(nums)]
        print(f"编号缺口: {'NONE (连续)' if not gaps else gaps[:20]}")
    dup = {k: v for k, v in Counter(nums).items() if v > 1} if nums else {}
    print(f"重复编号: {'NONE' if not dup else dup}")
    print(f"剩余未抓: {unique_count - len(crawled)}")
    if nums and len(crawled) < unique_count:
        print(f"进度: {len(crawled)/unique_count*100:.1f}%")


def verify():
    crawled = get_crawled_ids()
    nums = get_crawled_nums()
    src_ids = set(a["id"] for a in get_unique_articles())

    print("=== 完整验证 ===")
    print(f"文件数: {len(nums)}")
    print(f"唯一 id: {len(crawled)} / {len(src_ids)}")
    if nums:
        gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in set(nums)]
        print(f"编号缺口: {'✅ NONE' if not gaps else f'❌ {gaps[:20]}'}")
        dup = {k: v for k, v in Counter(nums).items() if v > 1}
        print(f"重复编号: {'✅ NONE' if not dup else f'❌ {dup}'}")

    missing = src_ids - crawled
    print(f"id 覆盖率: {'✅ 100%' if not missing else f'❌ 缺失 {len(missing)} 个'}")

    placeholders = [fp.name for fp in CONTENTS_DIR.glob("*.md") if fp.read_text(encoding="utf-8").startswith("[抓取待补]")]
    if placeholders:
        print(f"⚠️  占位文件: {placeholders}")

    if not gaps and not dup and not missing and not placeholders:
        print(f"\n🎉 验证通过! {len(src_ids)} 篇全部采集完成!")


def export_urls():
    crawled = get_crawled_ids()
    nums = get_crawled_nums()
    max_num = max(nums) if nums else 0
    seen, s = set(), []
    for a in get_unique_articles():
        aid = str(a["id"])
        if aid in crawled or aid in seen:
            continue
        seen.add(aid)
        num = max_num + 1 + len(s)
        s.append(f"{num:03d}_{aid}_{sanitize_title(a['title'])}.md | http://zhuanlan.zhihu.com/p/{aid}")

    if not s:
        print("全部已采集!")
        return
    output = BASE_DIR / "remaining_urls.txt"
    output.write_text("\n".join(s), encoding="utf-8")
    print(f"已导出 {len(s)} 条 URL 到 {output}")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="知乎专栏正文批量采集脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 crawl_articles.py --status            # 查看状态
  python3 crawl_articles.py --batch             # 采集下一批 8 篇
  python3 crawl_articles.py --batch --size 16   # 采集 16 篇
  python3 crawl_articles.py --all               # 采集全部剩余
  python3 crawl_articles.py --verify            # 验证完成度
  python3 crawl_articles.py --build-index       # 重新生成标题清单
        """,
    )
    parser.add_argument("--build-index", action="store_true", help="拉取文章 id 列表并生成标题清单")
    parser.add_argument("--status", action="store_true", help="显示当前采集状态")
    parser.add_argument("--batch", action="store_true", help=f"采集下一批 (默认 {DEFAULT_BATCH_SIZE} 篇)")
    parser.add_argument("--size", type=int, default=DEFAULT_BATCH_SIZE, help="批次大小")
    parser.add_argument("--all", action="store_true", help="采集全部剩余文章")
    parser.add_argument("--verify", action="store_true", help="验证已采集结果")
    parser.add_argument("--export-urls", action="store_true", help="导出未采集文章的 URL 列表")

    args = parser.parse_args()

    if args.build_index:
        sys.exit(build_index())

    if not TITLES_JSON.exists():
        print(f"[错误] 找不到标题清单: {TITLES_JSON}")
        print("       请先运行 --build-index, 或用 CORPUS_DIR 指定目录。")
        sys.exit(1)

    if not os.environ.get("ZHIHU_COOKIE") and (args.batch or args.all):
        print("[错误] 缺少 ZHIHU_COOKIE 环境变量, 无法抓取正文。")
        sys.exit(1)

    if args.status:
        show_status()
    elif args.batch:
        crawl_batch(size=args.size)
    elif args.all:
        crawl_all()
    elif args.verify:
        verify()
    elif args.export_urls:
        export_urls()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
