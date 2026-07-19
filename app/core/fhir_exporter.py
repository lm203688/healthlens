"""FHIR R5 标准数据导出
Phase 1: Observation + Patient Bundle
Phase 2: 完整 Composition + Condition + MedicationRequest

参考: https://hl7.org/fhir/R5/
"""
import uuid
from datetime import datetime, timezone
from loguru import logger


class FHIRExporter:
    """FHIR R5 导出器"""

    def export_observation(self, obs: dict) -> dict:
        """将单条观察值转为 FHIR Observation"""
        return {
            "resourceType": "Observation",
            "id": obs.get("id", str(uuid.uuid4())),
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "laboratory",
                    "display": "Laboratory",
                }],
            }],
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": obs.get("loinc_code"),
                    "display": obs.get("loinc_name", ""),
                }],
                "text": obs.get("loinc_name", ""),
            },
            "subject": {
                "reference": f"Patient/{obs.get('user_id', '')}",
                "display": obs.get("patient_name", ""),
            },
            "effectiveDateTime": str(obs.get("recorded_at", "")),
            "valueQuantity": {
                "value": float(obs["value_numeric"]) if obs.get("value_numeric") is not None else None,
                "unit": obs.get("value_unit", ""),
                "system": "http://unitsofmeasure.org",
            } if obs.get("value_numeric") is not None else None,
            "interpretation": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                    "code": "N" if not obs.get("is_abnormal") else "A",
                    "display": "Normal" if not obs.get("is_abnormal") else "Abnormal",
                }],
            }] if obs.get("is_abnormal") is not None else None,
            "referenceRange": [
                {
                    "low": {"value": float(rl) if rl else None, "unit": obs.get("value_unit", "")}
                    if (rl := obs.get("reference_range_low")) else None,
                    "high": {"value": float(rh) if rh else None, "unit": obs.get("value_unit", "")}
                    if (rh := obs.get("reference_range_high")) else None,
                    "text": obs.get("reference_range_text", "正常范围"),
                }
            ] if obs.get("reference_range_low") or obs.get("reference_range_high") else None,
        }

    def export_patient_bundle(self, user_data: dict, observations: list[dict]) -> dict:
        """将用户健康数据导出为 FHIR Bundle

        Args:
            user_data: 用户基本信息 {id, name, gender, birth_date, ...}
            observations: 观察值列表
        """
        bundle_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        entries = []

        # Patient resource
        patient = {
            "fullUrl": f"urn:uuid:{user_data.get('id', bundle_id)}",
            "resource": {
                "resourceType": "Patient",
                "id": user_data.get("id", str(uuid.uuid4())),
                "name": [{"text": user_data.get("name", ""), "family": user_data.get("name", "")}],
                "gender": user_data.get("gender", "unknown"),
                "birthDate": str(user_data.get("birth_date", "")) if user_data.get("birth_date") else None,
                "extension": [
                    {
                        "url": "http://hl7.org/fhir/StructureDefinition/patient-height",
                        "valueQuantity": {
                            "value": float(user_data["height_cm"]) if user_data.get("height_cm") else None,
                            "unit": "cm",
                        }
                    },
                    {
                        "url": "http://hl7.org/fhir/StructureDefinition/patient-weight",
                        "valueQuantity": {
                            "value": float(user_data["weight_kg"]) if user_data.get("weight_kg") else None,
                            "unit": "kg",
                        }
                    },
                ] if user_data.get("height_cm") or user_data.get("weight_kg") else [],
            },
        }
        entries.append(patient)

        # Observation resources
        for obs in observations:
            fhir_obs = self.export_observation(obs)
            obs_id = fhir_obs.get("id", str(uuid.uuid4()))
            entries.append({
                "fullUrl": f"urn:uuid:{obs_id}",
                "resource": fhir_obs,
            })

        # DiagnosticReport (汇总)
        if observations:
            report = {
                "fullUrl": f"urn:uuid:{str(uuid.uuid4())}",
                "resource": {
                    "resourceType": "DiagnosticReport",
                    "id": str(uuid.uuid4()),
                    "status": "final",
                    "category": [{
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                            "code": "LAB",
                            "display": "Laboratory",
                        }],
                    }],
                    "code": {
                        "coding": [{
                            "system": "http://loinc.org",
                            "code": "11502-2",
                            "display": "Laboratory report",
                        }],
                    },
                    "subject": {
                        "reference": f"Patient/{user_data.get('id', '')}",
                        "display": user_data.get("name", ""),
                    },
                    "effectiveDateTime": now,
                    "result": [
                        {"reference": f"Observation/{e['resource'].get('id', '')}"}
                        for e in entries[1:]  # 跳过 Patient
                    ],
                    "presentedForm": [{
                        "contentType": "text/html",
                        "url": f"urn:uuid:{str(uuid.uuid4())}",
                    }],
                },
            }
            entries.append(report)

        bundle = {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "collection",
            "timestamp": now,
            "entry": entries,
        }

        logger.info(f"Exported FHIR bundle: {len(entries)} resources (Patient + {len(observations)} Observations + Report)")
        return bundle
