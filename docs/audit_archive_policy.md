# HealthLens 审计日志归档策略

**版本**: v1.0  
**日期**: 2026-09-24  
**状态**: 已实施

---

## 1. 归档范围

| 数据类型 | 表 | 保留期限 | 归档方式 |
|---------|-----|---------|---------|
| 审计事件 | `audit_events` | 90 天在线 + 7 年归档 | 月度归档到冷存储 |
| 合规同意 | `consent_data` (文件系统) | 7 年 | 按年压缩归档 |
| 完整性巡检 | `audit_events` (event_type=integrity_check) | 90 天 | 与审计事件同策略 |

---

## 2. 每日完整性巡检

**已配置**: crontab 每天 03:00 UTC+8 自动运行

```bash
0 19 * * * /opt/healthlens/scripts/audit_integrity_cron.sh
```

### 巡检脚本

- **位置**: `/opt/healthlens/scripts/audit_integrity_cron.sh`
- **功能**: 调用 `POST /api/v1/audit/check-integrity`，结果写入 `audit_events` 表
- **日志**: `/var/log/healthlens/audit_integrity.log`
- **前置条件**: `/root/.hl_admin_token` 包含有效 admin JWT

### 巡检内容

1. 审计链完整性校验（HMAC + prev_hash 双重校验）
2. 结果作为 `event_type="integrity_check"` 写入审计链
3. 破坏时 severity=3（高优先级告警）

---

## 3. 合规扫描

**端点**: `POST /api/v1/compliance/scan`

### 扫描项

| 检查项 | 规则 | 严重级别 |
|--------|------|---------|
| 审计链完整性 | HMAC + prev_hash 校验 | Critical |
| 敏感操作 | severity >= 3 的事件（24h 内） | High |
| 数据删除 | DELETE 类事件（24h 内） | Medium |
| 暴力尝试 | 同一用户短时间大量认证失败 | High |

### 返回格式

```json
{
  "compliance_status": "ok" | "violations_found",
  "total_violations": <int>,
  "chain_integrity": "ok" | "broken",
  "sensitive_operations_24h": [...],
  "delete_operations_24h": <int>
}
```

---

## 4. 归档流程

### 月度归档（手动）

```bash
# 1. 导出 90 天前的数据
sudo -n docker exec healthlens-db psql -U healthlens -d healthlens -c \
  "COPY (SELECT * FROM audit_events WHERE created_at < NOW() - INTERVAL '90 days') 
   TO '/tmp/audit_archive_$(date +%Y%m).csv' WITH CSV HEADER"

# 2. 压缩
sudo -n gzip /tmp/audit_archive_*.csv

# 3. 移动到归档目录
sudo -n mv /tmp/audit_archive_*.csv.gz /opt/healthlens/archive/

# 4. 删除已归档数据（可选，需确认合规要求）
sudo -n docker exec healthlens-db psql -U healthlens -d healthlens -c \
  "DELETE FROM audit_events WHERE created_at < NOW() - INTERVAL '90 days'"
```

### 归档目录

```
/opt/healthlens/archive/
├── 2026-09/
│   └── audit_archive_202609.csv.gz
├── 2026-10/
│   └── audit_archive_202610.csv.gz
└── ...
```

---

## 5. 恢复流程

```bash
# 从归档恢复
sudo -n gunzip -c /opt/healthlens/archive/2026-09/audit_archive_202609.csv.gz \
  | sudo -n docker exec -i healthlens-db psql -U healthlens -d healthlens \
    -c "COPY audit_events FROM STDIN WITH CSV HEADER"
```

---

## 6. 合规要求对照

| 要求 | 实现状态 | 证据 |
|------|---------|------|
| 审计事件不可篡改 | ✅ HMAC-SHA256 链签名 | `audit_events.signature` |
| 链完整性可验证 | ✅ `verify_chain()` 端点 | `GET /api/v1/audit/verify` |
| 定期完整性巡检 | ✅ 每日 crontab | `/opt/healthlens/scripts/audit_integrity_cron.sh` |
| 合规扫描 | ✅ 自动化扫描端点 | `POST /api/v1/compliance/scan` |
| 数据保留 7 年 | ⬜ 需配置归档存储 | 本策略第 4 节 |
| 用户同意记录 | ✅ 文件系统存储 | `/.consent_data/` |

---

## 7. 告警配置（待实施）

当前巡检结果仅写入日志。建议后续添加：

- 邮件告警：`chain_integrity=broken` 时发送邮件
- 企业微信/钉钉 webhook
- PagerDuty 集成（生产环境）

---

## 8. 相关端点

| 端点 | 方法 | 权限 | 说明 |
|------|------|------|------|
| `/api/v1/audit/verify` | GET | Admin | 手动校验审计链 |
| `/api/v1/audit/check-integrity` | POST | Admin | 主动巡检并记录 |
| `/api/v1/audit/integrity-history` | GET | Admin | 查看巡检历史 |
| `/api/v1/compliance/scan` | POST | 公开 | 合规扫描 |
| `/api/v1/compliance/policies` | GET | 公开 | 合规政策列表 |

---

## 9. 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-09-24 | v1.0 | 初始版本，实施 HMAC 链 + 每日巡检 + 合规扫描 |
