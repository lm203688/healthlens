"""中医古籍知识库 API 测试"""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient

# conftest.py 已提供 client fixture (pytest_asyncio.fixture)


@pytest_asyncio.fixture
async def auth_header(client: AsyncClient):
    """获取认证 header"""
    email = f"test_knowledge_{uuid.uuid4().hex[:8]}@healthlens.com"
    resp = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Test1234!",
        "name": "Test Knowledge",
    })
    data = resp.json()["data"]
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestFoodTherapyRecommend:
    """食疗推荐 API 测试"""

    async def test_recommend_by_constitution(self, client, auth_header):
        """按体质推荐食疗"""
        resp = await client.post(
            "/api/v1/knowledge/food-therapy/recommend",
            json={"constitution_type": "qixu", "limit": 3},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]) > 0
        for item in data["data"]:
            assert "name" in item
            assert "ingredients" in item
            assert "method" in item
            assert "source" in item

    async def test_recommend_by_symptoms(self, client, auth_header):
        """按症状推荐食疗"""
        resp = await client.post(
            "/api/v1/knowledge/food-therapy/recommend",
            json={"symptoms": ["消渴", "口干"], "limit": 3},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) > 0
        names = [r["name"] for r in data["data"]]
        assert "萝卜粥" in names

    async def test_recommend_no_params_400(self, client, auth_header):
        """无参数应返回 400"""
        resp = await client.post(
            "/api/v1/knowledge/food-therapy/recommend",
            json={},
            headers=auth_header,
        )
        assert resp.status_code == 400

    async def test_recommend_seasonal(self, client, auth_header):
        """季节推荐"""
        resp = await client.post(
            "/api/v1/knowledge/food-therapy/recommend",
            json={"constitution_type": "qixu", "seasonal": "winter", "limit": 3},
            headers=auth_header,
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestNonPharmaRecommend:
    """非药物治疗 API 测试"""

    async def test_recommend_non_pharma(self, client, auth_header):
        """获取非药物治疗方案"""
        resp = await client.post(
            "/api/v1/knowledge/non-pharma/recommend",
            json={"constitution_type": "qixu", "limit": 3},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) > 0
        for item in data["data"]:
            assert "name" in item
            assert "treatment_type" in item
            assert "instructions" in item

    async def test_filter_by_treatment_type(self, client, auth_header):
        """按治疗类型过滤"""
        resp = await client.post(
            "/api/v1/knowledge/non-pharma/recommend",
            json={"constitution_type": "qixu", "treatment_types": ["qigong"], "limit": 3},
            headers=auth_header,
        )
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["treatment_type"] == "qigong"


@pytest.mark.asyncio
class TestWellnessPlan:
    """综合调理方案 API 测试"""

    async def test_wellness_plan(self, client, auth_header):
        """获取综合调理方案"""
        resp = await client.get(
            "/api/v1/knowledge/wellness-plan?constitution_type=qixu",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "constitution" in data
        assert "food_therapy" in data
        assert "non_pharma_treatments" in data
        assert "diet_guide" in data
        assert data["constitution"]["name"] == "气虚质"

    async def test_wellness_plan_all_constitutions(self, client, auth_header):
        """所有体质都应有综合调理方案"""
        for ctype in ["qixu", "yangxu", "yinxu", "tanshi", "shire", "xueyu", "qiyu"]:
            resp = await client.get(
                f"/api/v1/knowledge/wellness-plan?constitution_type={ctype}",
                headers=auth_header,
            )
            assert resp.status_code == 200, f"Wellness plan failed for {ctype}"
            data = resp.json()["data"]
            assert len(data["food_therapy"]) > 0, f"No food therapy for {ctype}"
