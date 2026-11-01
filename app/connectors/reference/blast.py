"""NCBI BLAST 连接器 — 同源性检索（BLAST URL API）

上游：https://blast.ncbi.nlm.nih.gov/Blast.cgi

三个必须知道的实现事实（均已实测，2026-11-01）：

1. **JSON2 响应是 ZIP 包，不是纯 JSON。**
   `FORMAT_TYPE=JSON2` 返回的字节流以 `PK` 开头。里面有两个文件：
     - `<RID>.json`     → `{"BlastJSON": [{"File": "<RID>_1.json"}]}`（索引）
     - `<RID>_1.json`   → `{"BlastOutput2": {"report": {...}}}`（真正的报告）
   直接 `json.loads` 会失败。必须按索引里的 `File` 指针跳转。

2. **公共队列排队时间不可控。**
   同一时刻实测：blastn+core_nt 的 RTOE≈30 秒；blastp+swissprot 的 RTOE≈34,000 秒
   （约 9.7 小时）。因此本连接器**必须**拆成 submit / status / fetch 三步，
   不允许在 HTTP 请求里同步等待。`run()` 只是给脚本用的便利封装，且必须传超时。

3. **TOOL / EMAIL 参数必填。**
   NCBI 要求标明工具名与联系方式，缺失会被降级排队甚至拒绝。

限速：无 API key 3 req/s，有 key 10 req/s（`NCBI_API_KEY`）。
"""
from __future__ import annotations

import asyncio
import io
import re
import zipfile
from typing import Any

from app.connectors.reference.base import (
    ReferenceError,
    ReferenceSource,
    SourceCapability,
    as_list,
)

#: 支持的程序 → 合法数据库（只列常用，避免调用方传错被上游拒）
PROGRAMS = {
    "blastn": {"core_nt", "nt", "refseq_rna", "refseq_genomes", "wgs", "16S_ribosomal_RNA"},
    "blastp": {"nr", "refseq_protein", "swissprot", "pdb", "pat"},
    "blastx": {"nr", "refseq_protein", "swissprot", "pdb"},
    "tblastn": {"core_nt", "nt", "refseq_rna"},
    "tblastx": {"core_nt", "nt"},
}

_QINFO = re.compile(r"QBlastInfoBegin(.*?)QBlastInfoEnd", re.S)
_STATUS = re.compile(r"Status\s*=\s*(\w+)")


class NCBIBlast(ReferenceSource):
    SOURCE = "ncbi_blast"
    DISPLAY_NAME = "NCBI BLAST"
    BASE_URL = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"
    MIN_INTERVAL = 0.34  # 3 req/s（无 key）
    DEFAULT_TTL = 0.0  # 比对结果不进缓存（RID 本身就是句柄）
    DEFAULT_TIMEOUT = 90.0

    def __init__(self, api_key: str = "", email: str = "", tool: str = "healthlens") -> None:
        super().__init__()
        self.api_key = api_key
        self.email = email
        self.tool = tool
        if api_key:
            self._limiter = type(self._limiter)(0.11)  # 10 req/s

    # -- 提交 ---------------------------------------------------------------
    async def submit(
        self,
        sequence: str,
        *,
        program: str = "blastn",
        database: str = "core_nt",
        hitlist_size: int = 10,
        megablast: bool = True,
        word_size: int | None = None,
        expect: float | None = None,
    ) -> dict[str, Any]:
        seq = _clean_sequence(sequence)
        program = program.lower().strip()
        if program not in PROGRAMS:
            raise ReferenceError(
                "invalid_input", self.SOURCE, f"program 必须是 {sorted(PROGRAMS)} 之一"
            )
        if database not in PROGRAMS[program]:
            raise ReferenceError(
                "invalid_input",
                self.SOURCE,
                f"{program} 不支持数据库 {database!r}；可选 {sorted(PROGRAMS[program])}",
            )

        fields: dict[str, Any] = {
            "CMD": "Put",
            "PROGRAM": program,
            "DATABASE": database,
            "QUERY": seq,
            "FORMAT_TYPE": "JSON2",
            "HITLIST_SIZE": max(1, min(int(hitlist_size), 100)),
            "TOOL": self.tool,
        }
        if self.email:
            fields["EMAIL"] = self.email
        if self.api_key:
            fields["API_KEY"] = self.api_key
        if megablast and program in {"blastn", "blastx", "tblastn", "tblastx"}:
            fields["MEGABLAST"] = "on"
        if word_size:
            fields["WORD_SIZE"] = int(word_size)
        if expect is not None:
            fields["EXPECT"] = expect

        resp = await self._request("POST", self.BASE_URL, data=fields, accept="text/html")
        html = resp.text
        block = _QINFO.search(html)
        if not block:
            # 上游把错误写在页面里，把首段文本带出来便于排查
            hint = re.sub(r"<[^>]+>", " ", html)
            hint = re.sub(r"\s+", " ", hint).strip()[:400]
            raise ReferenceError("upstream_error", self.SOURCE, f"未拿到 RID：{hint}")

        body = block.group(1)
        rid = _extract(body, "RID")
        rtoe = _extract(body, "RTOE")
        if not rid:
            raise ReferenceError("upstream_error", self.SOURCE, f"QBlastInfo 无 RID：{body[:200]}")
        return {
            "rid": rid,
            "rtoe_seconds": int(rtoe) if rtoe and rtoe.isdigit() else None,
            "program": program,
            "database": database,
            "query_length": len(seq),
            "note": "RTOE 是上游估算的等待秒数，公共队列可能长达数小时",
            "source": self.SOURCE,
        }

    # -- 状态 ---------------------------------------------------------------
    async def status(self, rid: str) -> dict[str, Any]:
        resp = await self._request(
            "GET", self.BASE_URL, params={"CMD": "Get", "FORMAT_OBJECT": "SearchInfo", "RID": rid}
        )
        text = resp.text
        m = _STATUS.search(text)
        state = m.group(1) if m else "UNKNOWN"
        # NCBI 的三种正常态 + 失败态
        normalized = {
            "WAITING": "waiting",
            "READY": "ready",
            "UNKNOWN": "expired_or_unknown",
            "FAILED": "failed",
        }.get(state, state.lower())
        return {"rid": rid, "status": normalized, "raw_status": state, "source": self.SOURCE}

    # -- 取结果 -------------------------------------------------------------
    async def fetch(self, rid: str) -> dict[str, Any]:
        """取 JSON2 并解包解析。"""
        resp = await self._request(
            "GET", self.BASE_URL, params={"CMD": "Get", "FORMAT_TYPE": "JSON2", "RID": rid}
        )
        raw = resp.content
        if raw[:2] != b"PK":
            head = raw[:300].decode("utf-8", errors="replace")
            if "Status=WAITING" in head or "waiting" in head.lower():
                raise ReferenceError("upstream_error", self.SOURCE, "任务仍在排队，尚未出结果")
            raise ReferenceError("parse_error", self.SOURCE, f"期望 ZIP，实得: {head[:160]}")

        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise ReferenceError("parse_error", self.SOURCE, f"ZIP 解包失败: {exc}") from exc

        names = archive.namelist()
        index_name = next((n for n in names if n.endswith(".json") and "_" not in n.rsplit("/", 1)[-1]), None)
        report_names: list[str] = []
        if index_name:
            index = _load_json(archive, index_name)
            for entry in as_list(index.get("BlastJSON")):
                if isinstance(entry, dict) and entry.get("File"):
                    report_names.append(entry["File"])
        if not report_names:
            # 兜底：索引缺失时直接吃所有带 _ 的报告文件
            report_names = [n for n in names if n != index_name and n.endswith(".json")]

        reports = []
        for name in report_names:
            try:
                payload = _load_json(archive, name)
            except KeyError:
                continue
            node = payload.get("BlastOutput2")
            if isinstance(node, list):
                # 每个元素形如 {"report": {...}}
                reports.extend(
                    _parse_report(r.get("report", r) if isinstance(r, dict) else r) for r in node
                )
            elif isinstance(node, dict):
                reports.append(_parse_report(node.get("report", node)))

        if not reports:
            raise ReferenceError("parse_error", self.SOURCE, f"ZIP 内无可解析报告: {names}")
        return {
            "rid": rid,
            "reports": reports,
            "report_count": len(reports),
            "source": self.SOURCE,
            "source_url": f"https://blast.ncbi.nlm.nih.gov/Blast.cgi?CMD=Get&FORMAT_TYPE=JSON2&RID={rid}",
        }

    # -- 便利封装 -----------------------------------------------------------
    async def run(
        self,
        sequence: str,
        *,
        program: str = "blastn",
        database: str = "core_nt",
        hitlist_size: int = 10,
        timeout_s: float = 180.0,
        respect_rtoe: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """提交 → 轮询 → 取结果。

        仅供脚本/测试使用。**不要在同步 HTTP 请求里调用**：blastp/nr 这类
        任务可能排队数小时，会把请求挂死。Web 场景请用 submit + 客户端轮询。
        """
        submitted = await self.submit(
            sequence, program=program, database=database, hitlist_size=hitlist_size, **kwargs
        )
        rid = submitted["rid"]
        rtoe = submitted.get("rtoe_seconds") or 0
        # 尊重上游 RTOE，但最多等 30 秒再开始轮询（RTOE 常被高估）
        if respect_rtoe and rtoe > 0:
            await asyncio.sleep(min(rtoe, 30))

        deadline = asyncio.get_event_loop().time() + timeout_s
        delay = 3.0
        while asyncio.get_event_loop().time() < deadline:
            state = await self.status(rid)
            if state["status"] == "ready":
                result = await self.fetch(rid)
                result["submitted"] = submitted
                result["elapsed_poll"] = "ok"
                return result
            if state["status"] in {"failed", "expired_or_unknown"}:
                raise ReferenceError(
                    "upstream_error", self.SOURCE, f"任务状态 {state['raw_status']}（RID={rid}）"
                )
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 20.0)

        raise ReferenceError(
            "timeout",
            self.SOURCE,
            f"{timeout_s}s 内未完成；RID={rid} 仍可用 status/fetch 继续取结果"
            f"（上游估算 RTOE={rtoe}s）",
        )

    async def health(self) -> dict[str, Any]:
        resp = await self._request(
            "GET", self.BASE_URL, params={"CMD": "Info"}, accept="text/html"
        )
        return {"status": "ok", "bytes": len(resp.content)}

    def capability(self) -> SourceCapability:
        return SourceCapability(
            source=self.SOURCE,
            display_name=self.DISPLAY_NAME,
            base_url=self.BASE_URL,
            requires_key=False,
            key_present=bool(self.api_key),
            operations=["submit", "status", "fetch", "run"],
            rate_limit="3 req/s（有 NCBI_API_KEY 时 10 req/s）",
            notes="JSON2 为 ZIP 包装；公共队列 RTOE 可能达数小时，必须异步",
        )


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def _parse_report(report: dict[str, Any]) -> dict[str, Any]:
    search = ((report.get("results") or {}).get("search")) or {}
    hits = []
    for hit in as_list(search.get("hits")):
        desc = (as_list(hit.get("description")) or [{}])[0]
        hsps = []
        for hsp in as_list(hit.get("hsps")):
            hsps.append(
                {
                    "evalue": _to_float(hsp.get("evalue")),
                    "bit_score": _to_float(hsp.get("bit_score")),
                    "identity": hsp.get("identity"),
                    "align_length": hsp.get("align_len"),
                    "gaps": hsp.get("gaps"),
                    "query_range": [hsp.get("query_from"), hsp.get("query_to")],
                    "hit_range": [hsp.get("hit_from"), hsp.get("hit_to")],
                    "query_strand": hsp.get("query_strand"),
                    "hit_strand": hsp.get("hit_strand"),
                }
            )
        hits.append(
            {
                "accession": desc.get("accession"),
                "title": desc.get("title"),
                "taxid": hit.get("taxid"),
                "hsps": hsps,
                "best_evalue": min((h["evalue"] for h in hsps if h["evalue"] is not None), default=None),
                "best_bit_score": max(
                    (h["bit_score"] for h in hsps if h["bit_score"] is not None), default=None
                ),
            }
        )
    return {
        "program": report.get("program"),
        "version": report.get("version"),
        "database": ((report.get("search_target") or {}).get("db")),
        "query_id": ((report.get("query_ID") or report.get("query_id"))),
        "hit_count": len(hits),
        "hits": hits,
        "params": report.get("params"),
    }


def _load_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    import json

    return json.loads(archive.read(name).decode("utf-8"))


def _extract(block: str, key: str) -> str | None:
    m = re.search(rf"{key}\s*=\s*(\S+)", block)
    return m.group(1) if m else None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_sequence(sequence: str) -> str:
    seq = "".join((sequence or "").split())
    if not seq:
        raise ReferenceError("invalid_input", NCBIBlast.SOURCE, "序列为空")
    if len(seq) < 7:
        raise ReferenceError("invalid_input", NCBIBlast.SOURCE, "序列过短（<7）")
    if len(seq) > 100_000:
        raise ReferenceError("invalid_input", NCBIBlast.SOURCE, "序列过长（>100k），请用本地 BLAST+")
    bad = set(seq.upper()) - set("ACGTUNRYKMSWBDHVXEFILPQZ*-")
    if bad:
        raise ReferenceError(
            "invalid_input", NCBIBlast.SOURCE, f"序列含非法字符: {''.join(sorted(bad))[:20]}"
        )
    return seq
