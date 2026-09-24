import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import MedicalDisclaimer from '../components/HealthDisclaimer';
import Modal from '../components/Modal';
import AxisRadar from '../components/AxisRadar';
import TrendChart from '../components/TrendChart';

/* 八轴稳态模型（A–H）。代谢-炎症轴按假说级映射落点 A / F。i18n: 使用 key 而非硬编码中文 */
const AXIS_KEYS = {
  A: 'axis.A', B: 'axis.B', C: 'axis.C', D: 'axis.D',
  E: 'axis.E', F: 'axis.F', G: 'axis.G', H: 'axis.H',
};

const AXIS_NOTE_KEYS = {
  A: 'axis.noteA', B: 'axis.noteB', C: 'axis.noteC', D: 'axis.noteD',
  E: 'axis.noteE', F: 'axis.noteF', G: 'axis.noteG', H: 'axis.noteH',
};

const MARKER_FIELDS = [
  { key: 'glucose',       labelKey: 'axis.glucose',      unit: 'mmol/L', step: '0.1',  hintKey: 'axis.glucoseHint' },
  { key: 'hba1c',         labelKey: 'axis.hba1c',        unit: '%',      step: '0.1',  hintKey: 'axis.hba1cHint' },
  { key: 'hs_crp',        labelKey: 'axis.hsCrp',        unit: 'mg/L',   step: '0.1',  hintKey: 'axis.hsCrpHint' },
  { key: 'waist_cm',      labelKey: 'axis.waist',        unit: 'cm',     step: '1',    hintKey: 'axis.waistHint' },
  { key: 'hdl',           labelKey: 'axis.hdl',          unit: 'mmol/L', step: '0.01', hintKey: 'axis.hdlHint' },
  { key: 'triglycerides', labelKey: 'axis.triglycerides', unit: 'mmol/L', step: '0.01', hintKey: 'axis.triglyceridesHint' },
  { key: 'sbp',           labelKey: 'axis.sbp',          unit: 'mmHg',   step: '1',    hintKey: 'axis.sbpHint' },
  { key: 'bmi',           labelKey: 'axis.bmi',          unit: '',       step: '0.1',  hintKey: 'axis.bmiHint' },
];

const STATUS_STYLE = {
  good: 'bg-emerald-100 text-emerald-700',
  watch: 'bg-amber-100 text-amber-700',
  poor: 'bg-red-100 text-red-700',
};

/* 迷你 Turboid 可用生活方式杠杆（key 须与后端 wellness_simulator.LEVERS 一致）i18n: 使用 labelKey */
const PROJECT_LEVERS = [
  { key: 'sleep_hygiene',          labelKey: 'axis.leverSleep' },
  { key: 'fasting',                labelKey: 'axis.leverFasting' },
  { key: 'aerobic',                labelKey: 'axis.leverAerobic' },
  { key: 'anti_inflammatory_diet', labelKey: 'axis.leverDiet' },
  { key: 'stress_mgmt',            labelKey: 'axis.leverStress' },
  { key: 'protein_intake',         labelKey: 'axis.leverProtein' },
  { key: 'thermal',                labelKey: 'axis.leverThermal' },
];

/* 八轴配色（用于推演轨迹线） */
const AXIS_COLORS = {
  A: '#10b981', B: '#06b6d4', C: '#3b82f6', D: '#8b5cf6',
  E: '#ec4899', F: '#f59e0b', G: '#84cc16', H: '#ef4444',
};

/* 迷你轨迹图：在 0-100 区间画一条轴的健康信号演化折线（无第三方依赖） */
function Sparkline({ points, color, width = 220, height = 40 }) {
  if (!points || points.length < 2) return null;
  const max = 100, min = 0;
  const stepX = width / (points.length - 1);
  const y = (v) => height - ((v - min) / (max - min)) * height;
  const d = points.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * stepX).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  return (
    <svg width={width} height={height} className="overflow-visible">
      <line x1="0" y1={y(50)} x2={width} y2={y(50)} stroke="#e2e8f0" strokeDasharray="3 3" />
      <path d={d} fill="none" stroke={color} strokeWidth="2" />
    </svg>
  );
}

function scoreColor(score) {
  if (score >= 75) return 'bg-emerald-500';
  if (score >= 60) return 'bg-amber-500';
  return 'bg-red-500';
}

export default function AxisProfile() {
  const { t } = useTranslation();
  const [chronoAge, setChronoAge] = useState(40);
  const [isMale, setIsMale] = useState(true);
  const [values, setValues] = useState({});
  const [meta, setMeta] = useState(null);
  const [bioage, setBioage] = useState(null);
  const [assess, setAssess] = useState(null);
  const [loading, setLoading] = useState('');
  const [error, setError] = useState(null);
  const [evidence, setEvidence] = useState(null);   // 证据卡弹窗数据
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  /* 迷你 Turboid 养生方案虚拟推演 */
  const [projLevers, setProjLevers] = useState([]);
  const [projWeeks, setProjWeeks] = useState(12);
  const [projection, setProjection] = useState(null);
  const [projLoading, setProjLoading] = useState(false);
  const [projError, setProjError] = useState(null);
  const [checkinApplied, setCheckinApplied] = useState(false);
  const [checkinLoading, setCheckinLoading] = useState(false);
  const [checkinData, setCheckinData] = useState(null);

  useEffect(() => {
    api.axesMeta()
      .then((r) => r.json())
      .then((d) => { if (d?.success) setMeta(d.data); })
      .catch(() => {});
  }, []);

  function payload() {
    const body = { chrono_age: Number(chronoAge) || 40, is_male: isMale };
    for (const f of MARKER_FIELDS) {
      const raw = values[f.key];
      if (raw !== undefined && raw !== '') body[f.key] = Number(raw);
    }
    return body;
  }

  async function run(kind) {
    setLoading(kind);
    setError(null);
    try {
      const resp = kind === 'bioage'
        ? await api.axesBioage(payload())
        : await api.axesAssess({ ...payload(), top_k: 8 });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || t('axis.analysisFailed'));
      if (kind === 'bioage') setBioage(data.data);
      else setAssess(data.data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading('');
    }
  }

  const mapped = meta?.mapped_axes || ['A', 'F'];

  async function applyCheckin() {
    setCheckinLoading(true);
    try {
      const resp = await api.checkinSummary();
      const data = await resp.json();
      if (data?.success && data.data?.averages) {
        const a = data.data.averages;
        // 取最近一次自测数据（若有）
        const histResp = await api.checkinHistory({ limit: 1 });
        const histData = await histResp.json();
        const latest = histData?.data?.items?.[0] || null;
        setCheckinData({
          energy: latest?.energy_score || Math.round((a.energy_score || 3) * 10) / 10,
          digestion: latest?.digestion_score || Math.round((a.digestion_score || 3) * 10) / 10,
          sleep: latest?.sleep_score || Math.round((a.sleep_score || 3) * 10) / 10,
          source: latest ? 'latest' : 'average',
        });
        setCheckinApplied(true);
      } else {
        setProjError(t('axis.noCheckinData'));
      }
    } catch (e) {
      setProjError(t('axis.checkinFetchError'));
    } finally {
      setCheckinLoading(false);
    }
  }

  async function runProject() {
    setProjLoading(true);
    setProjError(null);
    try {
      const body = {
        weak_axes: assess?.weak_axes || [],
        levers: projLevers,
        weeks: Number(projWeeks) || 12,
      };
      // 若已应用自测数据，优先用 checkin 基线
      if (checkinApplied && checkinData) {
        body.checkin_energy = Math.round(Math.min(5, Math.max(1, checkinData.energy)));
        body.checkin_digestion = Math.round(Math.min(5, Math.max(1, checkinData.digestion)));
        body.checkin_sleep = Math.round(Math.min(5, Math.max(1, checkinData.sleep)));
      }
      const resp = await api.axesProject(body);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || t('axis.projectionFailed'));
      setProjection(data.data);
    } catch (e) {
      setProjError(e.message);
    } finally {
      setProjLoading(false);
    }
  }

  function toggleLever(key) {
    setProjLevers((p) => (p.includes(key) ? p.filter((k) => k !== key) : [...p, key]));
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <MedicalDisclaimer />
      <div>
        <h2 className="text-2xl font-bold">🧭 {t('axis.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">
          {t('axis.subtitle', { axis: meta?.axis_label || t('axis.defaultAxis') })}
        </p>
      </div>

      {meta && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-xs text-slate-600">
          ⚗️ {t('axis.methodLabel')}：{meta.method} · {t('axis.weakThreshold')} &lt; {meta.weak_threshold} · {t('axis.mappedAxes')}{' '}
          {mapped.map((a) => `${a}（${t(AXIS_KEYS[a])}）`).join('、')}
        </div>
      )}

      {/* 输入 */}
      <div className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
        <h3 className="font-semibold text-slate-800">{t('axis.healthMarkers')}</h3>

        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm">
            <span className="block text-slate-600 mb-1">{t('axis.actualAge')}</span>
            <input
              type="number" min="1" max="120" value={chronoAge}
              onChange={(e) => setChronoAge(e.target.value)}
              className="w-24 px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            />
          </label>
          <div>
            <span className="block text-slate-600 mb-1 text-sm">{t('profile.gender')}</span>
            <div className="flex gap-2">
              {[{ v: true, t: t('profile.male') }, { v: false, t: t('profile.female') }].map((o) => (
                <button
                  key={o.t} type="button" onClick={() => setIsMale(o.v)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                    isMale === o.v
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-50 text-slate-600 border border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {o.t}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {MARKER_FIELDS.map((f) => (
            <label key={f.key} className="text-sm">
              <span className="block text-slate-600 mb-1">
                {t(f.labelKey)} {f.unit && <span className="text-slate-400 text-xs">{f.unit}</span>}
              </span>
              <input
                type="number" step={f.step} placeholder={t(f.hintKey)}
                value={values[f.key] ?? ''}
                onChange={(e) => setValues((p) => ({ ...p, [f.key]: e.target.value }))}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
              />
            </label>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => run('bioage')} disabled={!!loading}
            className="px-5 py-2.5 bg-white border border-emerald-600 text-emerald-700 rounded-xl font-semibold hover:bg-emerald-50 disabled:opacity-50 transition"
          >
            {loading === 'bioage' ? t('axis.calculating') : t('axis.calcAxisScore')}
          </button>
          <button
            onClick={() => run('assess')} disabled={!!loading}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {loading === 'assess' ? t('axis.analyzing') : t('axis.startAssessment')}
          </button>
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
      </div>

      {/* 轴分结果 */}
      {bioage && (
        <div className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
          <div className="flex items-baseline justify-between">
            <h3 className="font-semibold text-slate-800">{bioage.axis_label || t('axis.defaultAxis')}</h3>
            <span className="text-3xl font-bold text-slate-800">
              {bioage.axis_score}
              <span className="text-sm font-normal text-slate-400"> / 100</span>
            </span>
          </div>

          <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${scoreColor(bioage.axis_score)}`}
              style={{ width: `${Math.max(0, Math.min(100, bioage.axis_score))}%` }}
            />
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              { t: t('axis.actualAge'), v: bioage.chrono_age },
              { t: t('axis.bioAge'), v: bioage.bio_age },
              { t: t('axis.delta'), v: (bioage.delta > 0 ? '+' : '') + bioage.delta },
            ].map((x) => (
              <div key={x.t} className="bg-slate-50 rounded-xl py-3">
                <p className="text-xs text-slate-500">{x.t}</p>
                <p className="text-xl font-semibold text-slate-800">{x.v}</p>
              </div>
            ))}
          </div>

          {bioage.band && (
            <p className="text-sm text-slate-600 bg-slate-50 rounded-lg px-3 py-2">{bioage.band}</p>
          )}

          {bioage.markers?.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-700 mb-2">{t('axis.markerDetails')}</p>
              <div className="divide-y divide-slate-100">
                {bioage.markers.map((m) => (
                  <div key={m.key} className="flex items-center justify-between py-2 text-sm">
                    <span className="text-slate-700">{m.label}</span>
                    <span className="flex items-center gap-3">
                      <span className="text-slate-500">
                        {m.value}{m.unit ? ` ${m.unit}` : ''}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLE[m.status] || 'bg-slate-100 text-slate-600'}`}>
                        {m.status}
                      </span>
                      <span className="text-xs text-slate-400 w-16 text-right">
                        {m.age_delta > 0 ? '+' : ''}{m.age_delta} {t('axis.years')}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-xs text-slate-400">
            ⚠️ {bioage.not_clinical ? t('axis.notClinical') : ''}{bioage.method}
          </p>
        </div>
      )}

      {/* 八轴评估 */}
      {assess && (
        <div className="space-y-4">
          {assess.banner && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <p className="text-emerald-800 font-medium text-sm">{assess.banner}</p>
            </div>
          )}

          <div className="bg-white rounded-2xl shadow-sm p-6">
            <h3 className="font-semibold text-slate-800 mb-3">{t('axis.axisProfile')}</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {Object.keys(AXIS_KEYS).map((k) => {
                const weak = (assess.weak_axes || []).includes(k);
                const score = assess.axis_scores?.[k];
                return (
                  <div
                    key={k}
                    className={`rounded-xl px-3 py-2 border ${
                      weak ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-slate-50'
                    }`}
                  >
                    <p className="text-xs text-slate-400">
                      {k} · {t(AXIS_KEYS[k])}
                    </p>
                    <p className={`text-sm font-semibold ${weak ? 'text-amber-800' : 'text-slate-700'}`}>
                      {score !== undefined ? score : (weak ? t('axis.weakAxis') : '—')}
                    </p>
                  </div>
                );
              })}
            </div>

            {/* 八轴雷达可视化（零依赖 SVG） */}
            <div className="mt-5 flex justify-center">
              <AxisRadar scores={assess.axis_scores || {}} colors={AXIS_COLORS} />
            </div>

            <p className="text-xs text-slate-400 mt-3">
              {t('axis.noGenomeNote')}
            </p>
          </div>

          {assess.axis_bridges?.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold text-slate-800">
                {t('axis.axisBridges')}（{assess.axis_bridges.length} {t('dashboard.recCount')}）
              </h3>
              {assess.axis_bridges.map((b, i) => (
                <div key={i} className="rounded-xl p-4 shadow-sm bg-sky-50 border border-sky-100">
                  <div className="flex flex-wrap items-center gap-2 mb-1.5">
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-sky-100 text-sky-700">
                      {b.from} · {t(AXIS_KEYS[b.from])}
                    </span>
                    <span className="text-slate-500 text-sm font-medium">
                      {b.direction === 'negative' ? '↑ ' + t('axis.inhibit') : '↔ ' + t('axis.associate')}
                    </span>
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-sky-100 text-sky-700">
                      {b.to} · {t(AXIS_KEYS[b.to])}
                    </span>
                    {b.evidence_level && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-500">
                        {t('axis.evidence')} {b.evidence_level}
                      </span>
                    )}
                  </div>
                  {b.mechanism && (
                    <p className="text-sm text-slate-700 leading-relaxed">{b.mechanism}</p>
                  )}
                  {b.molecules?.length > 0 && (
                    <p className="text-xs text-slate-500 mt-1">
                      {t('axis.keyMolecules')}：{b.molecules.join(' · ')}
                    </p>
                  )}
                  {b.hypothesis_level && (
                    <p className="text-xs text-amber-700 mt-1">
                      {t('axis.hypothesisNote')}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {assess.recommendations?.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold text-slate-800">
                {t('dashboard.personalizedRecs')}（{assess.recommendations.length} {t('dashboard.recCount')}）
              </h3>
              {assess.recommendations.map((r, i) => (
                <div
                  key={i}
                  className={`rounded-xl p-4 shadow-sm ${r.gate_passed ? 'bg-white' : 'bg-red-50 border border-red-200'}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                      r.gate_passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                    }`}>
                      {r.gate_passed ? '✅ ' + t('dashboard.gatePassed') : '🚫 ' + t('dashboard.gateFailed')}
                    </span>
                    <span className="font-medium text-slate-800">{r.name || t('dashboard.recDefault', { n: i + 1 })}</span>
                    {r.mode === 'general' && (
                      <span className="text-xs text-slate-400">（{t('axis.general')}）</span>
                    )}
                  </div>
                  {r.prescription && <p className="text-sm text-slate-600 mt-1">{r.prescription}</p>}
                  {r.monitor_markers && (
                    <p className="text-xs text-slate-400 mt-1">📊 {t('dashboard.monitorMarkers')}：{r.monitor_markers}</p>
                  )}
                  {r.evidence_detail && (
                    <button
                      type="button"
                      onClick={() => { setEvidence(r.evidence_detail); setEvidenceOpen(true); }}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 px-2.5 py-1 rounded-lg transition"
                    >
                      🔬 {t('axis.viewEvidence')}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {assess.disclaimer && (
            <p className="text-xs text-slate-400 leading-relaxed">{assess.disclaimer}</p>
          )}
        </div>
      )}

      {/* 迷你 Turboid：养生方案虚拟推演 */}
      <div className="bg-white rounded-2xl shadow-sm p-6 space-y-4">
        <div>
          <h3 className="font-semibold text-slate-800">🌀 {t('axis.wellnessSim')}</h3>
          <p className="text-slate-500 text-sm mt-1">
            {t('axis.wellnessSimDesc')}
          </p>
        </div>

        <div>
          <p className="text-sm font-medium text-slate-700 mb-2">{t('axis.selectLevers')}</p>
          <div className="flex flex-wrap gap-2">
            {PROJECT_LEVERS.map((lv) => (
              <button
                key={lv.key}
                type="button"
                onClick={() => toggleLever(lv.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  projLevers.includes(lv.key)
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-50 text-slate-600 border border-slate-200 hover:bg-slate-100'
                }`}
              >
                {t(lv.labelKey)}
              </button>
            ))}
          </div>
        </div>

        {/* 个性化基线：使用自测数据 */}
        <div className="flex items-center gap-3">
          <button
            onClick={applyCheckin}
            disabled={checkinLoading || checkinApplied}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-sky-300 text-sky-700 bg-sky-50 hover:bg-sky-100 disabled:opacity-50 transition"
          >
            {checkinLoading ? t('common.loading') : checkinApplied ? '✓ ' + t('axis.checkinApplied') : '📊 ' + t('axis.useCheckin')}
          </button>
          {checkinData && (
            <span className="text-xs text-slate-500">
              {t('axis.baselineSource')}：{checkinData.source === 'latest' ? t('axis.latestCheckin') : t('axis.averageCheckin')}
              （{t('checkin.energy')} {checkinData.energy} / {t('checkin.digestion')} {checkinData.digestion} / {t('checkin.sleep')} {checkinData.sleep}）
            </span>
          )}
          {checkinApplied && (
            <button
              onClick={() => { setCheckinApplied(false); setCheckinData(null); }}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              {t('axis.clearCheckin')}
            </button>
          )}
        </div>

        <div className="flex items-center gap-4">
          <label className="text-sm text-slate-600">
            {t('axis.simulationWeeks')}
            <select
              value={projWeeks}
              onChange={(e) => setProjWeeks(Number(e.target.value))}
              className="ml-2 px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            >
              {[4, 8, 12, 24, 52].map((w) => (
                <option key={w} value={w}>{w} {t('axis.weeks')}</option>
              ))}
            </select>
          </label>
          <button
            onClick={runProject}
            disabled={projLoading || projLevers.length === 0}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {projLoading ? t('axis.simulating') : t('axis.startSimulation')}
          </button>
        </div>
        {projLevers.length === 0 && (
          <p className="text-xs text-amber-600">{t('axis.selectAtLeastOneLever')}</p>
        )}
        {projError && <p className="text-red-500 text-sm">{projError}</p>}

        {projection && (
          <div className="space-y-4 pt-2 border-t border-slate-100">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-slate-50 rounded-xl py-3">
                <p className="text-xs text-slate-500">{t('axis.baselineIndex')}</p>
                <p className="text-xl font-semibold text-slate-800">
                  {projection.trajectory?.[0]?.wellness_index}
                </p>
              </div>
              <div className="bg-emerald-50 rounded-xl py-3">
                <p className="text-xs text-emerald-700">{t('axis.finalIndex')}</p>
                <p className="text-xl font-semibold text-emerald-800">
                  {projection.final?.wellness_index}
                </p>
              </div>
              <div className="bg-slate-50 rounded-xl py-3">
                <p className="text-xs text-slate-500">{t('axis.change')}</p>
                <p className={`text-xl font-semibold ${projection.final?.delta_index >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                  {(projection.final?.delta_index > 0 ? '+' : '') + projection.final?.delta_index}
                </p>
              </div>
            </div>

            <div>
              <p className="text-sm font-medium text-slate-700 mb-2">{t('axis.trajectory')}</p>
              <div className="bg-white border border-slate-100 rounded-xl p-4">
                <TrendChart
                  width={640}
                  series={Object.keys(AXIS_KEYS).map((k) => ({
                    key: k,
                    label: `${k}·${t(AXIS_KEYS[k])}`,
                    color: AXIS_COLORS[k],
                    points: (projection.trajectory || []).map((step) => step.scores?.[k]),
                  }))}
                  xLabels={(projection.trajectory || []).map((_, i) => `W${i + 1}`)}
                />
              </div>
            </div>

            {projection.rate_limiting && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <p className="text-sm font-semibold text-amber-800">
                  ⏳ {t('axis.rateLimitingAxis')}：{projection.rate_limiting.axis} · {projection.rate_limiting.label}
                </p>
                <p className="text-xs text-amber-700 mt-1">{projection.rate_limiting.reason}</p>
              </div>
            )}

            {projection.prioritized_levers?.length > 0 && (
              <div>
                <p className="text-sm font-medium text-slate-700 mb-1">{t('axis.priorityLevers')}</p>
                <div className="flex flex-wrap gap-2">
                  {projection.prioritized_levers.map((p) => (
                    <span key={p.lever} className="text-xs px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700">
                      {p.label}（+{p.projected_gain}）
                    </span>
                  ))}
                </div>
              </div>
            )}

            {projection.bridges_activated?.length > 0 && (
              <div>
                <p className="text-sm font-medium text-slate-700 mb-1">{t('axis.activatedBridges')}</p>
                <div className="space-y-1.5">
                  {projection.bridges_activated.map((b, i) => (
                    <div key={i} className="text-xs text-slate-600 bg-slate-50 rounded-lg px-3 py-2 leading-relaxed">
                      <span className="font-semibold text-sky-700">{b.from_label}</span> →{' '}
                      <span className="font-semibold text-sky-700">{b.to_label}</span>：{b.mechanism}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {projection.disclaimer && (
              <p className="text-xs text-slate-400 leading-relaxed">{projection.disclaimer}</p>
            )}
          </div>
        )}
      </div>

      <Modal open={evidenceOpen} title={t('axis.evidenceModalTitle')} onClose={() => setEvidenceOpen(false)}>
        {evidence && (
          <div className="space-y-4 text-sm">
            <div>
              <p className="text-slate-500 text-xs">{t('axis.intervention')}</p>
              <p className="font-medium text-slate-800">{evidence.intervention || '—'}</p>
            </div>
            {evidence.tcm_concept && (
              <div>
                <p className="text-slate-500 text-xs">{t('axis.tcmPerspective')}</p>
                <p className="text-slate-700">{evidence.tcm_concept}</p>
              </div>
            )}
            {evidence.mechanism && (
              <div>
                <p className="text-slate-500 text-xs">{t('axis.mechanism')}</p>
                <p className="text-slate-700 leading-relaxed">{evidence.mechanism}</p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              {evidence.design && (
                <div>
                  <p className="text-slate-500 text-xs">{t('axis.studyDesign')}</p>
                  <p className="text-slate-700">{evidence.design}</p>
                </div>
              )}
              {evidence.population && (
                <div>
                  <p className="text-slate-500 text-xs">{t('axis.population')}</p>
                  <p className="text-slate-700">{evidence.population}</p>
                </div>
              )}
              {evidence.effect_size && (
                <div>
                  <p className="text-slate-500 text-xs">{t('axis.effectSize')}</p>
                  <p className="text-slate-700">{evidence.effect_size}</p>
                </div>
              )}
              {evidence.evidence_level && (
                <div>
                  <p className="text-slate-500 text-xs">{t('axis.evidenceLevel')}</p>
                  <p className="text-slate-700">{evidence.evidence_level}</p>
                </div>
              )}
            </div>
            {evidence.primary_outcomes?.length > 0 && (
              <div>
                <p className="text-slate-500 text-xs">{t('axis.primaryOutcomes')}</p>
                <ul className="list-disc list-inside text-slate-700 space-y-0.5">
                  {evidence.primary_outcomes.map((o, i) => (
                    <li key={i}>{o}</li>
                  ))}
                </ul>
              </div>
            )}
            {evidence.source && (
              <div className="bg-slate-50 rounded-lg px-3 py-2">
                <p className="text-slate-500 text-xs">{t('axis.literatureSource')}</p>
                <p className="text-slate-700">
                  {evidence.source.journal || '—'}
                  {evidence.source.year ? ` (${evidence.source.year})` : ''}
                </p>
                {evidence.source.doi && (
                  <p className="text-xs text-emerald-700 break-all">DOI: {evidence.source.doi}</p>
                )}
              </div>
            )}
            {evidence.fusion_note && (
              <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                {t('axis.fusionNote')}：{evidence.fusion_note}
              </p>
            )}
            <p className="text-xs text-slate-400 leading-relaxed border-t border-slate-100 pt-3">
              {t('axis.evidenceDisclaimer')}
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
