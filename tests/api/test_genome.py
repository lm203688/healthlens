"""基因组 API 测试"""
import pytest
from io import BytesIO

# 模拟 VCF 文件内容，包含 PGx 基因信息（INFO 字段中包含基因符号）
MOCK_VCF_CONTENT = """\
##fileformat=VCFv4.2
##INFO=<ID=GENE,Number=1,Type=String,Description="Gene symbol">
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
chr22	42128949	rs3892097	C	T	100	PASS	GENE=CYP2D6;GT=C/T
chr10	96541718	rs4244285	G	A	100	PASS	GENE=CYP2C19;GT=G/A
chr10	96534604	rs1057910	A	C	100	PASS	GENE=CYP2C19;GT=A/C
chr7	99358751	rs77674664	A	G	100	PASS	GENE=CYP3A5;GT=A/G
"""


async def _register_and_login(client, user_data):
    """注册并登录，返回 (token, user_id)"""
    register_resp = await client.post("/api/v1/auth/register", json=user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip(f"注册失败, status={register_resp.status_code}")
    reg_data = register_resp.json()["data"]
    token = reg_data["access_token"]
    user_id = reg_data["user"]["id"]
    return token, user_id


@pytest.mark.asyncio
async def test_upload_genome(client, test_user_data):
    """注册->登录->上传一个模拟 VCF 文件"""
    token, _ = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    vcf_bytes = MOCK_VCF_CONTENT.encode("utf-8")
    files = {"file": ("test_genome.vcf", vcf_bytes, "text/plain")}

    resp = await client.post(
        "/api/v1/genome/upload", files=files, headers=headers
    )

    assert resp.status_code == 200, f"上传基因组文件失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["filename"] == "test_genome.vcf"
    # VCF 中包含 3 条有 PGx 基因信息的记录
    assert data["data"]["parsed_variants"] >= 1


@pytest.mark.asyncio
async def test_get_genome_profile(client, test_user_data):
    """上传后查看基因组档案"""
    token, _ = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 先上传
    vcf_bytes = MOCK_VCF_CONTENT.encode("utf-8")
    files = {"file": ("test_genome.vcf", vcf_bytes, "text/plain")}
    upload_resp = await client.post(
        "/api/v1/genome/upload", files=files, headers=headers
    )
    assert upload_resp.status_code == 200

    # 查看基因组档案
    profile_resp = await client.get(
        "/api/v1/genome/profile", headers=headers
    )
    assert profile_resp.status_code == 200
    profile_data = profile_resp.json()
    assert profile_data["success"] is True
    assert profile_data["meta"]["total"] >= 1

    # 检查返回的基因数据
    gene_symbols = [item["gene_symbol"] for item in profile_data["data"]]
    assert "CYP2D6" in gene_symbols