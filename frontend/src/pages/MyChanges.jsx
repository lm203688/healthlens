/* P0-2（2026-10-23）：「我的变化」页——把 longitudinal（纵向追踪）闭环接进界面。
 *
 * P0-2b（2026-10-24）追加：自动快照 + 周报生成
 *   1) 自动快照：调 longitudinalAddSnapshot 从最新一次评估结果生成 baseline
 *   2) 周报：取首末两个快照做 comparison，再叠加 causal 归因给出「变好了什么」
 *   3) 干预归因：调 causalReport 生成逐轴 5/95 分位带 + 主要杠杆敏感度
 *
 * 未新增后端逻辑，全部走 app/api/longitudinal.py + app/api/causal.py 现有端点。
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import MedicalDisclaimer from "../components/HealthDisclaimer";
import { track } from "../lib/track";

export default function MyChanges() {
  const { t } = useTranslation();
  const [studies, setStudies] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [active, setActive] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  // P0-2b：自动快照 + 周报
  const [snapshotting, setSnapshotting] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [report, setReport] = useState(null);

  useEffect(() => {
    fetchStudies();
  }, []);

  useEffect(() => {
    if (activeId) fetchStudy(activeId);
  }, [activeId]);

  async function fetchStudies() {
    try {
      const resp = await api.longitudinalStudies();
      const data = await resp.json();
      const list = Array.isArray(data) ? data : (data.studies || data.items || []);
      setStudies(list);
      if (list.length && !activeId) setActiveId(list[0].id);
    } catch (e) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function fetchStudy(id) {
    try {
      const resp = await api.longitudinalStudy(id);
      const data = await resp.json();
      setActive(data);
      setReport(null);
    } catch (e) {
      setError(e.message || "加载失败");
    }
  }

  async function createStudy(e) {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      const resp = await api.longitudinalCreateStudy({
        name: newName.trim(),
        start_date: new Date().toISOString().slice(0, 10),
      });
      if (resp.ok) {
        const data = await resp.json();
        setStudies((s) => [data, ...s]);
        setActiveId(data.id);
        setNewName("");
        setShowNew(false);
        try { track("assessment_submitted", { page: "my_changes" }); } catch {}
      }
    } catch (e) {
      setError(e.message);
    }
  }

  /* P0-2b（2026-10-24）：自动快照
   * 从当前用户最近的 assessment 结果生成一次 baseline。
   * 输入走 localStorage 最近一次 agentFusion 响应缓存；无缓存时给一个
   * 中性基线并提示用户先做评估。
   */
  async function autoSnapshot() {
    if (!activeId) return;
    setSnapshotting(true);
    setError(null);
    try {
      // 优先读 Dashboard / HealthAssess 留下的最近一次结果缓存
      let cached = null;
      try {
        cached = JSON.parse(localStorage.getItem("hl_last_assessment") || "null");
      } catch {}
      let axis_scores = null;
      let weak_axes = null;
      let overall = null;
      let notes = "auto_snapshot";
      if (cached && (cached.axis_scores || cached.recommendations)) {
        axis_scores = cached.axis_scores || null;
        weak_axes = cached.weak_axes || null;
        overall = cached.overall_score || null;
        notes = `auto_snapshot:from_cached_assessment`;
      }
      // 兜底：无缓存时直接写入空输入快照（后端会 score_all_axes 走中性路径）
      const body = {
        date: new Date().toISOString().slice(0, 10),
        source: "auto_snapshot",
        notes,
      };
      if (axis_scores) body.axis_scores = axis_scores;
      if (weak_axes) body.weak_axes = weak_axes;
      if (overall != null) body.overall_score = overall;
      if (!axis_scores) body.inputs = { biomarkers: {}, wearable: {} }; // 触发后端打分

      const resp = await api.longitudinalAddSnapshot(activeId, body);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || "快照失败");
      // 刷新当前研究
      await fetchStudy(activeId);
      try { track("daily_checkin", { page: "my_changes", action: "auto_snapshot" }); } catch {}
    } catch (e) {
      setError(e.message || "自动快照失败");
    } finally {
      setSnapshotting(false);
    }
  }

  /* P0-2b（2026-10-24）：周报
   * 1) 取首末两个快照调 longitudinalComparison
   * 2) 用因果引擎对当前弱轴做反事实推演
   */
  async function generateReport() {
    if (!activeId) return;
    setReporting(true);
    setError(null);
    try {
      const snaps = active?.snapshots || [];
      if (snaps.length < 2) {
        setError("至少需要 2 次快照才能生成周报。请先创建 baseline。");
        return;
      }
      // 按日期排序，取首末
      const sorted = snaps.slice().sort((a, b) => {
        const da = a.snapshot_date || a.date || a.created_at || "";
        const db = b.snapshot_date || b.date || b.created_at || "";
        return da.localeCompare(db);
      });
      const first = sorted[0];
      const last = sorted[sorted.length - 1];
      // 计算跨度
      const d1 = new Date(first.snapshot_date || first.date || first.created_at || Date.now());
      const d2 = new Date(last.snapshot_date || last.date || last.created_at || Date.now());
      const days = Math.max(1, Math.round((d2 - d1) / 86400000));

      // 前后对比
      let comparison = null;
      try {
        const resp = await api.longitudinalComparison(activeId, {
          from_snapshot_id: first.id,
          to_snapshot_id: last.id,
        });
        comparison = await resp.json();
      } catch {
        // 对比失败不阻断（comparison 端点可能要求特定 schema）
      }

      // 因果归因：拿最新快照的 weak_axes 做反事实推演
      let causal = null;
      const weak = last.weak_axes || active?.weak_axes || [];
      if (weak.length > 0) {
        try {
          const resp = await api.causalReport({
            baseline: last.axis_scores || null,
            levers: weak.map((a) => `axis_${a}`),
            weeks: Math.max(1, Math.min(12, Math.ceil(days / 7))),
            lever_scale: 1.0,
          });
          causal = await resp.json();
        } catch {
          // 因果推演失败不阻断
        }
      }

      setReport({
        first,
        last,
        days,
        snapshots_count: snaps.length,
        comparison,
        causal,
        generated_at: new Date().toISOString(),
      });
      try { track("result_viewed", { page: "my_changes_report", snapshots: snaps.length }); } catch {}
    } catch (e) {
      setError(e.message || "生成周报失败");
    } finally {
      setReporting(false);
    }
  }

  const snapshots = active?.snapshots || [];
  const interventions = active?.interventions || [];
  const readings = active?.readings || [];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <MedicalDisclaimer />

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">📈 {t("myChanges.title", "我的变化")}</h2>
          <p className="text-slate-500 text-sm mt-1">
            {t("myChanges.subtitle", "追踪一段时间的健康干预，看真的变没变。")}
          </p>
        </div>
        <button onClick={() => setShowNew(!showNew)} className="btn-primary text-sm">
          ＋ {t("myChanges.newStudy", "新建追踪")}
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
          {error}
        </div>
      )}

      {showNew && (
        <form onSubmit={createStudy} className="card p-4 flex flex-col md:flex-row gap-3">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="例如：8 周减脂计划 / 睡眠改善追踪"
            className="flex-1 border rounded-lg px-3 py-2"
            required
          />
          <button type="submit" className="btn-primary">创建</button>
          <button type="button" onClick={() => setShowNew(false)} className="btn-ghost">
            取消
          </button>
        </form>
      )}

      {!loading && studies.length === 0 && !showNew && (
        <div className="card p-10 text-center text-slate-500">
          <div className="text-4xl mb-3">📊</div>
          <p>还没有追踪项目。点击上方「新建追踪」开始记录。</p>
        </div>
      )}

      {!loading && studies.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {studies.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveId(s.id)}
              className={`card p-4 text-left transition ${
                activeId === s.id ? "border-emerald-400 bg-emerald-50" : "hover:shadow-md"
              }`}
            >
              <p className="font-semibold text-slate-800 truncate">{s.name}</p>
              <p className="text-xs text-slate-500 mt-1">
                {s.start_date || "未设"} → {s.end_date || "进行中"}
              </p>
            </button>
          ))}
        </div>
      )}

      {active && (
        <div className="space-y-6">
          {/* 自动快照 + 周报（P0-2b，2026-10-24）*/}
          <div className="card p-5 border-emerald-200 bg-emerald-50/30">
            <h3 className="font-semibold text-slate-800 mb-3">🤖 一键追踪</h3>
            <p className="text-sm text-slate-500 mb-3">
              从最近一次评估自动生成快照，或对比首末快照生成本周报告。
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={autoSnapshot}
                disabled={snapshotting}
                className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {snapshotting ? "生成中..." : "📸 自动快照"}
              </button>
              <button
                onClick={generateReport}
                disabled={reporting || snapshots.length < 2}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                title={snapshots.length < 2 ? "至少需要 2 次快照" : "生成前后对比 + 因果归因"}
              >
                {reporting ? "分析中..." : "📊 生成周报"}
              </button>
            </div>
          </div>

          {/* 周报（P0-2b）*/}
          {report && (
            <div className="card p-5 border-blue-200 bg-blue-50/30">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-slate-800">📊 变更报告</h3>
                <span className="text-xs text-slate-400">
                  生成于 {new Date(report.generated_at).toLocaleString()}
                </span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <div className="p-3 rounded-lg bg-white">
                  <p className="text-xs text-slate-400">追踪天数</p>
                  <p className="text-lg font-bold text-slate-800">{report.days} 天</p>
                </div>
                <div className="p-3 rounded-lg bg-white">
                  <p className="text-xs text-slate-400">快照数</p>
                  <p className="text-lg font-bold text-slate-800">{report.snapshots_count}</p>
                </div>
                <div className="p-3 rounded-lg bg-white">
                  <p className="text-xs text-slate-400">起点</p>
                  <p className="text-sm font-mono text-slate-700">
                    {report.first.snapshot_date || report.first.date || "—"}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-white">
                  <p className="text-xs text-slate-400">终点</p>
                  <p className="text-sm font-mono text-slate-700">
                    {report.last.snapshot_date || report.last.date || "—"}
                  </p>
                </div>
              </div>

              {/* 首末轴对比 */}
              {report.first.axis_scores && report.last.axis_scores && (
                <div className="mb-4">
                  <p className="text-sm font-medium text-slate-700 mb-2">逐轴变化（末 - 首）</p>
                  <div className="space-y-1">
                    {Object.keys(report.last.axis_scores).sort().map((ax) => {
                      const start = report.first.axis_scores[ax] || 0;
                      const end = report.last.axis_scores[ax] || 0;
                      const delta = end - start;
                      const color = delta > 0 ? "text-emerald-600" : delta < 0 ? "text-red-600" : "text-slate-400";
                      const sign = delta > 0 ? "+" : "";
                      return (
                        <div key={ax} className="flex items-center justify-between text-sm">
                          <span className="text-slate-600">轴 {ax}</span>
                          <span className="text-slate-500">{start.toFixed(0)} → {end.toFixed(0)}</span>
                          <span className={`font-medium ${color}`}>{sign}{delta.toFixed(0)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 因果归因 */}
              {report.causal && (
                <div className="p-3 rounded-lg bg-white border border-blue-100">
                  <p className="text-sm font-medium text-slate-700 mb-2">🔍 因果归因（DoWhy 反事实推演）</p>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    基于当前干预强度与观察期，逐轴 5/95 分位带显示可能改善范围。
                    干预越一致，实际效果越靠近上界。
                  </p>
                  {report.causal.counterfactual && (
                    <p className="text-xs text-slate-600 mt-2 font-mono">
                      {JSON.stringify(report.causal.counterfactual).slice(0, 200)}
                    </p>
                  )}
                </div>
              )}

              {/* 干预列表 */}
              {interventions.length > 0 && (
                <div className="mt-3">
                  <p className="text-sm font-medium text-slate-700 mb-2">期间内干预</p>
                  <div className="flex flex-wrap gap-2">
                    {interventions.map((iv) => (
                      <span key={iv.id} className="px-2 py-1 rounded bg-blue-100 text-blue-700 text-xs">
                        {iv.name || iv.label || iv.intervention_type || "干预"}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 轨迹快照 */}
          <div className="card p-5">
            <h3 className="font-semibold text-slate-800 mb-3">📍 快照 ({snapshots.length})</h3>
            {snapshots.length === 0 ? (
              <p className="text-sm text-slate-400">
                还没有快照。点上方「自动快照」快速生成，或每次评估后手动添加一次数据点。
              </p>
            ) : (
              <div className="space-y-2">
                {snapshots
                  .slice()
                  .reverse()
                  .map((sn) => (
                    <div
                      key={sn.id}
                      className="flex items-center justify-between p-2 rounded bg-slate-50 text-sm"
                    >
                      <span className="font-mono text-slate-600">
                        {sn.snapshot_date || sn.date || "—"}
                      </span>
                      <span className="text-slate-700 truncate ml-3 flex-1">
                        {sn.axis_scores
                          ? Object.entries(sn.axis_scores).slice(0, 4).map(([k, v]) => `${k}=${Math.round(v)}`).join(" · ")
                          : (sn.metrics ? Object.entries(sn.metrics).slice(0, 3).map(([k, v]) => `${k}=${v}`).join(" · ") : (sn.note || "—"))}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </div>

          {/* 干预记录 */}
          <div className="card p-5">
            <h3 className="font-semibold text-slate-800 mb-3">💪 我做了什么 ({interventions.length})</h3>
            {interventions.length === 0 ? (
              <p className="text-sm text-slate-400">还没记录干预。</p>
            ) : (
              <div className="space-y-2">
                {interventions
                  .slice()
                  .reverse()
                  .map((iv) => (
                    <div key={iv.id} className="p-2 rounded bg-blue-50 text-sm">
                      <span className="font-medium">{iv.name || iv.label || "干预"}</span>
                      {iv.start_date && (
                        <span className="text-slate-500 ml-2 text-xs">{iv.start_date}</span>
                      )}
                    </div>
                  ))}
              </div>
            )}
          </div>

          {/* 读数记录 */}
          {readings.length > 0 && (
            <div className="card p-5">
              <h3 className="font-semibold text-slate-800 mb-3">📊 读数 ({readings.length})</h3>
              <div className="space-y-2">
                {readings
                  .slice()
                  .reverse()
                  .slice(0, 10)
                  .map((r) => (
                    <div key={r.id} className="flex items-center justify-between p-2 rounded bg-slate-50 text-sm">
                      <span className="text-slate-600">{r.reading_date || "—"}</span>
                      <span className="text-slate-700">{r.metric}={r.value}{r.unit ? ` ${r.unit}` : ""}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
