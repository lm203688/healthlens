import { useState, useEffect } from 'react';
import { api } from '../api/client';

/* 八轴稳态模型（A–H）。代谢-炎症轴按假说级映射落点 A / F。 */
const AXIS_LABELS = {
  A: { name: '气化 / 自噬', note: 'AMPK-mTOR 能量感应' },
  B: { name: '气血 / 线粒体', note: '能量代谢与氧化应激' },
  C: { name: '络脉 / 清瘀', note: '微循环与血液流变' },
  D: { name: '阴阳 / 昼夜', note: '昼夜节律与睡眠稳态' },
  E: { name: '脏腑 / 神经内分泌', note: 'HPA 轴与内分泌调节' },
  F: { name: '正邪 / 炎症', note: '炎症负荷与免疫监视' },
  G: { name: '神 / 情志', note: '情绪与应激心理' },
  H: { name: '先天 / 肾精', note: '先天禀赋与修复储备' },
};

const MARKER_FIELDS = [
  { key: 'glucose',       label: '空腹血糖',      unit: 'mmol/L', step: '0.1',  hint: '3.9–6.1' },
  { key: 'hba1c',         label: '糖化血红蛋白',  unit: '%',      step: '0.1',  hint: '< 5.7' },
  { key: 'hs_crp',        label: '超敏C反应蛋白', unit: 'mg/L',   step: '0.1',  hint: '< 1.0' },
  { key: 'waist_cm',      label: '腰围',          unit: 'cm',     step: '1',    hint: '男 < 90 / 女 < 85' },
  { key: 'hdl',           label: '高密度脂蛋白',  unit: 'mmol/L', step: '0.01', hint: '男 > 1.0 / 女 > 1.3' },
  { key: 'triglycerides', label: '甘油三酯',      unit: 'mmol/L', step: '0.01', hint: '< 1.7' },
  { key: 'sbp',           label: '收缩压',        unit: 'mmHg',   step: '1',    hint: '< 120' },
  { key: 'bmi',           label: '体质指数',      unit: '',       step: '0.1',  hint: '18.5–23.9' },
];

const STATUS_STYLE = {
  good: 'bg-emerald-100 text-emerald-700',
  watch: 'bg-amber-100 text-amber-700',
  poor: 'bg-red-100 text-red-700',
};

function scoreColor(score) {
  if (score >= 75) return 'bg-emerald-500';
  if (score >= 60) return 'bg-amber-500';
  return 'bg-red-500';
}

export default function AxisProfile() {
  const [chronoAge, setChronoAge] = useState(40);
  const [isMale, setIsMale] = useState(true);
  const [values, setValues] = useState({});
  const [meta, setMeta] = useState(null);
  const [bioage, setBioage] = useState(null);
  const [assess, setAssess] = useState(null);
  const [loading, setLoading] = useState('');
  const [error, setError] = useState(null);

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
      if (!resp.ok) throw new Error(data.detail || '分析失败');
      if (kind === 'bioage') setBioage(data.data);
      else setAssess(data.data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading('');
    }
  }

  const mapped = meta?.mapped_axes || ['A', 'F'];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">🧭 八轴稳态评估</h2>
        <p className="text-slate-500 text-sm mt-1">
          用常规体检指标量化「{meta?.axis_label || '代谢-炎症轴'}」，并映射到八轴稳态模型给出个性化建议
        </p>
      </div>

      {meta && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-xs text-slate-600">
          ⚗️ 方法：{meta.method} · 弱轴阈值 &lt; {meta.weak_threshold} · 落点轴{' '}
          {mapped.map((a) => `${a}（${AXIS_LABELS[a]?.name || a}）`).join('、')}
        </div>
      )}

      {/* 输入 */}
      <div className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
        <h3 className="font-semibold text-slate-800">体检指标（缺项留空即可，不影响其余评分）</h3>

        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm">
            <span className="block text-slate-600 mb-1">实际年龄</span>
            <input
              type="number" min="1" max="120" value={chronoAge}
              onChange={(e) => setChronoAge(e.target.value)}
              className="w-24 px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            />
          </label>
          <div>
            <span className="block text-slate-600 mb-1 text-sm">性别</span>
            <div className="flex gap-2">
              {[{ v: true, t: '男' }, { v: false, t: '女' }].map((o) => (
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
                {f.label} {f.unit && <span className="text-slate-400 text-xs">{f.unit}</span>}
              </span>
              <input
                type="number" step={f.step} placeholder={f.hint}
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
            {loading === 'bioage' ? '计算中…' : '计算轴分与生物学年龄'}
          </button>
          <button
            onClick={() => run('assess')} disabled={!!loading}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {loading === 'assess' ? '分析中…' : '八轴个性化评估 →'}
          </button>
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
      </div>

      {/* 轴分结果 */}
      {bioage && (
        <div className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
          <div className="flex items-baseline justify-between">
            <h3 className="font-semibold text-slate-800">{bioage.axis_label || '代谢-炎症轴'}</h3>
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
              { t: '实际年龄', v: bioage.chrono_age },
              { t: '生物学年龄', v: bioage.bio_age },
              { t: '偏移', v: (bioage.delta > 0 ? '+' : '') + bioage.delta },
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
              <p className="text-sm font-medium text-slate-700 mb-2">标志物明细</p>
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
                        {m.age_delta > 0 ? '+' : ''}{m.age_delta} 岁
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-xs text-slate-400">
            ⚠️ {bioage.not_clinical ? '非临床指标：' : ''}{bioage.method}
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
            <h3 className="font-semibold text-slate-800 mb-3">八轴稳态画像</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {Object.keys(AXIS_LABELS).map((k) => {
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
                      {k} · {AXIS_LABELS[k].name}
                    </p>
                    <p className={`text-sm font-semibold ${weak ? 'text-amber-800' : 'text-slate-700'}`}>
                      {score !== undefined ? score : (weak ? '偏弱' : '—')}
                    </p>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 mt-3">
              未提供基因/组学数据时，仅代谢-炎症轴参与评分，其余轴显示为「—」。
            </p>
          </div>

          {assess.recommendations?.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold text-slate-800">
                个性化建议（{assess.recommendations.length} 条）
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
                      {r.gate_passed ? '✅ 通过' : '🚫 需警惕'}
                    </span>
                    <span className="font-medium text-slate-800">{r.name || `建议 ${i + 1}`}</span>
                    {r.mode === 'general' && (
                      <span className="text-xs text-slate-400">（通用）</span>
                    )}
                  </div>
                  {r.prescription && <p className="text-sm text-slate-600 mt-1">{r.prescription}</p>}
                  {r.monitor_markers && (
                    <p className="text-xs text-slate-400 mt-1">📊 监测指标：{r.monitor_markers}</p>
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
    </div>
  );
}
