"""基因组路由 - 基因数据上传、分析结果、药物基因组报告"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.genomics import PharmacogenomicProfile
from app.api.deps import get_current_user

router = APIRouter(tags=["genome"])


def _parse_genomic_file(content: bytes, filename: str) -> list[dict]:
    """基础 VCF/23andMe 格式解析"""
    variants = []
    text = content.decode("utf-8", errors="ignore")
    lines = text.strip().splitlines()

    # 已知的 PGx 相关基因
    PGX_GENES = {"CYP2D6", "CYP2C19", "CYP2C9", "CYP3A5", "VKORC1", "DPYD", "TPMT", "UGT1A1", "SLCO1B1", "CYP2B6"}

    is_vcf = filename.endswith(".vcf") or text.startswith("##")

    for line in lines:
        if is_vcf:
            if line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 8:
                chrom, pos, rsid, ref, alt, qual, filt, info = parts[:8]
                gene_match = None
                for gene in PGX_GENES:
                    if gene in info.upper():
                        gene_match = gene
                        break
                if gene_match:
                    gt_field = [x for x in info.split(";") if x.startswith("GT=")]
                    genotype = gt_field[0].split("=")[1] if gt_field else f"{ref}/{alt}"
                    variants.append({
                        "gene": gene_match,
                        "rsid": rsid,
                        "genotype": genotype,
                        "phenotype": "unknown",
                    })
        else:
            # 23andMe 格式: rsid chrom position genotype
            parts = line.strip().split("\t")
            if len(parts) >= 4 and parts[0].startswith("rs"):
                rsid = parts[0]
                # 尝试从注释行找基因信息（简化版）
                variants.append({
                    "gene": None,
                    "rsid": rsid,
                    "genotype": parts[3],
                    "phenotype": "unknown",
                })

    return variants


@router.post("/upload")
async def upload_genome(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传基因组数据(VCF/23andMe格式) - 解析并存储药物基因组学特征"""
    content = await file.read()

    # 解析 VCF/文本格式
    parsed_variants = _parse_genomic_file(content, file.filename)

    # 写入 PGx 表
    created_count = 0
    for variant in parsed_variants[:50]:  # 限制一次最多50条
        try:
            pgx = PharmacogenomicProfile(
                id=str(uuid.uuid4()),
                user_id=str(current_user.id),
                gene_symbol=variant.get("gene"),
                phenotype=variant.get("phenotype", "unknown"),
                variant_rsid=variant.get("rsid"),
                genotype=variant.get("genotype"),
                source=file.filename,
            )
            db.add(pgx)
            created_count += 1
        except Exception:
            continue

    if created_count > 0:
        await db.commit()

    return {
        "success": True,
        "data": {
            "filename": file.filename,
            "parsed_variants": created_count,
            "total_lines": len(content.decode("utf-8", errors="ignore").splitlines()),
            "message": f"Extracted {created_count} pharmacogenomic variants" if created_count else "No recognized PGx variants found",
        },
    }


@router.get("/profile", response_model=dict)
async def get_genome_profile(
    gene_symbol: str | None = Query(None, description="按基因符号筛选，如 CYP2D6"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取药物基因组分析结果 - 包含 PGx 引擎解读"""
    query = select(PharmacogenomicProfile).where(
        PharmacogenomicProfile.user_id == current_user.id
    )
    count_query = select(func.count()).select_from(PharmacogenomicProfile).where(
        PharmacogenomicProfile.user_id == current_user.id
    )
    if gene_symbol:
        query = query.where(PharmacogenomicProfile.gene_symbol == gene_symbol)
        count_query = count_query.where(PharmacogenomicProfile.gene_symbol == gene_symbol)

    result_count = await db.execute(count_query)
    total = result_count.scalar() or 0

    query = query.order_by(PharmacogenomicProfile.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    profiles = result.scalars().all()

    # 调用 PGx 引擎解读
    from app.core.pgx_engine import PGxEngine
    engine = PGxEngine()

    data = []
    for p in profiles:
        # 尝试解读基因型
        interpretation = None
        if p.gene_symbol and p.genotype:
            pgx_result = engine.interpret_genotype(p.gene_symbol, p.genotype)
            if pgx_result:
                interpretation = {
                    "phenotype": pgx_result.phenotype,
                    "activity_score": pgx_result.activity_score,
                    "drug_count": len(pgx_result.drug_recommendations),
                    "top_drugs": [d["drug_name"] for d in pgx_result.drug_recommendations[:3]],
                }
                # 更新数据库中的表型
                if p.phenotype == "unknown" or not p.phenotype:
                    p.phenotype = pgx_result.phenotype

        if interpretation:
            await db.commit()

        data.append({
            "id": str(p.id),
            "gene_symbol": p.gene_symbol,
            "phenotype": p.phenotype,
            "variant_rsid": p.variant_rsid,
            "genotype": p.genotype,
            "source": p.source,
            "interpretation": interpretation,
        })

    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/pgx", response_model=dict)
async def get_pgx_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取药物基因组(PGx)综合报告 - 含用药建议和相互作用风险"""
    result = await db.execute(
        select(PharmacogenomicProfile).where(
            PharmacogenomicProfile.user_id == current_user.id
        )
    )
    profiles = result.scalars().all()

    from app.core.pgx_engine import PGxEngine
    engine = PGxEngine()

    # 转换为引擎输入
    variants = []
    for p in profiles:
        if p.gene_symbol and p.genotype:
            variants.append({
                "gene": p.gene_symbol,
                "genotype": p.genotype,
                "rsid": p.variant_rsid,
            })

    # 分析基因型
    gene_results = await engine.analyze_user_genome(variants)

    # 获取药物相互作用
    interactions = engine.get_drug_interactions(variants)

    return {
        "success": True,
        "data": {
            "user_id": str(current_user.id),
            "analyzed_genes": gene_results,
            "drug_interactions": interactions,
            "risk_alerts": [
                {
                    "drug": i["drug"],
                    "gene": i["gene"],
                    "severity": i["severity"],
                    "advice": i["advice"],
                }
                for i in interactions if i["severity"] == "high"
            ],
            "summary": {
                "total_genes": len(gene_results),
                "abnormal_genes": sum(1 for g in gene_results if g.get("phenotype") != "NM"),
                "high_risk_drugs": sum(1 for i in interactions if i["severity"] == "high"),
            },
        },
    }
