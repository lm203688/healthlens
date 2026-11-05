/* P1-PROD-01（2026-10-27）：Today —— 四任务导航的「今天」视图。
 *
 * 报告 §4.2 要求「今天」只呈现四件事：今日状态、一个最重要变化、一个可执行行动、
 * 需要关注的风险；不先展示复杂雷达和模型角色（雷达归 Dashboard 评估页）。
 *
 * 数据源（全部复用现有端点，零新后端）：
 *   - api.dashboard()        → summary / key_metrics / risk_overview
 *   - api.checkinSummary()   → averages / trend（自测趋势）
 *   - api.longitudinalStudies() → 是否有活跃追踪（供睡眠实验入口判断）
 *
 * 诚实边界：
 *   - 「变化」= 观察到的数据变化，明确标注「≠ 疗效 / 因果」，不把波动写成结论。
 *   - 「风险」= risk_overview 的最高等级提示 + 免责声明，非医疗诊断。
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import MedicalDisclaimer from "../components/HealthDisclaimer";
import { track } from "../lib/track";

// 睡眠 8 周实验（报告 §4.3 先锋场景）——预注册主要指标，复用 n-of-1 实验引擎
const SLEEP_EXPERIMENT = {
  name: "8 周睡眠规律作息实验",
  protocol: {
    type: "sleep_8w",
    weeks: 8,
    target_axes: ["E"], // 稳态轴 E = 睡眠/昼夜节律（fusion_engine AXIS_BRIDGES）
    levers: ["固定起床时间", "减少晚间咖啡因"],
    pre_registered_metrics: ["sleep_duration", "sleep_efficiency", "hrv", "energy_score"],
    baseline_days: 14,
    review_frequency: "weekly",
  },
};

export default function Today() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [dash, setDash] = useState(null);
  const [checkin, setCheckin] = useState(null);
  const [hasActiveStudy, setHasActiveStudy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [d, c, s] = await Promise.all([
          api.dashboard().then((r) => r.json()).catch(() => null),
          api.checkinSummary().then((r) => r.json()).catch(() => null),
          api.longitudinalStudies().then((r) => r.json()).catch(() => null),
        ]);
        if (!alive) return;
        setDash(d?.data || null);
        setCheckin(c?.data || null);
        const studies = Array.isArray(s) ? s : (s?.studies || s?.items || []);
        setHasActiveStudy(studies.some((x) => x?.status === "active" || x?.status === "recruiting"));
      } catch {
        /* 任一数据源失败不阻断整页 */
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  async function startSleepExperiment() {
    if (creating) return;
    setCreating(true);
    setNotice(null);
    try {
      const resp = await api.longitudinalCreateStudy({
        name: SLEEP_EXPERIMENT.name,
        start_date: new Date().toISOString().slice(0, 10),
        cohort: "n_of_1",
        protocol: SLEEP_EXPERIMENT.protocol,
        consent_version: "sleep-8w-v1",
        notes: "P1-PROD-01 先锋场景：睡眠与压力恢复 8 周闭环",
      });
      if (resp.ok) {
        try { track("sleep_experiment_created", { via: "today" }); } catch {}
        navigate("/changes");
      } else {
        const body = await resp.json().catch(() => ({}));
        setNotice(body?.detail || "创建失败，请重试");
      }
    } catch (e) {
      setNotice(e.message || "创建失败，请重试");
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return <div className="max-w-4xl mx-auto text-center py-16 text-slate-400">…</div>;
  }

  // ── 数据整理 ──
  const metrics = dash?.key_metrics || {};
  const metricList = Object.entries(metrics).map(([loinc, m]) => ({ loinc, ...m }));
  const riskList = dash?.risk_overview || [];
  const riskLevels = { low: 0, medium: 1, high: 2 };
  const topRisk = [...riskList].sort((a, b) => (riskLevels[b.risk_level] || 0) - (riskLevels[a.risk_level] || 0))[0] || null;

  const trend = checkin?.trend || null;
  // 一个最重要变化：取 |趋势| 最大的自测维度（诚实标注为观察变化）
  let topChange = null;
  if (trend) {
    const dims = ["energy", "digestion", "sleep"]
      .map((k) => ({ key: k, delta: trend[k] ?? 0 }))
      .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    topChange = dims[0] || null;
  }

  const averages = checkin?.averages || null;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <MedicalDisclaimer />

      <div>
        <h2 className="text-2xl font-bold text-slate-800">☀️ {t("today.title", "今天")}</h2>
        <p className="text-slate-500 text-sm mt-1">
          {t("today.subtitle", "只看今天最重要的事，不堆模型。")}
        </p>
      </div>

      {/* ① 今日状态 */}
      <section className="card p-5">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          {t("today.status", "今日状态")}
        </h3>
        {metricList.length === 0 && !averages ? (
          <p className="text-slate-400 text-sm">
            {t("today.noMetrics", "暂无关键指标。先去上传或自测一次，之后这里会显示最近数值。")}
          </p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {metricList.slice(0, 4).map((m) => (
              <div key={m.loinc} className="rounded-lg bg-slate-50 p-3">
                <div className="text-xs text-slate-500">{m.name}</div>
                <div className="text-xl font-semibold text-slate-800">
                  {m.value ?? "—"}
                  <span className="text-xs text-slate-400 ml-1">{m.unit || ""}</span>
                </div>
              </div>
            ))}
            {averages && (
              <div className="rounded-lg bg-emerald-50 p-3">
                <div className="text-xs text-emerald-600">{t("today.selfCheckAvg", "近况自测均分")}</div>
                <div className="text-xl font-semibold text-emerald-700">
                  {averages.overall ?? "—"}<span className="text-xs ml-1">/5</span>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ② 一个最重要变化 */}
      <section className="card p-5">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          {t("today.topChange", "一个最重要变化")}
        </h3>
        {topChange ? (
          <>
            <div className="flex items-center gap-3">
              <div className={`text-2xl ${topChange.delta >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                {topChange.delta >= 0 ? "▲" : "▼"}
              </div>
              <div>
                <div className="font-medium text-slate-800">
                  {t(`today.dim.${topChange.key}`)} {topChange.delta >= 0 ? "+" : ""}{topChange.delta.toFixed(2)}
                </div>
                <div className="text-xs text-slate-400">
                  {t("today.changeIsObservation", "自测后半段 vs 前半段的均分变化（观察值，非疗效结论）")}
                </div>
              </div>
            </div>
          </>
        ) : (
          <p className="text-slate-400 text-sm">
            {t("today.noTrend", "自测满 4 次后这里会给出趋势变化。")}
          </p>
        )}
      </section>

      {/* ③ 一个可执行行动 */}
      <section className="card p-5 border-l-4 border-l-emerald-500">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          {t("today.action", "一个可执行行动")}
        </h3>
        <p className="text-slate-700 text-sm leading-relaxed">
          {t("today.actionText", "今晚比平时早 30 分钟熄灯，并把手机放在卧室外充电。这是一项低风险、可逆的作息杠杆。")}
        </p>
        {!hasActiveStudy && (
          <button
            onClick={startSleepExperiment}
            disabled={creating}
            className="mt-4 px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 transition disabled:opacity-50"
          >
            {creating
              ? t("today.creating", "创建中…")
              : t("today.startSleep", "创建 8 周睡眠规律作息实验")}
          </button>
        )}
        {notice && <p className="mt-2 text-sm text-red-600">{notice}</p>}
      </section>

      {/* ④ 需要关注的风险 */}
      <section className="card p-5">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          {t("today.risks", "需要关注的风险")}
        </h3>
        {topRisk ? (
          <div className="flex items-start gap-3">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
              topRisk.risk_level === "high" ? "bg-red-100 text-red-700"
              : topRisk.risk_level === "medium" ? "bg-amber-100 text-amber-700"
              : "bg-slate-100 text-slate-600"
            }`}>
              {topRisk.risk_type} · {topRisk.risk_level}
            </span>
            <span className="text-xs text-slate-400">
              {t("today.riskNote", "评估时间")}: {topRisk.assessed_at ? new Date(topRisk.assessed_at).toLocaleDateString() : "—"}
            </span>
          </div>
        ) : (
          <p className="text-slate-400 text-sm">
            {t("today.noRisk", "暂无高风险提示。健康管理建议仅供参考，不构成医疗诊断。")}
          </p>
        )}
      </section>
    </div>
  );
}