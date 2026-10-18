# 号脉感应硬件 · 分步设计文档（HealthLens Pulse Device, V0）

> 定位：把"号脉"做成可量化的健康信号采集终端，信号经边缘盒上送 HealthLens 云端，由脉象解读引擎给出**养生参考**（非诊断）。
> 安全护栏：本设备与结论均属 wellness（健康管理）范畴，不宣称医疗诊断/治疗；一切解读仅供自我养生引导，异常信号附就医提示。

---

## 1. 设计目标与约束

| 目标 | 说明 |
|---|---|
| 可感"脉" | 采集桡动脉/指端容积脉搏波（PPG），反推脉率、波形形态、节律——对应中医"数/形/势/律"四纲 |
| 可定位"脉位" | V0 单点采样（浮/沉靠取脉压力扫描近似）；寸关尺三才定位为后续增强（见 §8） |
| 可上云 | 复用已建 `edge/healthgateway` 边缘网关：本地特征提取 → `POST /api/v1/device-metrics`（票据鉴权） |
| 不依赖 BLE 在服务器 | 边缘盒常开（树莓派/EPS32），原始波形不出户，只上送聚合特征（与 Muse 方案一致） |
| 低成本可复现 | 全开源硬件 + 标准模块，BOM 控制在百元级 |

**为什么是 PPG 而不是压力传感器阵列**：真正中医号脉是"手指压力波"，但压力阵列（如专利 CN105147261A 的柔性阵列+气囊）成本高、标定难。PPG（光电容积脉搏波）是消费级最成熟方案，其 h1–h5 时域参数已被现代研究证明与脉象要素（弦/滑/涩/洪/细）强相关，足以支撑"养生参考"级解读。压力阵列作为 §8 的 P2 增强。

---

## 2. 总体架构

```
  [号脉指套/腕带]
       │ 桡动脉搏动 → 微血管血容量变化
       ▼
  MAX30102 (红光660nm + 红外880nm)
       │ I2C
       ▼
  [边缘盒]  ESP32 / 树莓派 Pico W
   - 采样 PPG (≥100Hz)
   - 特征提取 (rate, h1, h3/h1, h4/h1, h5/h1, dicrotic, slope, perfusion, rhythm)
   - 压力扫描近似浮/沉
       │ HTTPS + 票据 (X-HL-Edge-Ticket)
       ▼
  HealthLens 云端  POST /api/v1/device-metrics
       │
       ▼
  app/connectors/pulse_gateway.py  →  app/lib/pulse_engine.py（脉象分类）
       │
       ▼
  八轴融合引擎（气血/脏腑/神情志/肾精 等）
       │
       ▼
  养生参考结论 + 健康护栏（前端展示）
```

---

## 3. 信号链路原理

PPG 原理：LED 光照皮下，含氧/缺氧血红蛋白对 660nm/880nm 吸收率不同，光电管接收反射光强随心动周期起伏 → 容积脉搏波。

关键波形参数（来自 ScienceDirect pulse matrix 研究，已在 `data/pulse_signatures.json` 的 `ppg_feature_dictionary` 定义）：

- **h1** 收缩期叩击波振幅 → 洪/细/微
- **h3/h1** 重搏前波比（外周阻力/血管弹性）→ 弦（比值高、出现早）
- **h4/h1** 重搏切迹比 → 外周阻力/舒张压
- **h5/h1** 重搏波比 → 大动脉弹性
- **dicrotic_notch** 降支重搏切迹 → 滑/涩（模糊=涩）
- **ascending_slope** 升支斜率 → 实/虚
- **rhythm_regularity / pause_pattern** → 结/代/促
- **perfusion_index × 取脉压力扫描** → 浮/沉

---

## 4. 组件清单（BOM，V0）

| 部件 | 型号/规格 | 用量 | 备注 |
|---|---|---|---|
| 主控 | ESP32-WROOM-32 或 树莓派 Pico W | 1 | 需 WiFi；ESP32 更省电 |
| 脉搏传感器 | MAX30102 模块（带 INT 中断） | 1 | 反射式 PPG，I2C |
| 压力/接触反馈 | FSR402 薄膜压力传感器（可选） | 1 | 量化"按压力度"，近似浮沉 |
| 指套/腕带 | 3D 打印支架 + 硅胶垫 | 1 | 固定 MAX30102 于桡动脉/食指 |
| 状态指示 | 红绿 LED | 2 | 采样中/上传成功 |
| 供电 | 3.7V 锂电 + TP4056 充电 | 1 | 或 USB 直供 |
| 外壳 | 3D 打印 | 1 | — |

> 不需要 ECS 上 BLE（与 Muse 方案同理：ECS 无 BLE，采集必须在边缘盒完成）。

---

## 5. 机械结构（分步）

1. **定位桡动脉**：手腕掌侧、桡骨茎突内侧（关部）为基准；V0 也可简化为食指指根（容积脉搏最强且稳定）。
2. **指套/腕带支架**：3D 打印一个带凹槽的夹子，把 MAX30102 光学窗正对血管，硅胶垫提供稳定接触压力（约 1–3 N）。
3. **压力扫描（近似浮沉）**：让设备以 3 档接触压力（轻/中/重）各采 5 秒，记录各档信号强度；轻压最强→浮，重压最强→沉。FSR402 读数作为压力标定。
4. **防环境光**：MAX30102 加黑色遮光罩（直接日晒会淹没信号——其 datasheet 明确提到需避杂散光）。

---

## 6. 边缘固件职责（`edge/healthgateway/pulse_source.py`）

固件/边缘 Python 负责：

1. 以 ≥100Hz 采样 PPG（RED 或 IR 通道），做带通滤波（0.5–8Hz 去基线漂移与高频噪声）。
2. 找峰值 → 计算 `rate_bpm`（RR 间期中位数）。
3. 对每个心动周期提取 h1（主峰）、h3（重搏前波）、h4（切迹）、h5（重搏波）振幅，算出 h3/h1、h4/h1、h5/h1。
4. 判定 `dicrotic_notch` 清晰度、`ascending_slope`、`perfusion_index`。
5. 统计 RR 间期变异 → `rhythm_regularity`、`pause_pattern`（none/irregular/regular）。
6. 组装成 `hl.pulse.*` 载荷（见 `data/pulse_signatures.json` 的 `device_output_contract`），通过 `reporter.push()` 上送（优先票据，回落静态 token）。

> 复用现有 `signal_source.py` 的 `build_source()` 范式，新增 `PulsePpgSource`；复用 `reporter.py` 的鉴权与上送逻辑，无需重写网络层。

---

## 7. 与现有边缘网关接线

- 在 `edge/healthgateway/main.py` 的 `collect` 子命令新增 `--kind pulse`，调用 `PulsePpgSource`。
- 聚合后通过 `reporter.build_request()` 上送，endpoint 默认 `https://healthlens.cc/api/v1/device-metrics`。
- 云端 `app/api/device_metrics.py` 已支持任意 `hl.*` 命名空间键（正则白名单 `^[a-z0-9][a-z0-9._-]{0,63}$`），无需改动接收口。
- 云端 `pulse_gateway` 连接器把 `hl.pulse.*` 指标读入 `pulse_engine` 分类。

---

## 8. 后续增强（P1/P2，不在 V0 范围）

| 阶段 | 内容 |
|---|---|
| P1 | 三探头同步采样（寸/关/尺）或单探头机械移位，输出三才分区信号；参考专利 CN105147261A 柔性阵列+气囊自动定位 |
| P2 | FSR 压力阵列替代单点 FSR，精确复现"浮中沉"三取脉压力下的脉象变化 |
| P2 | 边缘盒 Docker 镜像化（与 Muse 方案 §10 合并） |

---

## 9. 安全护栏清单

- 设备只采波形、只上送聚合特征，**原始波形不出户**（与 Muse 一致）。
- 云端结论一律带 `guardrail` 字段：提示"仅供养生参考，异常请就医"。
- 危象信号（疾/微/散/代/促频发）触发强提醒文案，引导就医，平台不做任何处置建议。
- 不接入任何"处方/治疗"逻辑。

---

## 10. 分步实施路线

| Phase | 动作 | 产出 |
|---|---|---|
| 0 | 采购 BOM、3D 打印支架 | 实物 |
| 1 | 跑通 MAX30102 在边缘盒的 I2C 读数 + 波形显示 | `pulse_source.py` 原型 |
| 2 | 实现特征提取（h1–h5、节律） | 与 `pulse_engine` 对齐的载荷 |
| 3 | 接 `reporter` 上送 + 云端 `pulse_engine` 出脉象标签 | 端到端可演示 |
| 4 | 前端展示脉象养生参考 + 健康护栏 | 闭环 |
