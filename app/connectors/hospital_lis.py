"""医院 LIS (实验室信息系统) 数据连接器
Phase 1: FHIR API 拉取骨架
Phase 2: 对接具体医院 FHIR/HL7 接口

医院 LIS 通常通过 FHIR API 或 HL7 v2 对接。
Phase 1 实现通用的 FHIR Observation 拉取逻辑。
"""
from datetime import datetime, timezone
from loguru import logger
from app.connectors.base import BaseConnector, ConnectorRegistry


class HospitalLISConnector(BaseConnector):
    """医院 LIS 连接器 - FHIR API 模式"""

    SOURCE_TYPE = "hospital_lis"
    DISPLAY_NAME = "医院检验系统(LIS)"

    def __init__(self):
        self.fhir_base_url = None
        self.api_key = None

    def configure(self, fhir_base_url: str, api_key: str | None = None):
        """配置医院 FHIR API 地址"""
        self.fhir_base_url = fhir_base_url.rstrip("/")
        self.api_key = api_key

    async def get_auth_url(self, state: str) -> str:
        raise NotImplementedError("医院 LIS 通常使用 API Key 或医院专用认证，不支持 OAuth2")

    async def exchange_token(self, code: str) -> dict:
        raise NotImplementedError("医院 LIS 使用 API Key 认证")

    async def fetch_observations(self, patient_id: str, days: int = 30) -> dict:
        """从医院 FHIR API 拉取检验结果"""
        import httpx

        if not self.fhir_base_url:
            return {"error": "FHIR base URL not configured", "items_count": 0}

        headers = {"Accept": "application/fhir+json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.fhir_base_url}/Observation"
        params = {"patient": patient_id, "_count": 100}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, headers=headers, timeout=30.0)
                resp.raise_for_status()
                bundle = resp.json()

            observations = []
            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                loinc_code = None
                for coding in resource.get("code", {}).get("coding", []):
                    if coding.get("system") == "http://loinc.org":
                        loinc_code = coding.get("code")
                        break

                value_quantity = resource.get("valueQuantity", {})
                observations.append({
                    "loinc_code": loinc_code,
                    "loinc_name": resource.get("code", {}).get("text", ""),
                    "value_numeric": float(value_quantity.get("value", 0)) if value_quantity.get("value") else None,
                    "value_unit": value_quantity.get("unit", ""),
                    "source": "hospital_lis",
                    "recorded_at": resource.get("effectiveDateTime", ""),
                    "resource_id": resource.get("id"),
                })

            logger.info(f"Hospital LIS: fetched {len(observations)} observations for patient {patient_id}")
            return {
                "items_count": len(observations),
                "items": observations,
                "message": f"Fetched {len(observations)} lab results from hospital LIS",
            }

        except Exception as e:
            logger.error(f"Hospital LIS fetch failed: {e}")
            return {"error": str(e), "items_count": 0}

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        return await self.fetch_observations(access_token, days)

    async def sync_data(self, access_token: str, user_id: str, since: datetime | None = None) -> dict:
        """同步医院 LIS 数据"""
        # access_token 在这里作为 patient_id 使用
        result = await self.fetch_observations(access_token)

        return {
            "items_count": result.get("items_count", 0),
            "observations": result.get("items", []),
            "message": result.get("message", "Sync complete"),
        }


ConnectorRegistry.register("hospital_lis", HospitalLISConnector)
