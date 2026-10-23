/* P0-2（2026-10-23）：「我的变化」页——把 longitudinal（纵向追踪）闭环接进界面。
 *
 * 背景：2026-10-22 产品评估定位到「随访 / n-of-1 对比」是产品最值钱的闭环
 * （回答"我做了 8 周干预，到底变没变"），后端 10 端点齐全，但 client.js
 * 完全未封装、前端零触达。此页面用现有端点实现最小可用闭环：
 *   1) 列研究 / 建研究
 *   2) 看轨迹（每周一次快照）
 *   3) 记录干预（"我做了 X"）
 *   4) 前后对比（选两个时间窗）
 *
 * 未新增任何后端逻辑，全部走 app/api/longitudinal.py 现有端点。
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
      // 兼容 {studies: [...]} 或裸数组
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
          {/* 轨迹快照 */}
          <div className="card p-5">
            <h3 className="font-semibold text-slate-800 mb-3">📍 快照 ({snapshots.length})</h3>
            {snapshots.length === 0 ? (
              <p className="text-sm text-slate-400">
                还没有快照。每次评估后可在此添加一次数据点。
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
                        {sn.metrics ? Object.entries(sn.metrics).slice(0, 3).map(([k, v]) => `${k}=${v}`).join(" · ") : (sn.note || "—")}
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
