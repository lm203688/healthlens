# 号脉硬件 · 一步步装配与调试手册

> 目标读者：第一次做这块板子的人。按顺序做完，每步都有**可验证的通过标准**，不通不过就别往下走。
> 配套：`pulse_esp32.ino`（可直接烧录的固件）、`PULSE_DEVICE.md`（设计原理）。
> 定位：健康信号采集与养生参考，非医学诊断。

---

## 第 0 步：先跑通「无硬件」全链路（0 元，1 小时）

**为什么先做这步**：先证明「特征 → 云端 → 解读」这条路是通的，再去调硬件。
否则硬件调好了却发现云端收不到键名，你会分不清是传感器坏了还是协议错了。

```bash
cd edge
python healthgateway/main.py collect --kind pulse --seconds 8
```

**通过标准**：输出一行 JSON，含 `hl.pulse.rate_bpm`（约 72）、`hl.pulse.h1`、`hl.pulse.h3_h1` 等 12 个键。

再验证云端能解读这组特征：

```bash
curl -X POST https://healthlens.cc/api/v1/pulse/interpret \
  -H 'Content-Type: application/json' \
  -d '{"features":{"hl.pulse.rate_bpm":68,"hl.pulse.h1":0.52,"hl.pulse.h3_h1":0.60,"hl.pulse.h5_h1":0.41,"hl.pulse.dicrotic_present":1,"hl.pulse.ascending_slope":0.49,"hl.pulse.rhythm_regularity":0.96,"hl.pulse.pause_pattern":"none","hl.pulse.perfusion_index":0.52,"hl.pulse.depth":""}}'
```

**通过标准**：返回 `db_available: true`，`labels` 里有中文脉名（不是 `huan` 这种 id —— 若出现 id 说明云端知识库没加载，见第 6 步）。

---

## 第 1 步：采购（约 ¥70–120）

| 部件 | 型号 | 数量 | 参考价 | 备注 |
|---|---|---|---|---|
| 主控 | ESP32-WROOM-32 DevKit V1 | 1 | ¥25 | 30 引脚版即可，必须带 WiFi |
| 脉搏传感器 | **MAX30102** 模块（带 breakout） | 1 | ¥40 | 买 **breakout**，裸芯片要自己处理 1.8V |
| 导线 | 杜邦线 公-母 / 公-公 | 1 排 | ¥5 | |
| USB 线 | Micro-USB 数据线 | 1 | ¥5 | 很多线只能充电不能传数据，换一根 |
| （可选）压力传感器 | FSR402 薄膜压力传感器 | 1 | ¥25 | 想测「浮/沉」才需要，见第 5 步 |
| （可选）硅胶垫/指套 | 3D 打印或现成指套 | 1 | ¥10 | 决定佩戴稳定性 |

> **关键采购提示**：MAX30102 假货多。要买**带 breakout 板**的（板上有 1.8V LDO 和电平转换），插上就能用。裸芯片版本 VIN 只能接 1.8V，接 3.3V 会烧。

---

## 第 2 步：接线（照表接，别凭感觉）

| MAX30102 | ESP32 | 说明 |
|---|---|---|
| VIN | **3.3V** | breakout 板才可接 3.3V |
| GND | GND | |
| SDA | **GPIO21** | I2C 数据 |
| SCL | **GPIO22** | I2C 时钟 |
| INT | GPIO27 | 可不接，固件用轮询 |
| 另有板载引脚 | 别接 | 部分模块有 vREG 输出，悬空即可 |

**接线自检**（万用表通断档）：
1. `VIN—3.3V` 短路蜂鸣 → 对
2. `GND—GND` 短路蜂鸣 → 对
3. **SDA 和 SCL 之间不能短路** → 不响才对

---

## 第 3 步：烧录固件

1. Arduino IDE → 库管理器搜并安装 `Adafruit MAX30102` + `Adafruit BusIO`
2. 打开 `pulse_esp32.ino`
3. 工具菜单选：`ESP32 Dev Module` / 板子按你买的选 / 115200
4. 烧录

**通过标准**（串口监视器 115200）：
```
{"ready":"MAX30102 ok, sending hl.pulse.* every 8s"}
```

若看到：
```
{"fatal":"MAX30102 not found on I2C 0x57..."}
```
→ **不要改代码**，按序排查：① SDA/SCL 是否接反（21↔22 互换试）② VIN 电压 ③ 板子是否断电后仍插着。

若能看到 `ready` 但 8 秒后输出 `{"hl.pulse.quality":0.0}`：
→ 传感器初始化成功但**没戴在手上**。见第 4 步。

---

## 第 4 步：戴上手指调信号（最难的一步，也是最关键）

### 4.1 佩戴位置
- **推荐 V0 位置**：食指指根（指甲盖往下一指节），PPG 信号最强最稳。
- **若要贴「关部」**：手腕掌侧、桡骨茎突（高骨）内侧。但腕部皮下脂肪和静脉搏动干扰多，**新手先用食指**，等信号稳了再上腕。

### 4.2 三个必须做到的事
1. **遮光**——环境光会淹没信号。MAX30102 datasheet 明确要求避杂散光。用黑色不透明胶带/3D 打印遮光罩盖住探头正面，只留皮肤接触面。
2. **压力固定**——太松读不到，太紧挤掉血。目标是轻压 1–3 N。用硅胶垫/指套固定，别用手一直按着。
3. **别动**——测量 8 秒内手臂、手指保持静止。体动会产生远超脉搏的基线漂移。

### 4.3 通过标准
串口每 8 秒输出：
```json
{"hl.pulse.rate_bpm":68.0,"hl.pulse.h1":0.523,...,"hl.pulse.quality":0.85}
```
- `quality > 0.5`（固件用信号方差近似，**动一下就会掉到 0.1 以下**，可自测）
- `rate_bpm` 与你用手指数的脉搏一致（±3 bpm 内）

### 4.4 调不好时的排查顺序
| 现象 | 原因 | 处理 |
|---|---|---|
| quality 一直 0 | 位置/压力/遮光任一不对 | 逐个改，一次只改一个 |
| rate 翻倍（约 144） | 重搏波 h5 被当主峰 | 正常，`extract_features` 的 NMS 已处理；若仍出现调大 `minDist` |
| rate 减半（约 36） | 漏检主峰 | 调小 `0.4 * SAMPLE_RATE` 的系数 |
| 波形乱跳 | 体动 | 采样时肘部支撑固定 |
| 数值漂移严重 | 环境光 | 加遮光罩 |

---

## 第 5 步（可选）：加 FSR402 测「浮/沉」

中医的「浮/沉」= 取脉轻/重不同导致脉体显现位置不同。V0 单点做不到，但可以用压力传感器近似：
- 装 FSR402 与 MAX30102 并排
- 用 3 档已知压力（轻/中/重）各采 5 秒
- 记录各档的 `perfusion_index`：**轻压最强 → 浮；重压最强 → 沉**
- 把结论写进 `hl.pulse.depth`（`superficial` / `""` / `deep`）

不做这一步，浮/沉两脉永远测不出（`depth` 留空时引擎只用 `perfusion_index < 0.3` 弱推断沉脉）。

---

## 第 6 步：接边缘盒（组成完整系统）

ESP32 输出的 JSON 交给树莓派（边缘盒），由边缘盒上送云端 —— 固件**不直接联网**，原因：原始数据处理、票据管理都在边缘盒，且 ESP32 直连公网会暴露长期凭据。

边侧网关已内置串口读取能力（`edge/healthgateway/pulse_source.py` 的 `PulseSerialSource`），不用自己写串口代码：

```bash
# 1) 装可选依赖（只在用真实串口时需要，回放模式不用装）
pip install pyserial

# 2) 边缘盒读固件串口 → 多窗平均 → 写本地日指标
python edge/healthgateway/main.py collect --kind pulse --port /dev/ttyUSB0 --seconds 60 --loop

# 3) 上送云端（用网页端签发的票据，或静态令牌 HL_EDGE_TOKEN）
python edge/healthgateway/main.py report --day $(date +%F)
```

> 无硬件也能验证这条链路：把固件每行输出存成 `fw.jsonl`，用 `--serial-file fw.jsonl` 代替 `--port`，走的是**完全相同的解析与上报路径**。

**方式 B（无线，进阶）**：ESP32 用 WiFi POST 到边缘盒本地 HTTP（`server.py` 已在监听）。固件目前走串口，WiFi 直推需另改固件。

**通过标准**（全链路）：
```bash
curl -X POST https://healthlens.cc/api/v1/agent/pulse \
  -H 'Content-Type: application/json' -d '{"user_ref":"你的ref"}'
```
返回 `available: true` 且 `pulse_interpretation.labels` 里有中文脉名与八轴信号，即说明「固件 → 串口 → 边缘盒 → 云端 → 解读」整条链路闭合。

---

## 第 7 步：知识库缺失怎么排查

若返回的 `labels` 里 `name` 是 `se` / `xian` 这种**英文 id 而不是中文名**，说明云端没读到知识库（引擎降级了）。

线上排查：
```bash
curl https://healthlens.cc/api/v1/device-metrics/backend
# 另：interpret 返回 503 即知识库不可用（这是刻意的，宁可报错也不给假解读）
```
自修：在 ECS 上把 `data/pulse_signatures.json` 放到容器可见路径，或设 `HL_PULSE_DB=/app/data/pulse_signatures.json`。

---

## 下一步（Phase 4：前端展示）
硬件打通后，解读结果要能在网页上看到 —— 对应 `PULSE_DEVICE.md` §10 Phase 4。

---

## 已知边界（务必先看，避免误用）

1. **阈值未用真人数据标定**：引擎阈值来自文献区间 + 合成波形自测，**没有**经过真人 7 天数据校准。可靠性上限如实标注，买到硬件后需用真实数据回流校准。
2. **固件不输出 `h4_h1`**：ESP32 端只算 `h3_h1`、`h5_h1`、`dicrotic_present`，没算重搏切迹比 `h4_h1`（板上难稳定检测切迹）。因此真实设备走「`h4_h1` 偏低判涩脉」这条分支不会触发，涩脉改由 `dicrotic<0.5` 或 `h5_h1<0.2` 触发。如需固件端判涩，后续在固件加切迹检测。
3. **三才（寸/关/尺）与浮/沉压力扫描未做**：单探头只能采一处。浮/沉需 FSR402 做压力扫描（第 5 步），寸关尺需三探头或机械移位，均为硬件依赖。
4. **PPG 的固有天花板**：单点外周脉搏波能可靠反映「数/形/律」，但医生三指按压的浮沉语义无法被单点传感器完全复现。本系统定位为健康信号参考，非替代中医师判断。
