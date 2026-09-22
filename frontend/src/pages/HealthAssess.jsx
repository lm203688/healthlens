import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import MedicalDisclaimer from '../components/HealthDisclaimer';

const SYMPTOM_CATEGORIES = [
  { titleKey: 'healthAssess.catSleep', items: ['healthAssess.symInsomnia','healthAssess.symEarlyWake','healthAssess.symDifficultySleep','healthAssess.symDaytimeFatigue','healthAssess.symLowEnergy','healthAssess.symDrowsy'] },
  { titleKey: 'healthAssess.catColdHeat', items: ['healthAssess.symColdIntolerance','healthAssess.symColdLimbs','healthAssess.symInternalHeat','healthAssess.symMouthUlcer','healthAssess.symDryMouth','healthAssess.symHotPalmsFeet'] },
  { titleKey: 'healthAssess.catDigest', items: ['healthAssess.symPoorAppetite','healthAssess.symBloating','healthAssess.symDiarrhea','healthAssess.symConstipation','healthAssess.symReflux','healthAssess.symIndigestion'] },
  { titleKey: 'healthAssess.catMood', items: ['healthAssess.symAnxiety','healthAssess.symLowMood','healthAssess.symIrritable','healthAssess.symPoorFocus','healthAssess.symStress','healthAssess.symInsomniaAnxiety'] },
  { titleKey: 'healthAssess.catChronic', items: ['healthAssess.symChronicCough','healthAssess.symNeckShoulder','healthAssess.symHeadache','healthAssess.symJointPain','healthAssess.symChronicInflammation','healthAssess.symLowImmunity'] },
  { titleKey: 'healthAssess.catMetabolic', items: ['healthAssess.symOverweight','healthAssess.symDyslipidemia','healthAssess.symHighGlucose','healthAssess.symHighBP','healthAssess.symHighUricAcid','healthAssess.symEdema'] },
];

const LIFESTYLE_TAGS = [
  { key: 'healthAssess.lifeSedentary', icon: '💺' },
  { key: 'healthAssess.lifeStayUpLate', icon: '🌙' },
  { key: 'healthAssess.lifeNoExercise', icon: '🛋️' },
  { key: 'healthAssess.lifeIrregularDiet', icon: '🍕' },
  { key: 'healthAssess.lifeSmoking', icon: '🚬' },
  { key: 'healthAssess.lifeDrinking', icon: '🍺' },
  { key: 'healthAssess.lifeLongTermMeds', icon: '💊' },
  { key: 'healthAssess.lifeFamilyHistory', icon: '🧬' },
];

export default function HealthAssess() {
  const { t } = useTranslation();
  const [step, setStep] = useState(1);
  const [symptoms, setSymptoms] = useState([]);
  const [lifestyle, setLifestyle] = useState([]);
  const [freeText, setFreeText] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function toggleSymptom(item) {
    setSymptoms(p => p.includes(item) ? p.filter(s => s !== item) : [...p, item]);
  }

  function toggleLifestyle(item) {
    setLifestyle(p => p.includes(item) ? p.filter(s => s !== item) : [...p, item]);
  }

  async function submit() {
    if (symptoms.length === 0 && lifestyle.length === 0 && !freeText.trim()) {
      setError(t('healthAssess.pleaseSelectOne'));
      return;
    }

    setLoading(true);
    setError(null);
    const parts = [];
    if (freeText.trim()) parts.push(freeText.trim());
    if (symptoms.length) parts.push(t('healthAssess.symptomsLabel') + symptoms.join('、'));
    if (lifestyle.length) parts.push(t('healthAssess.lifestyleLabel') + lifestyle.join('、'));

    try {
      const resp = await api.agentFusion({ user_input: parts.join(' | ') });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.message || t('healthAssess.analyzeFailed'));
      setResult(data);
      setStep(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (step === 1) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <MedicalDisclaimer />
        <div>
          <h2 className="text-2xl font-bold">🩺 {t('healthAssess.title')}</h2>
          <p className="text-slate-500 text-sm mt-1">{t('healthAssess.subtitle')}</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-4">{t('healthAssess.selectSymptoms')}</h3>
          <div className="space-y-4">
            {SYMPTOM_CATEGORIES.map((cat, ci) => (
              <div key={ci} className="space-y-2">
                <p className="text-sm font-medium text-slate-700">{t(cat.titleKey)}</p>
                <div className="flex flex-wrap gap-2">
                  {cat.items.map(itemKey => {
                    const itemLabel = t(itemKey);
                    return (
                    <button
                      key={itemKey}
                      type="button"
                      onClick={() => toggleSymptom(itemLabel)}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition
                        ${symptoms.includes(itemLabel)
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                    >
                      {itemLabel}
                    </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-4">{t('healthAssess.selectLifestyle')}</h3>
          <div className="flex flex-wrap gap-2 mb-4">
            {LIFESTYLE_TAGS.map(tag => {
              const tagLabel = t(tag.key);
              return (
              <button
                key={tag.key}
                type="button"
                onClick={() => toggleLifestyle(tagLabel)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition flex items-center gap-1.5
                  ${lifestyle.includes(tagLabel)
                    ? 'bg-amber-100 text-amber-800 border border-amber-300'
                    : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
              >
                <span>{tag.icon}</span> {tagLabel}
              </button>
              );
            })}
          </div>
          <p className="text-xs text-slate-400">{t('healthAssess.privacyNote')}</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-3">{t('healthAssess.extraDesc')}</h3>
          <textarea
            rows={3}
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            placeholder={t('healthAssess.extraPlaceholder')}
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none text-sm"
          />
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => setStep(2)}
            disabled={symptoms.length === 0 && lifestyle.length === 0 && !freeText.trim()}
            className="flex-1 bg-emerald-600 text-white py-3 rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {t('healthAssess.startAssess')}
          </button>
        </div>
        {error && <p className="text-red-500 text-sm text-center">{error}</p>}
      </div>
    );
  }

  if (step === 2) {
    return (
      <div className="text-center py-16 space-y-4">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-emerald-200 border-t-emerald-600" />
        <h3 className="text-xl font-semibold text-slate-800">{t('healthAssess.loadingTitle')}</h3>
        <p className="text-slate-500">{t('healthAssess.loadingDesc')}</p>
        <div className="flex justify-center gap-3 mt-4">
          {['healthAssess.stepSymptom','healthAssess.stepRisk','healthAssess.stepGate','healthAssess.stepRecommend'].map(key => (
            <span key={key} className="px-3 py-1 bg-slate-100 text-slate-500 text-xs rounded-full">{t(key)}</span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <MedicalDisclaimer />
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-emerald-700">✅ {t('healthAssess.completeTitle')}</h2>
          <p className="text-slate-500 text-sm mt-1">{t('healthAssess.completeDesc')}</p>
        </div>
        <button
          onClick={() => { setStep(1); setResult(null); setSymptoms([]); setLifestyle([]); setFreeText(''); }}
          className="bg-slate-100 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 transition"
        >
          {t('healthAssess.reAssess')}
        </button>
      </div>

      {result?.banner && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
          <p className="text-emerald-800 font-medium">{result.banner}</p>
        </div>
      )}

      {result?.weak_axes && result.weak_axes.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-3">⚠️ {t('healthAssess.focusAreasTitle')}</h3>
          <div className="flex flex-wrap gap-2">
            {result.weak_axes.map((a, i) => (
              <span key={i} className="px-3 py-1.5 bg-amber-100 text-amber-800 text-sm font-medium rounded-lg">
                {a}
              </span>
            ))}
          </div>
        </div>
      )}

      {result?.recommendations && result.recommendations.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold text-slate-800">{t('healthAssess.recsTitle', { count: result.recommendations.length })}</h3>
          {result.recommendations.map((r, i) => (
            <div key={i} className={`rounded-xl p-4 shadow-sm ${r.gate_passed ? 'bg-white' : 'bg-red-50 border border-red-200'}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${r.gate_passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                  {r.gate_passed ? t('healthAssess.gatePassed') : t('healthAssess.gateFailed')}
                </span>
                <span className="font-medium text-slate-800">{r.name || t('healthAssess.defaultRec', { n: i + 1 })}</span>
              </div>
              {r.prescription && <p className="text-sm text-slate-600 mt-1">{r.prescription}</p>}
              {r.monitor_markers && <p className="text-xs text-slate-400 mt-1">📊 {t('healthAssess.monitorMarkers')}：{r.monitor_markers}</p>}
              {r.evidence_level && <p className="text-xs text-slate-400 mt-0.5">📚 {t('healthAssess.evidenceLevel')}：{r.evidence_level}</p>}
            </div>
          ))}
        </div>
      )}

      {result?.evidence_chain && result.evidence_chain.length > 0 && (
        <details className="bg-white rounded-2xl shadow-sm p-6">
          <summary className="cursor-pointer font-medium text-slate-800">📚 {t('healthAssess.evidenceChainTitle', { count: result.evidence_chain.length })}</summary>
          <ul className="mt-3 space-y-1 text-sm text-slate-600">
            {result.evidence_chain.map((c, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-xs text-slate-400 mt-0.5 shrink-0">[{c.evidence_level}]</span>
                <span>{c.name} — {c.tcm_source || c.gene_relevance || t('healthAssess.generalRec')}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
