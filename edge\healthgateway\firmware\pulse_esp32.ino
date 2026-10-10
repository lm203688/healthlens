/*
 * HealthLens 号脉终端固件 V0 (ESP32 + MAX30102)
 * ============================================================
 * 职责：采 PPG → 提特征 → 经串口把一行 JSON 交给边缘盒（树莓派），
 *       由 edge/healthgateway 负责上送云端。
 *
 * 关键设计约束（与云端契约严格对齐）：
 *   1. 固件只输出「聚合特征」，不输出原始波形 —— 原始波形不出户（健康护栏）。
 *   2. 输出键名必须与 data/pulse_signatures.json 的 device_output_contract
 *      及 edge/healthgateway/pulse_source.py 完全一致，否则云端识别不出。
 *   3. 本固件不做任何脉象判定，判定一律在云端 pulse_engine（可迭代、可审计）。
 *
 * 接线（ESP32-WROOM-32 DevKit）：
 *   MAX30102          ESP32
 *   ----------------  --------------------------
 *   VIN      ->  3.3V
 *   GND      ->  GND
 *   SDA      ->  GPIO21   (I2C 数据)
 *   SCL      ->  GPIO22   (I2C 时钟)
 *   INT      ->  GPIO27   (可选，数据就绪中断，不接也能轮询)
 *   备注：MAX30102  breakout 多数板载 1.8V->3.3V 电平转换；
 *         若你的板子是裸芯片，VIN 必须接 1.8V，不能接 3.3V。
 *
 * 串口协议（115200 8N1，每采完一窗输出一行）：
 *   {"hl.pulse.rate_bpm":72.0,"hl.pulse.h1":0.61,...,"hl.pulse.quality":1.0}
 *
 * 依赖：Adafruit MAX30102 库 + Adafruit BusIO
 *   Arduino IDE → Library Manager 搜 "MAX30102" 与 "Adafruit BusIO"
 *
 * 作者：HealthLens 号脉硬件路线 P1
 * 免责：本设备输出为健康信号参考，非医学诊断。
 */
#include <Wire.h>
#include <Adafruit_Max30102.h>
#include <math.h>
#include <string.h>

// ---------------- 可调参数 ----------------
static const float SAMPLE_RATE   = 100.0f;  // Hz，必须与云端 sample_rate 一致
static const float WINDOW_SEC    = 8.0f;    // 每窗时长
static const int   WINDOW_N      = (int)(SAMPLE_RATE * WINDOW_SEC);  // 800 点
static const int   SERIAL_BAUD   = 115200;

// 与 pulse_source.py 的归一化参考保持一致，否则 h1/slope 尺度会漂
static const float REF_AMP       = 1.15f;
static const float REF_SLOPE     = 12.0f;

Adafruit_MAX30102 max30102;

static float buf[WINDOW_N];
static int   bufN = 0;

// ---------------- 特征提取（与云端算法同构） ----------------
// 局部极大
static int localMaxima(const float *v, int n, int i) {
  return (i > 0 && i < n - 1 && v[i] > v[i - 1] && v[i] >= v[i + 1]) ? 1 : 0;
}

// 提取特征并输出 JSON 一行。signal_quality<0.5 时输出 quality 而不编造特征。
static void emitFeatures(float quality) {
  if (bufN < WINDOW_N / 2 || quality < 0.5f) {
    Serial.printf("{\"hl.pulse.quality\":%.2f}\n", quality < 0 ? 0.0f : quality);
    return;
  }

  // 去均值
  float mean = 0.0f;
  for (int i = 0; i < bufN; i++) mean += buf[i];
  mean /= bufN;
  for (int i = 0; i < bufN; i++) buf[i] -= mean;

  float mx = buf[0];
  for (int i = 1; i < bufN; i++) if (buf[i] > mx) mx = buf[i];
  if (mx <= 0) { Serial.printf("{\"hl.pulse.quality\":0.0}\n"); return; }

  // 候选峰：局部极大且 > 0.5*全局最大
  int cand[256], nc = 0;
  for (int i = 1; i < bufN - 1 && nc < 256; i++) {
    if (localMaxima(buf, bufN, i) && buf[i] > 0.5f * mx) cand[nc++] = i;
  }
  if (nc < 2) { Serial.printf("{\"hl.pulse.quality\":0.0}\n"); return; }

  // NMS：按高度降序贪心，间距 >= 0.4s（排除 h3/h5 次级峰，避免脉率翻倍）
  int minDist = (int)(0.4f * SAMPLE_RATE);
  int kept[64], nk = 0;
  bool used[256] = {false};
  for (int pass = 0; pass < nc && nk < 64; pass++) {
    int best = -1; float bv = -1e9f;
    for (int i = 0; i < nc; i++) if (!used[i] && buf[cand[i]] > bv) { bv = buf[cand[i]]; best = i; }
    if (best < 0) break;
    used[best] = true;
    bool ok = true;
    for (int k = 0; k < nk; k++) if (abs(cand[best] - kept[k]) < minDist) { ok = false; break; }
    if (ok) kept[nk++] = cand[best];
  }
  if (nk < 2) { Serial.printf("{\"hl.pulse.quality\":0.0}\n"); return; }

  // RR 间隔 + 中位数（丢弃 <0.5x 或 >1.5x 中位周期：检测伪差，非真性心律不齐）
  float rr[63], nr = 0;
  for (int i = 0; i < nk - 1 && nr < 63; i++) rr[nr++] = (float)(kept[i + 1] - kept[i]) / SAMPLE_RATE;
  float srr[63]; memcpy(srr, rr, sizeof(float) * nr);
  for (int i = 1; i < nr; i++) { float v = srr[i]; int j = i - 1; while (j >= 0 && srr[j] > v) { srr[j + 1] = srr[j]; j--; } srr[j + 1] = v; }
  float medRR = srr[nr / 2];
  float sumIn = 0; int nIn = 0;
  for (int i = 0; i < nr; i++) if (rr[i] >= 0.5f * medRR && rr[i] <= 1.5f * medRR) { sumIn += rr[i]; nIn++; }
  if (nIn < 2) { sumIn = 0; for (int i = 0; i < nr; i++) sumIn += rr[i]; nIn = nr; }
  float meanRR = sumIn / nIn;
  float rate = meanRR > 0 ? 60.0f / meanRR : 0.0f;
  float h1raw = 0; for (int i = 0; i < nk; i++) if (buf[kept[i]] > h1raw) h1raw = buf[kept[i]];

  // 逐周期取 h3 / h5 / 升支斜率
  float sum3 = 0, sum5 = 0, sumSlope = 0; int n3 = 0, n5 = 0, nSl = 0;
  for (int i = 0; i < nk - 1; i++) {
    int a = kept[i], b = kept[i + 1], cyc = b - a;
    if (cyc <= 2) continue;
    float base = 1e9f;
    for (int j = a; j <= b && j < bufN; j++) if (buf[j] < base) base = buf[j];
    float amp = (h1raw - base) > 1e-6f ? (h1raw - base) : 1e-6f;

    int lo3 = a + (int)(0.20f * cyc), hi3 = min(b, a + (int)(0.45f * cyc));
    float h3 = buf[a];
    for (int j = lo3; j <= hi3 && j < bufN; j++) if (buf[j] > h3) h3 = buf[j];
    if (hi3 > lo3) { sum3 += (h3 - base) / amp; n3++; }

    int lo5 = a + (int)(0.45f * cyc), hi5 = b - max((int)(0.15f * cyc), 2);
    float h5 = base;
    for (int j = lo5; j <= hi5 && j < bufN; j++) if (buf[j] > h5) h5 = buf[j];
    if (hi5 > lo5) { sum5 += (h5 - base) / amp; n5++; }

    int upLo = max(a - (int)(0.12f * cyc), 0);
    if (a - upLo > 0) {
      float steep = (buf[a] - buf[upLo]) / ((a - upLo) / SAMPLE_RATE);
      float v = steep / REF_SLOPE; if (v > 1.0f) v = 1.0f;
      sumSlope += v; nSl++;
    }
  }

  float h3h1   = n3 ? sum3 / n3 : 0.0f;
  float h5h1   = n5 ? sum5 / n5 : 0.0f;
  float slope  = nSl ? sumSlope / nSl : 0.0f;
  float dicro  = (h5h1 > 0.2f) ? 1.0f : 0.0f;

  float cv = 0.0f;
  if (nIn >= 2) {
    float mn = rr[0], mxr = rr[0];
    for (int i = 0; i < nr; i++) { if (rr[i] < mn) mn = rr[i]; if (rr[i] > mxr) mxr = rr[i]; }
    cv = (mxr - mn) / meanRR;
  }
  float rhythm = 1.0f - cv * 2.0f; if (rhythm < 0.0f) rhythm = 0.0f;

  float h1n = h1raw / REF_AMP; if (h1n > 1.0f) h1n = 1.0f;

  // 键名与云端 contract 完全一致（pause_pattern V0 恒 none，depth 留空由边缘填）
  Serial.printf(
    "{\"hl.pulse.rate_bpm\":%.1f,\"hl.pulse.h1\":%.3f,\"hl.pulse.h3_h1\":%.3f,"
    "\"hl.pulse.h5_h1\":%.3f,\"hl.pulse.dicrotic_present\":%.0f,"
    "\"hl.pulse.ascending_slope\":%.3f,\"hl.pulse.rhythm_regularity\":%.3f,"
    "\"hl.pulse.pause_pattern\":\"none\",\"hl.pulse.perfusion_index\":%.3f,"
    "\"hl.pulse.depth\":\"\",\"hl.pulse.sampling_hz\":%.0f,\"hl.pulse.quality\":%.2f}\n",
    rate, h1n, h3h1, h5h1, dicro, slope, rhythm, h1n, SAMPLE_RATE, quality);
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  Wire.begin(21, 22);
  if (!max30102.begin(Wire)) {
    Serial.println(F("{\"fatal\":\"MAX30102 not found on I2C 0x57. Check VIN=1.8V/3.3V and SDA=21,SCL=22\"}"));
    while (1) delay(1000);
  }
  max30102.setup();
  // 100Hz 多采样平均（AVERAGE=4 提升信噪比）
  max30102.setSampleRate(MAX30102_SAMPLE_RATE_100);
  max30102.setAveraging(MAX30102_AVERAGING_4);
  // LED 功率：腕式透射需较高，MAX30102 最大 50mW(0x7F=49.9mW)
  max30102.setLedPower(0x40, MAX30102_LED_RED);   // 660nm
  max30102.setLedPower(0x40, MAX30102_LED_IR);    // 880nm
  Serial.println(F("{\"ready\":\"MAX30102 ok, sending hl.pulse.* every 8s\"}"));
}

void loop() {
  static unsigned int lastMs = 0;
  static float sigSum = 0; static int sigN = 0;

  unsigned long now = millis();
  if (now - lastMs < (1000 / (unsigned)SAMPLE_RATE)) return;
  lastMs = now;

  uint32_t ir = max30102.getIR();
  float v = (float)ir / 262144.0f;  // 18bit -> [0,1)

  // 简单滑动平均当低通（8 窗）
  static float sm = 0; static bool initSm = false;
  if (!initSm) { sm = v; initSm = true; } else { sm += 0.35f * (v - sm); }

  if (bufN < WINDOW_N) {
    buf[bufN++] = sm;
    // 灌注质量代理：MAX30102 未直接给 PI，用信号方差近似（静息不动时越高）
    if (bufN > 20) {
      float mean = 0; for (int i = 0; i < bufN; i++) mean += buf[i]; mean /= bufN;
      float var = 0; for (int i = 0; i < bufN; i++) var += (buf[i] - mean) * (buf[i] - mean);
      var /= bufN;
      sigSum += var; sigN++;
    }
    return;
  }

  float quality = (sigN ? sigSum / sigN : 0.0f) * 4000.0f;
  if (quality > 1.0f) quality = 1.0f;
  emitFeatures(quality);
  bufN = 0; sigSum = 0; sigN = 0;
}
