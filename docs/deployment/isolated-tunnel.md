# HealthLens 独立 Cloudflare Tunnel 部署说明

> 状态：✅ 已于 2026-09-02 完成迁移并验证
> 目标：HealthLens 与 AIShield 各用各的隧道，永不再互相踩踏

---

## 一、为什么要拆开（故障根因）

以前两个项目共用 **同一份** `/root/.cloudflared/config.yml`（AIShield 的隧道 `aishield-tunnel`）：

```
cloudflared (aishield) ──运行──> 读取 /root/.cloudflared/config.yml
                                 └─ 把 ingress 推送到 Cloudflare 远端（source: local）
```

**关键点**：cloudflared 进程启动时会把本地 config 里的 ingress 上传到 Cloudflare 远端配置
（通过 API 查询可见 `"source": "local"`）。也就是说：

- AIShield 重新部署 → 它生成的 config.yml 只含 `aishield.tools` → 推送后
  **HealthLens 的 `api.healthlens.cc` 路由从远端消失** → 全部落到兜底 `http_status:404`。
- 这就是 2026-08-31 / 09-01 两次「注册接口 404、`Unexpected end of JSON input`」的真正原因。
- 之前的「每 5 分钟自愈 cron」只是不断把 HealthLens 条目补回去，和对方**赛跑**，治标不治本。

雪上加霜：AIShield 部署脚本里有一行 `pkill -f "cloudflared"`，会把机器上**所有** cloudflared
进程杀掉（包括 HealthLens 的）。

---

## 二、迁移后的架构

| 项目 | 隧道名 / ID | 配置文件 | systemd 服务 | 承载域名 |
|---|---|---|---|---|
| **HealthLens** | `healthlens-tunnel`<br>`772e48b6-fec9-4295-9816-92f6479e823d` | `/etc/cloudflared-healthlens/config.yml` | `cloudflared-healthlens` | `api.healthlens.cc` |
| **AIShield** | `aishield-tunnel`<br>`0c39bcfb-0c96-4858-9025-d54131e062ec` | `/root/.cloudflared/config.yml` | `cloudflared-tunnel` | `aishield.tools` |

- 凭证文件各存各目录：HealthLens 的 json 副本在 `/etc/cloudflared-healthlens/`（600）。
- DNS：`api.healthlens.cc` CNAME → `772e48b6-….cfargotunnel.com`（橙云代理）。
- 前端 `healthlens.cc` / `www.healthlens.cc` 仍走 **Cloudflare Pages**（CNAME → `healthlens-a3w.pages.dev`），不经过隧道。
- 互不引用、互不重启、互不可见。

### 三层防护

1. **独立 systemd 服务** `Restart=always`，进程级自愈（5 秒）。
2. **看门狗 cron**（每 5 分钟）：`systemctl is-active --quiet cloudflared-healthlens || systemctl restart cloudflared-healthlens`，
   覆盖「服务被停掉」而不仅是「进程崩溃」。
3. **AIShield 脚本已收敛**：原 `pkill -f "cloudflared"` 改为
   `systemctl stop cloudflared-tunnel || pkill -f "cloudflared tunnel --config /root/.cloudflared/config.yml"`，
   只停它自己，不再误杀 HealthLens。

---

## 三、全新机器上重新部署（可复现步骤）

### 需要你操作的部分（仅首次、需 Cloudflare 登录）

如果你的 ECS 上还没有 `/root/.cloudflared/cert.pem`（cloudflared 账户证书），需要：

1. 在 ECS 执行 `cloudflared tunnel login`；
2. 终端会打印一个 `https://dash.cloudflare.com/argotunnel?...` 链接，
   在**浏览器**打开 → 选择 `healthlens.cc` 所在账户 → 授权；
3. 授权后 cert.pem 自动生成，之后所有 tunnel 操作都不再需要浏览器。

> 当前 ECS 已有 cert.pem（账户 `8162aa3b…`，含 healthlens.cc 与 aishield.tools），
> 所以本次迁移**你无需任何操作**，我全部做完了。

### AI / 脚本执行的部分

```bash
# 上传 tools/setup_healthlens_tunnel.sh 到 ECS 后：
sudo bash setup_healthlens_tunnel.sh
```

脚本幂等，会完成：创建/复用隧道 → 写独立 config → 写 systemd 服务 → 校正 DNS CNAME →
装看门狗 cron → 验证。

---

## 四、验证方法

```bash
# 1. 两个服务都活着
systemctl is-active cloudflared-healthlens cloudflared-tunnel

# 2. 进程确实是两个、各读各的配置
pgrep -af cloudflared
#   /usr/local/bin/cloudflared --config /etc/cloudflared-healthlens/config.yml tunnel ... run
#   /usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run

# 3. 隔离硬验证：停掉 AIShield 隧道，HealthLens 必须仍然 200
sudo systemctl stop cloudflared-tunnel
curl -s -o /dev/null -w '%{http_code}\n' https://api.healthlens.cc/health   # 期望 200
sudo systemctl start cloudflared-tunnel

# 4. 业务端点
curl https://api.healthlens.cc/health                      # 200 {"status":"ok",...}
curl -X POST https://api.healthlens.cc/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"x@y.com","password":"x"}'               # 401（正确，不再是 404 空体）
```

### 迁移当日实测结果

| 检查项 | 结果 |
|---|---|
| `systemctl stop cloudflared-tunnel` 后 `api.healthlens.cc/health` | **200**（证明隔离成功） |
| `api.healthlens.cc/health` | 200 `{"status":"ok","version":"0.18.1"}` |
| 登录接口（错误密码） | 401（此前为 404 空体 → `Unexpected end of JSON input`） |
| `aishield.tools` | 200 |
| `healthlens.cc` / `healthlens.cc/app/` | 200 / 200 |
| 远端路由：healthlens-tunnel | 仅 `api.healthlens.cc` |
| 远端路由：aishield-tunnel | 仅 `aishield.tools`（version 6，HealthLens 残留已清除） |

---

## 五、日常运维

```bash
# 改了源站端口/新增域名后
sudo vim /etc/cloudflared-healthlens/config.yml
sudo cloudflared --config /etc/cloudflared-healthlens/config.yml tunnel ingress validate
sudo systemctl restart cloudflared-healthlens

# 看日志
sudo journalctl -u cloudflared-healthlens -f

# 查远端实际生效的路由（两个隧道对比）
sudo python3 /tmp/hl_cfg_check.py
```

**新增子域走隧道时**，除了改 config.yml，还要把该域名的 CNAME 指向
`772e48b6-fec9-4295-9816-92f6479e823d.cfargotunnel.com`
（`cloudflared tunnel route dns healthlens-tunnel <域名>` 对新域名可用；
对已被别的项目占用的域名，CLI 不会覆盖，需用 API 改 DNS 记录）。

---

## 六、回滚

最坏情况回退到共用隧道：

```bash
sudo systemctl stop cloudflared-healthlens
# 把 api.healthlens.cc 的 CNAME 改回 0c39bcfb-....cfargotunnel.com
# 并在 /root/.cloudflared/config.yml 里补回 healthlens ingress，重启 cloudflared-tunnel
```

回滚会重新引入互相覆盖的风险，不建议。

---

## 七、遗留事项

- `/root/.cloudflared/` 下仍有两个历史隧道的凭证（`aa3f86b8-…` 名为 `healthlens` 的旧隧道、
  `a956a3fe-…` 名为 `aishield.tools` 的旧隧道），均无连接，可清理但无害。
- 建议轮换泄露过的 Cloudflare 令牌（曾硬编码在脚本中）。
- cloudflared 版本 2026.7.3 偏旧，可升级到 2026.8.3（升级会短暂中断，需挑低峰）。
