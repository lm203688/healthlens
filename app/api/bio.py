"""外部参考数据库 API — 结构生物学 / 化学信息学 / 同源性检索

设计取舍（有意为之，不要"优化"掉）：

1. **读接口全部公开**（不要求登录）。
   这些是纯公开科学数据，不含任何用户信息；要求登录只会阻碍演示、SEO
   与 B 端联调。写接口（CADD 作业执行）必须登录且限流更严。

2. **错误一律结构化返回**，`detail` 里带机器可读的 `code`。
   上层据此决定提示语，不靠字符串匹配。

3. **BLAST 拆成 submit / status / result 三步**。
   公共队列实测可能排队数小时（blastp+swissprot RTOE≈34,000s），
   同步接口会把请求挂死。`/blast/run` 只是给脚本的便利封装，默认 180s 超时。

4. **AlphaFold 与 RCSB 的语义严格分开**。
   预测结构不得计入实验证据等级。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.auth import conditional_limit
from app.api.deps import get_current_user
from app.connectors.reference import (
    ERROR_CODES,
    ReferenceError,
    describe_target,
    get_source,
    list_sources,
    probe_all,
)
from app.connectors.reference.schrodinger import MODULES, SchrodingerCADD
from app.models.user import User

router = APIRouter(tags=["生物医学数据源"])

_STATUS_MAP = {
    "invalid_input": 400,
    "not_found": 404,
    "rate_limited": 429,
    "timeout": 504,
    "license_unavailable": 501,
    "not_implemented": 501,
    "network_error": 502,
    "upstream_error": 502,
    "parse_error": 502,
}


def _http(exc: ReferenceError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS_MAP.get(exc.code, 502),
        detail=exc.to_dict(),
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PdbSearchRequest(BaseModel):
    text: str | None = Field(None, description="全文检索词（标题/摘要等）")
    method: str | None = Field(
        None,
        description="实验方法完整名，区分大小写：X-RAY DIFFRACTION / ELECTRON MICROSCOPY / SOLUTION NMR",
    )
    max_resolution: float | None = Field(None, gt=0, le=20, description="分辨率上限（Å），越小越清晰")
    organism: str | None = Field(None, description="来源物种学名片段，如 Homo sapiens")
    released_after: str | None = Field(None, description="发布日期下界，ISO 日期 YYYY-MM-DD")
    limit: int = Field(25, ge=1, le=100)
    start: int = Field(0, ge=0)


class SimilarRequest(BaseModel):
    smiles: str = Field(..., min_length=1, description="查询 SMILES")
    threshold: int = Field(95, ge=1, le=100, description="Tanimoto 相似度阈值（%）")
    limit: int = Field(50, ge=1, le=200)


class BlastSubmitRequest(BaseModel):
    sequence: str = Field(..., min_length=7, description="核酸或蛋白序列（自动去空白）")
    program: str = Field("blastn", description="blastn / blastp / blastx / tblastn / tblastx")
    database: str = Field("core_nt", description="目标数据库")
    hitlist_size: int = Field(10, ge=1, le=100)
    megablast: bool = Field(True, description="核酸比对时启用 megablast（更快）")


class BlastRunRequest(BlastSubmitRequest):
    timeout_s: float = Field(180.0, ge=10, le=900, description="同步等待上限；超时返回 RID 供后续取")


class CaddJobRequest(BaseModel):
    module: str = Field(..., description=f"模块名，可用：{sorted(MODULES)}")
    args: list[str] = Field(default_factory=list, description="原样传给该模块的命令行参数")
    workdir: str | None = Field(None, description="工作目录（产物落在这里）")
    timeout_s: float = Field(3600.0, ge=10, le=86400)


# ---------------------------------------------------------------------------
# 数据源自描述
# ---------------------------------------------------------------------------

@router.get("/sources", summary="列出全部外部数据源与能力")
@conditional_limit("30/minute")
async def list_reference_sources(
    request: Request,
    probe: bool = Query(False, description="true 时并发探活（会增加时延）"),
) -> dict[str, Any]:
    if probe:
        result = await probe_all()
        return {"success": True, "data": result, "error_codes": ERROR_CODES}
    caps = [cap.__dict__ for cap in list_sources()]
    return {"success": True, "data": {"capabilities": caps}, "error_codes": ERROR_CODES}


# ---------------------------------------------------------------------------
# RCSB PDB
# ---------------------------------------------------------------------------

@router.get("/pdb/{pdb_id}", summary="PDB 条目完整描述（元数据 + 实体 + 配体）")
@conditional_limit("60/minute")
async def get_pdb_entry(request: Request, pdb_id: str) -> dict[str, Any]:
    try:
        data = await get_source("rcsb_pdb").describe(pdb_id)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.post("/pdb/search", summary="RCSB 全库检索（多条件 AND）")
@conditional_limit("20/minute")
async def search_pdb(request: Request, body: PdbSearchRequest) -> dict[str, Any]:
    try:
        data = await get_source("rcsb_pdb").search(
            text=body.text,
            method=body.method,
            max_resolution=body.max_resolution,
            organism=body.organism,
            released_after=body.released_after,
            limit=body.limit,
            start=body.start,
        )
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.get("/pdb/by-uniprot/{accession}", summary="按 UniProt 号列出已解析结构")
@conditional_limit("40/minute")
async def pdb_by_uniprot(
    request: Request, accession: str, limit: int = Query(25, ge=1, le=100)
) -> dict[str, Any]:
    try:
        data = await get_source("rcsb_pdb").search_by_uniprot(accession, limit=limit)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


# ---------------------------------------------------------------------------
# PubChem
# ---------------------------------------------------------------------------

@router.get("/compound", summary="化合物查询（名称 / SMILES / InChIKey 自动识别）")
@conditional_limit("60/minute")
async def get_compound(request: Request, q: str = Query(..., min_length=1)) -> dict[str, Any]:
    try:
        data = await get_source("pubchem").describe(q)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.get("/compound/{cid}", summary="按 CID 取计算属性")
@conditional_limit("60/minute")
async def get_compound_properties(request: Request, cid: int) -> dict[str, Any]:
    try:
        data = await get_source("pubchem").properties(cid)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.get("/compound/{cid}/synonyms", summary="按 CID 取同义词与 CAS 号")
@conditional_limit("60/minute")
async def get_compound_synonyms(request: Request, cid: int) -> dict[str, Any]:
    try:
        data = await get_source("pubchem").synonyms(cid)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.post("/compound/similar", summary="2D 指纹相似性搜索（Tanimoto）")
@conditional_limit("10/minute")
async def search_similar_compounds(request: Request, body: SimilarRequest) -> dict[str, Any]:
    try:
        data = await get_source("pubchem").similar(
            body.smiles, threshold=body.threshold, limit=body.limit
        )
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


# ---------------------------------------------------------------------------
# NCBI BLAST
# ---------------------------------------------------------------------------

@router.post("/blast", summary="提交比对任务，立即返回 RID（推荐）")
@conditional_limit("5/minute")
async def submit_blast(request: Request, body: BlastSubmitRequest) -> dict[str, Any]:
    try:
        data = await get_source("ncbi_blast").submit(
            body.sequence,
            program=body.program,
            database=body.database,
            hitlist_size=body.hitlist_size,
            megablast=body.megablast,
        )
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {
        "success": True,
        "data": data,
        "next": {
            "status": f"/api/v1/bio/blast/{data['rid']}/status",
            "result": f"/api/v1/bio/blast/{data['rid']}/result",
        },
    }


@router.get("/blast/{rid}/status", summary="查询比对任务状态")
@conditional_limit("60/minute")
async def blast_status(request: Request, rid: str) -> dict[str, Any]:
    try:
        data = await get_source("ncbi_blast").status(rid)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.get("/blast/{rid}/result", summary="取比对结果（任务未完成时报错，不返回空）")
@conditional_limit("30/minute")
async def blast_result(request: Request, rid: str) -> dict[str, Any]:
    try:
        data = await get_source("ncbi_blast").fetch(rid)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.post("/blast/run", summary="提交并同步等待结果（脚本用，勿在网页主流程调用）")
@conditional_limit("3/minute")
async def run_blast(request: Request, body: BlastRunRequest) -> dict[str, Any]:
    try:
        data = await get_source("ncbi_blast").run(
            body.sequence,
            program=body.program,
            database=body.database,
            hitlist_size=body.hitlist_size,
            megablast=body.megablast,
            timeout_s=body.timeout_s,
        )
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


# ---------------------------------------------------------------------------
# UniProt / AlphaFold
# ---------------------------------------------------------------------------

@router.get("/protein/gene/{symbol}", summary="基因符号 → UniProt 登录号")
@conditional_limit("30/minute")
async def resolve_gene(
    request: Request, symbol: str, organism_id: int = Query(9606, ge=1)
) -> dict[str, Any]:
    try:
        data = await get_source("uniprot").resolve_gene(symbol, organism_id=organism_id)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.get("/protein/{accession}", summary="UniProt 条目元数据")
@conditional_limit("60/minute")
async def get_protein(request: Request, accession: str) -> dict[str, Any]:
    try:
        data = await get_source("uniprot").entry(accession)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.get("/structure/predicted/{accession}", summary="AlphaFold 预测结构（非实验证据）")
@conditional_limit("30/minute")
async def get_predicted_structure(request: Request, accession: str) -> dict[str, Any]:
    try:
        data = await get_source("alphafold").predictions(accession)
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


@router.get("/target/{gene_symbol}", summary="靶点全景：基因 → 蛋白 → 实验结构 + 预测结构")
@conditional_limit("20/minute")
async def get_target(
    request: Request,
    gene_symbol: str,
    organism_id: int = Query(9606, ge=1),
    max_structures: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    try:
        data = await describe_target(
            gene_symbol, organism_id=organism_id, max_structures=max_structures
        )
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data}


# ---------------------------------------------------------------------------
# Schrödinger（需许可，必须登录）
# ---------------------------------------------------------------------------

@router.get("/cadd/capabilities", summary="CADD 套件能力探测（是否安装、哪些模块可用）")
@conditional_limit("30/minute")
async def cadd_capabilities(request: Request) -> dict[str, Any]:
    data = await SchrodingerCADD().capabilities()
    return {"success": True, "data": data}


@router.post("/cadd/jobs", summary="执行 CADD 作业（需许可 + 登录）")
@conditional_limit("5/minute")
async def run_cadd_job(
    request: Request,
    body: CaddJobRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        data = await SchrodingerCADD().run_job(
            body.module, body.args, workdir=body.workdir, timeout_s=body.timeout_s
        )
    except ReferenceError as exc:
        raise _http(exc) from exc
    return {"success": True, "data": data, "executed_by": str(current_user.id)}