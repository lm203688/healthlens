import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import HealthDisclaimer from '../components/HealthDisclaimer';

/* 特征字段：键名必须与 data/pulse_signatures.json 的 device_output_contract
 * 以及 edge/healthgateway/pulse_source.py 输出一致，改名会全部读成 None。 */
const FIELDS = [
  { key: 'hl.pulse.rate_bpm',           label: 'pulse.fRate',  type: 'number', step: '0.1', hint: 'pulse.hRate' },
  { key: 'hl.pulse.h1',                 label: 'pulse.fH1',    type: 'number', step: '0.001', hint: 'pulse.hH1' },
  { key: 'hl.pulse.h3_h1',              label: 'pulse.fH3H1',  type: 'number', step: '0.001' },
  { key: 'hl.pulse.h4_h1',              label: 'pulse.fH4H1',  type: 'number', step: '0.001' },
  { key: 'hl.pulse.h5_h1',              label: 'pulse.fH5H1',  type: 'number', step: '0.001' },
  { key: 'hl.pulse.dicrotic_present',   label: 'pulse.fDicrotic', type: 'number', step: '1' },
  { key: 'hl.pulse.ascending_slope',    label: 'pulse.fSlope', type: 'number', step: '0.001' },
  { key: 'hl.pulse.perfusion_index',    label: 'pulse.fPerf',  type: 'number', step: '0.001' },
  { key: 'hl.pulse.rhythm_regularity',  label: 'pulse.fRhythm', type: 'number', step: '0.001' },
];

const DEPTHS = [
  { value: '',               label: 'pulse.depthAuto' },
  { value: 'superficial',    label: 'pulse.depthSuperficial' },
  { value: 'deep',           label: 'pulse.depthDeep' },
];

const PAUSES = [
  { value: 'none',      label: 'pulse.pauseNone' },
  { value: 'irregular', label: 'pulse.pauseIrregular' },
  { value: 'regular',   label: 'pulse.pauseRegular' },
];

const SEVERITY_STYLE = {
  normal: { box: 'bg-emerald-50 border-emerald-300', text: 'text-emerald-800', label: 'pulse.sevNormal' },
  watch:  { box: 'bg-amber-50 border-amber-300',     text: 'text-amber-800',   label: 'pulse.sevWatch' },
  alert:  { box: 'bg-red-50 border-red-400',         text: 'text-red-800',     label: 'pulse.sevAlert' },
};

/* 基线样本：一组健康基线特征，便于无硬件时先看到完整页面效果 */
const SAMPLE = {
  'hl.pulse.rate_bpm': 68,
  'hl.pulse.h1': 0.52,
  'hl.pulse.h3_h1': 0.6,
  'hl.pulse.h4_h1': 0.5,
  'hl.pulse.h5_h1': 0.41,
  'hl.pulse.dicrotic_present': 1,
  'hl.pulse.ascending_slope': 0.49,
  'hl.pulse.perfusion_index': 0.52,
  'hl.pulse.rhythm_regularity': 0.96,
};

export default function PulseDevice() {
  const { t } = useTranslation();
  const [features, setFeatures] = useState({ ...SAMPLE });
  const [depth, setDepth] = useState('');
  const [pause, setPause] = useState('none');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function setField(key, value) {
    setFeatures((prev) => ({ ...prev, [key]: value }));
  }

  async function handleInterpret(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const payload = { ...features, 'hl.pulse.depth': depth, 'hl.pulse.pause_pattern': pause };
      // 去掉空值，避免把 0 当成有效读数
      const clean = {};
      for (const [k, v] of Object.entries(payload)) {
        if (v !== '' && v !== null && v !== undefined) clean[k] = v;
      }
      const resp = await api.pulseInterpret({ features: clean });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || t('pulse.errRequest'));
      }
      setResult(await resp.json());
    } catch (err) {
      setError(err.message || t('pulse.errRequest'));
    } finally {
      setLoading(false);
    }
  }

  function loadSample() {
    setFeatures({ ...SAMPLE });
    setDepth('');
    setPause('none');
    setResult(null);
    setError(null);
  }

  const sev = result ? SEVERITY_STYLE[result.severity] || SEVERITY_STYLE.normal : null;

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">{t('pulse.title')}</h1>
        <p className="text-sm text-gray-600 mt-1">{t('pulse.subtitle')}</p>
      </header>

      <HealthDisclaimer text={t('pulse.disclaimer')} />

      {/* 特征录入 */}
      <form onSubmit={handleInterpret} className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">{t('pulse.formTitle')}</h2>
          <button type="button" onClick={loadSample}
                  className="text-sm text-indigo-600 hover:underline">
            {t('pulse.loadSample')}
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {FIELDS.map((f) => (
            <label key={f.key} className="block">
              <span className="text-xs text-gray-600 block mb-1">
                {t(f.label)}
                {f.hint ? <span className="ml-1 text-gray-400">{t(f.hint)}</span> : null}
              </span>
              <input
                type={f.type}
                step={f.step}
                value={features[f.key] ?? ''}
                onChange={(e) => setField(f.key, e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </label>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs text-gray-600 block mb-1">{t('pulse.depthLabel')}</span>
            <select value={depth} onChange={(e) => setDepth(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
              {DEPTHS.map((d) => <option key={d.value} value={d.value}>{t(d.label)}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-gray-600 block mb-1">{t('pulse.pauseLabel')}</span>
            <select value={pause} onChange={(e) => setPause(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
              {PAUSES.map((p) => <option key={p.value} value={p.value}>{t(p.label)}</option>)}
            </select>
          </label>
        </div>

        <button type="submit" disabled={loading}
                className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50">
          {loading ? t('pulse.interpreting') : t('pulse.interpret')}
        </button>
      </form>

      {error && (
        <div className="bg-red-50 border border-red-300 rounded-xl p-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {/* 解读结果 */}
      {result && (
        <div className="space-y-4">
          <div className={`rounded-xl border p-4 ${sev.box}`}>
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-semibold text-gray-900">{t('pulse.resultTitle')}</h2>
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${sev.box} ${sev.text}`}>
                {t(sev.label)}
              </span>
            </div>

            {/* 脉象标签 */}
            {result.labels?.length ? (
              <div className="flex flex-wrap gap-2 mt-2">
                {result.labels.map((l) => (
                  <span key={l.id}
                        className="inline-flex items-center gap-1.5 text-sm bg-white border border-gray-200 rounded-full px-3 py-1">
                    <span className="font-medium text-gray-900">{l.name}</span>
                    {l.category && <span className="text-xs text-gray-500">{l.category}</span>}
                    <span className="text-xs text-gray-400">{Math.round(l.confidence * 100)}%</span>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-700 mt-2">{t('pulse.noLabels')}</p>
            )}

            {/* 相兼脉 */}
            {result.compounds?.length > 0 && (
              <div className="mt-3 pt-3 border-t border-white/60">
                <h3 className="text-xs font-medium text-gray-700 mb-1.5">{t('pulse.compounds')}</h3>
                <div className="flex flex-wrap gap-2">
                  {result.compounds.map((c, i) => (
                    <span key={`${c.name}-${i}`}
                          className="inline-flex items-center gap-1.5 text-xs bg-white/70 border border-gray-200 rounded-full px-2.5 py-1">
                      <span className="font-medium text-gray-900">{c.name}</span>
                      <span className="text-gray-500">{Math.round(c.confidence * 100)}%</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 八轴信号 */}
            {result.axis_signals && Object.keys(result.axis_signals).length > 0 && (
              <div className="mt-3 pt-3 border-t border-white/60">
                <h3 className="text-xs font-medium text-gray-700 mb-1.5">{t('pulse.axes')}</h3>
                <div className="space-y-1.5">
                  {Object.entries(result.axis_signals).map(([axis, v]) => (
                    <div key={axis} className="flex items-center gap-2">
                      <span className="text-xs text-gray-700 w-28 shrink-0">{axis}</span>
                      <div className="flex-1 h-1.5 bg-white/70 rounded-full overflow-hidden">
                        <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.round(v * 100)}%` }} />
                      </div>
                      <span className="text-xs text-gray-500 w-8 text-right">{v.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 养生参考 + 健康护栏 */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-1">{t('pulse.wellnessTitle')}</h3>
              <p className="text-sm text-gray-700 leading-relaxed">{result.wellness_ref}</p>
            </div>
            <div className={`rounded-lg p-3 ${result.severity === 'alert' ? 'bg-red-50 border border-red-300' : 'bg-gray-50 border border-gray-200'}`}>
              <h3 className={`text-sm font-semibold mb-1 ${result.severity === 'alert' ? 'text-red-800' : 'text-gray-900'}`}>
                {t('pulse.guardrailTitle')}
              </h3>
              <p className={`text-sm leading-relaxed ${result.severity === 'alert' ? 'text-red-800' : 'text-gray-700'}`}>
                {result.guardrail}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
