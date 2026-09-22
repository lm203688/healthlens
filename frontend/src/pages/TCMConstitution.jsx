import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import MedicalDisclaimer from '../components/HealthDisclaimer';

const NINE_TYPES = {
  pinghe:   { key: 'tcm.pinghe',   color: 'bg-emerald-50 border-emerald-300',  dot: 'text-emerald-600', descKey: 'tcm.pingheDesc' },
  qixu:     { key: 'tcm.qixu',     color: 'bg-blue-50 border-blue-300',        dot: 'text-blue-600',    descKey: 'tcm.qixuDesc' },
  yangxu:   { key: 'tcm.yangxu',   color: 'bg-orange-50 border-orange-300',    dot: 'text-orange-600',  descKey: 'tcm.yangxuDesc' },
  yinxu:    { key: 'tcm.yinxu',    color: 'bg-red-50 border-red-300',          dot: 'text-red-600',     descKey: 'tcm.yinxuDesc' },
  tanshi:   { key: 'tcm.tanshi',   color: 'bg-slate-50 border-slate-300',      dot: 'text-slate-600',   descKey: 'tcm.tanshiDesc' },
  shire:    { key: 'tcm.shire',    color: 'bg-amber-50 border-amber-300',      dot: 'text-amber-600',   descKey: 'tcm.shireDesc' },
  xueyu:    { key: 'tcm.xueyu',    color: 'bg-purple-50 border-purple-300',    dot: 'text-purple-600',  descKey: 'tcm.xueyuDesc' },
  qiyu:     { key: 'tcm.qiyu',     color: 'bg-indigo-50 border-indigo-300',    dot: 'text-indigo-600',  descKey: 'tcm.qiyuDesc' },
  tebing:   { key: 'tcm.tebing',   color: 'bg-pink-50 border-pink-300',        dot: 'text-pink-600',    descKey: 'tcm.tebingDesc' },
};

const QUESTIONNAIRE = [
  { key: 'tcm.q0', field: 'fatigue', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q1', field: 'cold', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q2', field: 'sweat', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q3', field: 'sleep', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q4', field: 'mood', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q5', field: 'infection', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q6', field: 'digest', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q7', field: 'heat', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q8', field: 'allergy', options: ['dashboard.optRarely','dashboard.optOccasionally','dashboard.optOften','dashboard.optAlways'] },
  { key: 'tcm.q9', field: 'body', options: ['tcm.bodyThin','tcm.bodyNormal','tcm.bodyOverweight'] },
];

export default function TCMConstitution() {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));

  const scoreMap = {
    [t('dashboard.optRarely')]: 0,
    [t('dashboard.optOccasionally')]: 1,
    [t('dashboard.optOften')]: 2,
    [t('dashboard.optAlways')]: 3,
    [t('checkin.optVeryGood')]: 3,
    [t('checkin.optNormal')]: 2,
    [t('checkin.optBad')]: 1,
    [t('checkin.optVeryBad')]: 0,
  };

  useEffect(() => {
    loadExisting();
  }, []);

  async function loadExisting() {
    if (!token) return;
    try {
      const resp = await api.tcmConstitution();
      if (resp.ok) {
        const data = await resp.json();
        if (data?.data) setResult(data.data);
      }
    } catch {
      // no existing profile
    }
  }

  async function handleAnalyze() {
    setLoading(true);
    setError(null);
    const questionnaire = {};
    for (const [k, v] of Object.entries(answers)) {
      questionnaire[k] = typeof v === 'string' ? v : scoreMap[v] ?? 0;
    }

    try {
      const resp = await api.tcmConstitutionPost({ questionnaire_data: questionnaire });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.message || t('tcm.analyzeFailed'));
      if (data?.data) setResult(data.data);
      else setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const hasAllAnswers = Object.keys(answers).length >= 6;
  const mainType = result?.constitution_type;
  const typeInfo = mainType ? NINE_TYPES[mainType] : null;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <MedicalDisclaimer />
      <div>
        <h2 className="text-2xl font-bold">🏥 {t('tcm.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">{t('tcm.subtitle')}</p>
      </div>

      <form className="space-y-4 bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800">{t('tcm.questionnaireHeader')}</h3>
        {QUESTIONNAIRE.map((item, i) => (
          <div key={i} className="space-y-1.5">
            <p className="text-sm font-medium text-slate-700">{t(item.key)}</p>
            <div className="flex gap-2">
              {item.options.map(optKey => {
                const optLabel = t(optKey);
                return (
                <button
                  key={optKey}
                  type="button"
                  onClick={() => setAnswers(p => ({ ...p, [item.field]: optLabel }))}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition
                    ${answers[item.field] === optLabel
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                >
                  {optLabel}
                </button>
                );
              })}
            </div>
          </div>
        ))}
        <button
          type="button"
          onClick={handleAnalyze}
          disabled={loading || !hasAllAnswers}
          className="bg-emerald-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
        >
          {loading ? t('tcm.analyzing') : `🔍 ${t('tcm.analyzeBtn', { done: Object.keys(answers).length, total: QUESTIONNAIRE.length })}`}
        </button>
      </form>

      {error && <div className="bg-red-50 text-red-600 p-4 rounded-lg text-sm">{error}</div>}

      {typeInfo && (
        <div className={`${typeInfo.color} border-2 rounded-2xl p-6 space-y-4`}>
          <div className="flex items-center gap-3">
            <span className={`text-3xl ${typeInfo.dot}`}>●</span>
            <div>
              <h3 className="text-2xl font-bold text-slate-800">{t(typeInfo.key)}</h3>
              <p className="text-sm text-slate-600 mt-1">{t(typeInfo.descKey)}</p>
            </div>
          </div>

          {result?.constitution_score && (
            <div className="bg-white/80 rounded-xl p-4">
              <h4 className="font-medium text-sm text-slate-700 mb-3">{t('tcm.nineScoreTitle')}</h4>
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(result.constitution_score).map(([key, score]) => {
                  const info = NINE_TYPES[key];
                  if (!info) return null;
                  const pct = Math.min(100, (typeof score === 'number' ? score : 0) * 100);
                  const isMain = key === mainType;
                  return (
                    <div key={key} className={`text-center p-2 rounded-lg ${isMain ? 'bg-white shadow-sm ring-2 ring-emerald-300' : 'bg-white/50'}`}>
                      <p className={`text-xs font-medium ${isMain ? info.dot : 'text-slate-500'}`}>{t(info.key)}</p>
                      <div className="w-full bg-slate-200 rounded-full h-1.5 mt-1.5">
                        <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{pct.toFixed(0)}%</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {result?.recommendations && result.recommendations.length > 0 && (
            <div className="bg-white/80 rounded-xl p-4">
              <h4 className="font-medium text-sm text-slate-700 mb-3">{t('tcm.recommendTitle')}</h4>
              <ul className="space-y-2">
                {result.recommendations.slice(0, 5).map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="text-emerald-600 mt-0.5 shrink-0">●</span>
                    <span>{r.prescription || r.description || r.name || t('tcm.defaultRec', { n: i + 1 })}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {!typeInfo && !loading && !error && (
        <div className="text-center py-8 text-slate-400 text-sm">
          {t('tcm.finishHint')}
        </div>
      )}
    </div>
  );
}
