# HealthLens 边缘网关方案（健康信号常开采集）

> 状态：骨架已落地（edge/healthgateway + app/connectors/edge_gateway.py + app/api/device_metrics.py）
> 定位：**补 Open Wearables 覆盖不到的那一块**，不是替代它。

---

## 0. 一句话结论

八轴引擎现在吃的大多是「问卷 + 历史设备数据」推出来的量。边缘网关提供**一条常开的、低频但连续的真实生理信号通道**，
让 F（脏腑神经内分泌）、G（神情志）、B（气血线粒体）三轴从"模型估计"升级为"有信号支撑"。
代价是一台常开小盒子 + 一套上报链路；不接 Meta 的 Muse Gadget SDK（理由见第 2 节）。

## 1. 为什么需要它

| 现状 | 缺口 |
|---|---|
| Open Wearables 14 provider 覆盖的是**手机/手表侧的爆发式采样**（睡眠、活动、体重） | 没有「连续脑电/自主神经」这一类信号 |
| 八轴的 F / G 轴主要靠问卷与模型推导 | 缺可证伪的原始量，容易被质疑"玄学换算" |
| ECS 服务器**没有蓝牙，也放不了可穿戴设备** | 采集只能发生在用户侧，边缘侧必须自己建 |

## 2. 为什么不接 Meta 的 Muse Gadgets（结论：0 价值）

一手核查（2026-10-04，`facebookincubator/muse-gadget-sdk` 官方 README）：

- 它开源的是 **SDK 与固件（Apache 2.0），不是开源硬件**——没有原理图/PCB/BOM，板子要自己买现成货。
- Linux SDK 的全部能力只有 4 条：`system.run`、`file.read`、`file.write`、`device.health`。
  **没有任何一条产生人体健康数据**；`device.health` 报的是 uptime / load / 内存 / 磁盘 / 温度。
- 配对要 `gadgets.muse.ai` 的 SDK token + 手机 Muse app（iOS/Android）开发者模式。
  实测本机 `curl https://gadgets.muse.ai/` → **超时 20s（境内不可达）**；
  GitHub 仓库 200 可达。
- 它的目标是让 Meta 的 Muse AI 助手操作你的机器，README 原话：
  `Muse gets the same access to the machine as the account you install it for`——
  把 shell / sudo 交给远端 AI，官方自承 community device、无厂商验证、挡不住中间人。
- **我们的解决办法不是"接入它"，而是"抄它的骨架、换掉它的危险部分、换掉它的目的"**：
  抄 `executor.py` 的命令白名单结构、`install.sh` + systemd 的落地与可观测性、`send-user-msg` 的消息通道；
  不抄 `system.run`；目的从"给 AI 助手开机器"改成"把健康指标推上云"。

## 3. 架构

```
Muse 头环（BLE）
   └── 边缘盒子（树莓派 Zero 2 W / 3B+ / 4 / 5，Linux）
         ├── 采集：muse-lsl（可选依赖）起 BLE 流，pylsl inlet 取样本
         ├── 本地聚合：4s 窗 → Goertzel 频带功率 → 60s 平均 → 日粒度指标（原始波形不出户）
         ├── 本地只读口：GET /health /status /metrics（127.0.0.1:8421，只回 JSON）
         └── 上报：POST /api/v1/device-metrics（令牌 + nonce，失败落 offline.jsonl 补发）
                          │
                          ▼
HealthLens 云（ECS）
   ├── POST /api/v1/device-metrics   接收 + 去重 + 白名单校验（app/api/device_metrics.py）
   ├── 最近指标缓存（进程内；多 worker 时迁 Redis）
   └── app/connectors/edge_gateway.py → HealthObservation → 八轴融合引擎
```

**为什么是边缘推、不是云端拉**：盒子在家庭 NAT 后面，云端没有可拨号的入口。断网时先落盘，下次启动补发。

## 4. 硬件选型

| 方案 | 优点 | 代价 | 建议 |
|---|---|---|---|
| 树莓派 Zero 2 W + 电源 + microSD | 最小常开形态，功耗低 | 只有 1 核，聚合要降窗；无 PoE | 尝鲜 / POC |
| 树莓派 3B+ / 4 / 5 | 有蓝牙、USB、够算 | 功耗与体积上去了 | 正式形态 |
| ESP32 | 便宜、能挂屏幕传感器 | **没有蓝牙 4.0+ 的连续 BLE 中枢能力**，做不了 EEG 聚合 | 只做转发/显示节点 |
| Muse 头环（Muse 2 / Muse S / 2016） | 社区协议已开源（muse-lsl，Zenodo 10.5281/zenodo.3228861），EEG + PPG + ACC/GYRO 一次拿到 | 需自己买；Gen 1 无 PPG | 首选信号源 |

> 成本按实际渠道价计（盒子 + 头环），此处不给数字，避免拍脑袋。

## 5. 指标 → 八轴映射

| 边缘指标（key） | 单位 | 证据级 | 对应轴 | 说明 |
|---|---|---|---|---|
| `hl.eeg.alpha_ratio` / `theta` / `beta` / `delta` | ratio（0~1） | signal-derived | G 神情志、F 脏腑神经内分泌 | 相对频带比，抗电极阻抗漂移 |
| `hl.eeg.alpha_asymmetry` | log-ratio | signal-derived | G 神情志 | 前额左右 α 不对称（AF7−AF8），经典指标 |
| `resting_heart_rate` | bpm | signal-derived | B 气血线粒体 | 有真实 LOINC 码 **8867-4** |
| PPG → HRV（RMSSD，ms） | ms | signal-derived | B 气血线粒体 | 需 Muse 2；**目前未启用**，缺校准数据 |
| ACC/GYRO 夜间体动 | count | signal-derived | E 脏腑神经内分泌 | 睡眠扰动，需 Muse 2 |

命名纪律（跟项目其它证据一致）：**只有能给出真实 LOINC 的字段才填 loinc_code**，其余走 `hl.` 自有命名空间，
不冒充标准码。当前 `LOINC_MAP` 只登记了 `8867-4`（心率）这一条确定项。

## 6. 安全护栏（这块比功能更重要）

| 层 | 措施 |
|---|---|
| 设备侧命令 | **只读白名单**（status / device.list / metrics.query / pair.status / log.tail），无 shell、无写文件、无重启外发 |
| 日志回读 | 只能读网关自己的 `gateway.log`，解析路径限制在 data_dir 内（防目录穿越） |
| 传输 | `X-HL-Edge-Token` + 一次性 nonce，云端 30 分钟重放窗口去重 |
| payload | 指标 key 走正则白名单 `^[a-z0-9][a-z0-9._-]{0,63}$`，条数 ≤64，`day` 必须真能解析成 `YYYY-MM-DD` |
| 数值 | `PHYSIO_BOUNDS` 生理区间外直接丢弃（例如心率 900 直接丢，不进八轴） |
| 身份 | 边缘只带 `user_ref`（用户自造绑定串），边缘侧没有账号体系，也不知道真实身份 |

对比 Meta 那版：`system.run` 以安装账号权限执行、账号有 sudo 则远端也有 sudo。这条**明确不抄**。

## 7. 落地步骤

```bash
# 1) 边缘盒子（Linux / 树莓派）
pip install muselsl                     # 可选：只有要用 Muse 头环时才装
git clone <this repo> && cd healthlens/edge
python healthgateway/main.py collect --kind muse_lsl --seconds 60 --data-dir /var/lib/healthlens
python healthgateway/main.py serve --port 8421            # 常驻，配 systemd
python healthgateway/main.py report --endpoint https://healthlens.cc/api/v1/device-metrics

# 无硬件自测（跑通整条链路、验证频谱算法）
python healthgateway/main.py collect --kind synthetic --seconds 8
python healthgateway/tests/test_spectrum.py

# 2) 云端
#    .env 里设 EDGE_GATEWAY_TOKEN=<云端签发>，留空则该接口整体 503
supervisor/restart web                  # 记忆里的正规操作：docker compose up -d --force-recreate web
```

## 8. 边界（必须写在明面上）

- 这是**健康管理平台，不是医疗产品**：边缘网关只产生"健康信号"，不产生诊断结论。
- 不做：原始波形上传、长期波形存储、任何"治疗建议"。
- 不做设备认证体系（token 是共享密钥形态；要多用户得换成每设备一密钥 + 证书）。
- 最近指标缓存是**进程内**的：多 worker 部署时迁移到 Redis，改动点只有 `app/api/device_metrics.py` 的 `ingest()`。

## 9. 路线建议

| 优先级 | 动作 | 依赖 |
|---|---|---|
| P0 | 用 `--kind synthetic` 跑通整条链路 + 频谱真值验证 | 无（已落地） |
| P1 | 真机接 Muse S，采集 7 天，看 α/θ 比是否能在日间波动上区分"作息变化" | 需要一台 Muse 头环 |
| P1 | 云端 token 签发流程（现在 handoff 成明文 .env） | 一个管理员端点 |
| P2 | HRV（RMSSD）启用 + 与 OW 的睡眠数据做交叉校验 | Muse 2 的 PPG |
| P2 | 边缘盒子镜像化（树莓派 hazel 预装） | 时间 |
| 不做 | 接 Meta Muse Gadgets SDK | 见第 2 节 |
