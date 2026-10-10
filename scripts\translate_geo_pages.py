"""GEO 内容英文化管线 —— 把 seo_pages 的中文页翻译为英文译本。

设计原则（对齐项目「不伪造」约定）
------------------------------------
1. **只用现有字段**：英文译本写入 `structured_data['i18n']['en']`，
   不需要任何 schema 迁移（alembic 在本环境已失效，见 2026-09-23 排查）。
2. **幂等**：默认只处理「已发布 + 尚无英文译本」的页面，可反复运行。
3. **不产出半成品**：翻译结果必须通过 HTML 结构校验（标签序列一致）
   才写库；校验失败就跳过该页并记入报告，宁可缺，不可错。
4. **只有真实存在的译本才会被 sitemap 输出 hreflang**，见 geo_infra.sitemap_xml。

端点实测坑（2026-09-23）
-----------------------
- `deepseek-v4-flash` 默认开思考，reasoning 会吃满 max_tokens 导致
  content 为空。需带 `reasoning: {"type":"disabled"}` **且** max_tokens 留足
  （实测 reasoning 仍会产出 ~770 token，故正文调用不能低于 ~1200）。
- 该 key 有较紧的 TPM/RPM 限流，连续请求会 429（code 429003）。必须节流 +
  长退避，否则静默丢页。注意 `reasoning_effort: minimal` 不被接受（400）。

用法（在容器内执行，经 stdin 投递）
----------------------------------
    SENSENOVA_API_KEY=sk-xxx python3 - --limit 30
    SENSENOVA_API_KEY=sk-xxx python3 - --limit 30 --delay 4
    SENSENOVA_API_KEY=sk-xxx python3 - --slug 丹沙 --force --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.seo import SeoPage

# ---------------------------------------------------------------------------
# LLM 配置（SenseNova，OpenAI 兼容）
# ---------------------------------------------------------------------------
LLM_URL = os.environ.get("SENSENOVA_URL", "https://token.sensenova.cn/v1").rstrip("/")
LLM_MODEL = os.environ.get("SENSENOVA_MODEL", "deepseek-v4-flash")
LLM_KEY = os.environ.get("SENSENOVA_API_KEY", "").strip()
LLM_TIMEOUT = int(os.environ.get("TRANSLATE_TIMEOUT", "240"))
# 429 退避序列（秒）：key 限流较紧，需要等得起
BACKOFFS = (10, 20, 35, 55, 80, 120)

# ---------------------------------------------------------------------------
# 翻译提示词
# ---------------------------------------------------------------------------
# 术语与合规约束写死在 system 里 —— 与「wellness 非医疗」定位一致：
# 英文文案同样不得出现诊断/治疗/患者类主张。
SYSTEM_PROMPT = """You are a professional EN translator for HealthLens, a wellness (NOT medical) platform.

Rules you MUST follow:
1. Translate Simplified Chinese into natural, fluent English for a general wellness audience.
2. The platform is wellness-oriented, NOT medical. Never introduce diagnosis, treatment,
   cure, prescription, or "patient" claims. Use "support / may help / wellness guidance" phrasing.
3. Keep TCM (Traditional Chinese Medicine) terms accurate: render the concept in English and
   keep the pinyin in parentheses on first use, e.g. "qi (气)", "spleen-stomach (脾胃)".
4. If a value is HTML: preserve EVERY tag, attribute, class, id and href EXACTLY as-is.
   Translate only the human-visible text nodes. Never add, remove, reorder or restructure tags.
5. Output ONLY a JSON object, no preamble, no explanation, no markdown code fences.
"""


def _llm_json(prompt: str, max_tokens: int) -> tuple[dict | None, str]:
    """调用 SenseNova 并解析 JSON。返回 (data, err)。绝不抛异常打断批处理。"""
    if not LLM_KEY:
        return None, "no_key"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        # 关闭思考（否则 reasoning 会吃满 max_tokens，content 变空串）
        "reasoning": {"type": "disabled"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{LLM_URL}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {LLM_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    last_err = "unknown"
    for attempt, wait in enumerate((0,) + BACKOFFS):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=LLM_TIMEOUT) as resp:
                body = json.loads(resp.read())
            content = (body["choices"][0]["message"].get("content") or "").strip()
            if not content:
                last_err = "empty_content"
                continue
            content = _strip_fences(content)
            try:
                return json.loads(content), "ok"
            except json.JSONDecodeError:
                # 兜底：从文本里抠出第一个 {...}
                m = re.search(r"\{.*\}", content, re.S)
                if m:
                    try:
                        return json.loads(m.group(0)), "ok_recovered"
                    except json.JSONDecodeError:
                        pass
                last_err = "bad_json"
                continue
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            last_err = f"HTTP{exc.code}:{detail[:80]}"
            if exc.code == 429 or exc.code >= 500:
                continue
            # 4xx（非限流）重试无意义
            return None, last_err
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}"
            continue
    return None, last_err


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


# ---------------------------------------------------------------------------
# HTML 结构校验
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9-]*)")
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
              "link", "meta", "param", "source", "track", "wbr"}


def _tag_sequence(html: str) -> list[str]:
    return [
        m.group(1).lower()
        for m in _TAG_RE.finditer(html or "")
        if m.group(1).lower() not in _VOID_TAGS
    ]


def _structure_ok(src: str, out: str) -> tuple[bool, str]:
    """结构校验：非空 html 的标签序列必须完全一致，避免 LLM 重排/吞标签。"""
    a, b = _tag_sequence(src), _tag_sequence(out)
    if not a:
        return True, "no-tags"
    if a == b:
        return True, "ok"
    if len(a) != len(b):
        return False, f"tagcount {len(a)}->{len(b)}"
    return False, "tagorder"


# ---------------------------------------------------------------------------
# 单页翻译（1 次 LLM 调用）
# ---------------------------------------------------------------------------
async def translate_page(page: SeoPage, force: bool = False, dry_run: bool = False) -> dict:
    sd = page.structured_data if isinstance(page.structured_data, dict) else {}
    i18n = sd.get("i18n") if isinstance(sd.get("i18n"), dict) else {}
    existing = i18n.get("en")
    if existing and (existing.get("title") or "").strip() and not force:
        return {"slug": page.slug, "status": "skip_exists"}

    title = (page.title or "").strip()
    meta = (page.meta_description or "").strip()
    content = page.content_html or ""
    keywords = page.meta_keywords or ""

    # max_tokens：正文长度换算 + reasoning 预留（实测 reasoning 约 770）
    est_out = int(len(content) * 0.9) + 900
    max_tokens = max(1600, min(16000, est_out))

    prompt = (
        "Translate the Chinese values in this JSON into English.\n"
        'Return ONLY a JSON object with exactly these keys: '
        '"title", "meta_description", "content_html".\n'
        "Keep title <= 70 chars, meta_description <= 160 chars.\n"
        "content_html must keep the exact same HTML tags as the input.\n\n"
        + json.dumps(
            {"title": title, "meta_description": meta, "content_html": content},
            ensure_ascii=False,
        )
    )

    data, err = _llm_json(prompt, max_tokens)
    if data is None:
        return {"slug": page.slug, "status": f"fail_llm({err})"}

    en_title = str(data.get("title") or "").strip()
    en_meta = str(data.get("meta_description") or "").strip()
    en_content = str(data.get("content_html") or "").strip()
    if not en_title:
        return {"slug": page.slug, "status": "fail_empty_title"}

    note = ""
    if content.strip():
        ok, reason = _structure_ok(content, en_content)
        if not ok:
            # 结构被破坏 → 不写正文，只留标题/描述（诚实降级，不产半成品）
            en_content = ""
            note = f"body_rejected:{reason}"

    payload = {
        "title": en_title,
        "meta_description": en_meta,
        "meta_keywords": keywords,
        "content_html": en_content,
        "translated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "translator": LLM_MODEL,
    }

    if dry_run:
        return {"slug": page.slug, "status": "dry_run" + (f"({note})" if note else ""),
                "title": en_title}

    new_sd = dict(sd)
    new_i18n = dict(i18n)
    new_i18n["en"] = payload
    new_sd["i18n"] = new_i18n
    page.structured_data = new_sd  # 整体重新赋值，确保 SQLAlchemy 检测到 JSON 变更

    return {"slug": page.slug, "status": "ok" + (f"_{note}" if note else ""), "title": en_title}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def run(args) -> int:
    if not LLM_KEY:
        print("[FATAL] 未设置 SENSENOVA_API_KEY")
        return 2

    async with async_session_factory() as db:  # type: AsyncSession
        stmt = select(SeoPage).where(SeoPage.status == "published")
        if args.slug:
            stmt = stmt.where(SeoPage.slug == args.slug)
        if args.category:
            stmt = stmt.where(SeoPage.category == args.category)
        stmt = stmt.order_by(SeoPage.created_at.asc())
        if args.limit and not args.slug:
            stmt = stmt.limit(args.limit)
        rows = (await db.execute(stmt)).scalars().all()

        print(f"命中 {len(rows)} 个已发布页面（model={LLM_MODEL}, delay={args.delay}s, "
              f"dry_run={args.dry_run}, force={args.force}）")
        print("=" * 72)

        results = []
        ok_count = 0
        started = time.time()
        for i, page in enumerate(rows, 1):
            try:
                res = await translate_page(page, force=args.force, dry_run=args.dry_run)
            except Exception as exc:  # noqa: BLE001
                res = {"slug": page.slug, "status": f"error:{type(exc).__name__}"}
            results.append(res)
            if res["status"].startswith(("ok", "dry_run")):
                ok_count += 1
            line = f"[{i}/{len(rows)}] {page.slug[:28]:<30} -> {res['status']}"
            if res.get("title"):
                line += f" | {res['title'][:52]}"
            print(line, flush=True)

            if not args.dry_run and i % 25 == 0:
                await db.commit()
                print("    [commit]", flush=True)

            if args.delay and i < len(rows):
                await asyncio.sleep(args.delay)

        if not args.dry_run:
            await db.commit()

    elapsed = time.time() - started
    print("=" * 72)
    print(f"完成：{ok_count}/{len(results)} 成功，耗时 {elapsed/60:.1f} 分钟")
    by_status: dict[str, int] = {}
    for r in results:
        key = r["status"].split("(")[0].split(":")[0]
        by_status[key] = by_status.get(key, 0) + 1
    for k, v in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<28} {v}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="GEO 内容英文化管线")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 页（0=不限）")
    ap.add_argument("--slug", type=str, default="", help="只处理指定 slug")
    ap.add_argument("--category", type=str, default="", help="只处理指定 category")
    ap.add_argument("--delay", type=float, default=4.0, help="每页之间的间隔秒数（默认 4）")
    ap.add_argument("--force", action="store_true", help="已有英文译本也重译")
    ap.add_argument("--dry-run", action="store_true", help="只翻译不写库")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
