import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import MedicalDisclaimer from '../components/HealthDisclaimer';
import SelfCheck from '../components/SelfCheck';

const METRIC_DEFS = [
  { code: '8867-4', key: 'checkin.metricBloodSbp', unit: 'mmHg', refLow: 90, refHigh: 140, type: 'number' },
  { code: '8480-6', key: 'checkin.metricBloodDbp', unit: 'mmHg', refLow: 60, refHigh: 90, type: 'number' },
  { code: '8867-4', key: 'checkin.metricHeartRate', unit: 'bpm', refLow: 60, refHigh: 100, type: 'number' },
  { code: '2339-0', key: 'checkin.metricGlucose', unit: 'mmol/L', refLow: 3.9, refHigh: 6.1, type: 'number' },
  { code: '2160-0', key: 'checkin.metricWeight', unit: 'kg', refLow: 0, refHigh: 999, type: 'number' },
  { code: '8302-2', key: 'checkin.metricTemp', unit: '°C', refLow: 36.1, refHigh: 37.2, type: 'number' },
  { code: '8932-2', key: 'checkin.metricSpO2', unit: '%', refLow: 95, refHigh: 100, type: 'number' },
  { code: 'custom', key: 'checkin.metricSleepQuality', unit: '', refLow: 0, refHigh: 5, type: 'string', options: ['checkin.optVeryBad','checkin.optBad','checkin.optNormal','checkin.optGood','checkin.optVeryGood'] },
  { code: 'custom', key: 'checkin.metricMood', unit: '', refLow: 0, refHigh: 5, type: 'string', options: ['checkin.optVeryBad','checkin.optBad','checkin.optNormal','checkin.optGood','checkin.optVeryGood'] },
  { code: 'custom', key: 'checkin.metricEnergy', unit: '', refLow: 0, refHigh: 5, type: 'string', options: ['checkin.optVeryBad','checkin.optBad','checkin.optNormal','checkin.optGood','checkin.optVeryGood'] },
];

export default function CheckIn() {
  const { t } = useTranslation();
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    fetchHistory();
  }, []);

  async function fetchHistory() {
    try {
      const resp = await api.observations();
      const data = await resp.json();
      const items = data.results || data.items || data.data || data.observations || (Array.isArray(data) ? data : []);
      if (Array.isArray(items)) setHistory(items.slice(0, 20));
    } catch {
      // silent
    }
  }

  function setMetricValue(code, value) {
    setValues(p => ({ ...p, [code]: value }));
  }

  async function submitCheckIn() {
    const entries = Object.entries(values).filter(([, v]) => v !== '' && v != null);
    if (entries.length === 0) {
      setError(t('checkin.pleaseFillAtLeastOne'));
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    const payloads = entries.map(([code, value]) => {
      const metric = METRIC_DEFS.find(m => m.code === code);
      const nameKey = metric ? metric.key : code;
      const displayName = metric ? t(nameKey) : code;
      const payload = {
        loinc_code: metric ? metric.code : 'custom',
        loinc_name: displayName,
        value_unit: metric ? metric.unit : '',
        source: 'manual',
      };

      if (metric && metric.options) {
        payload.value_string = String(value);
        payload.value_numeric = metric.options.indexOf(String(value));
      } else {
        payload.value_numeric = parseFloat(value);
      }

      if (metric) {
        payload.reference_range_low = metric.refLow;
        payload.reference_range_high = metric.refHigh;
      }

      return payload;
    });

    try {
      const now = new Date().toISOString();
      const endpoint = entries.length > 1 ? api.observationsBatch : api.observationPost;
      const payload = entries.length > 1
        ? { items: payloads.map(p => ({ ...p, recorded_at: now })) }
        : { ...payloads[0], recorded_at: now };
      const resp = await endpoint(payload);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.message || t('checkin.submitFailed'));
      setSuccess(t('checkin.submitSuccess', { count: entries.length }));
      setValues({});
      fetchHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const glucoseKey = 'checkin.metricGlucose';
  const weightKey = 'checkin.metricWeight';

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <MedicalDisclaimer />
      <div>
        <h2 className="text-2xl font-bold">📅 {t('checkin.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">{t('checkin.subtitle')}</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {METRIC_DEFS.map((m, i) => {
            const name = t(m.key);
            return (
            <div key={i} className="space-y-1">
              <label className="text-sm font-medium text-slate-700">
                {name} {m.unit ? <span className="text-xs text-slate-400">({m.unit})</span> : ''}
              </label>
              {m.type === 'number' ? (
                <input
                  type="number"
                  step="any"
                  placeholder={m.key === glucoseKey ? '5.2' : m.key === weightKey ? '65' : ''}
                  value={values[m.code] || ''}
                  onChange={(e) => setMetricValue(m.code, e.target.value)}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none text-sm"
                />
              ) : (
                <div className="flex gap-1.5 flex-wrap">
                  {m.options.map(optKey => {
                    const optLabel = t(optKey);
                    return (
                    <button
                      key={optKey}
                      type="button"
                      onClick={() => setMetricValue(m.code, optLabel)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition
                        ${values[m.code] === optLabel
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                    >
                      {optLabel}
                    </button>
                    );
                  })}
                </div>
              )}
              {m.refLow > 0 && m.refHigh < 999 && (
                <p className="text-xs text-slate-400">{t('checkin.referenceRange')}：{m.refLow}–{m.refHigh} {m.unit}</p>
              )}
            </div>
            );
          })}
        </div>

        <div className="mt-6 flex gap-3">
          <button
            onClick={submitCheckIn}
            disabled={loading || Object.keys(values).length === 0}
            className="bg-emerald-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {loading ? t('checkin.submitting') : `📤 ${t('checkin.submitBtn', { count: Object.keys(values).length })}`}
          </button>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="bg-slate-100 text-slate-700 px-4 py-2.5 rounded-lg font-medium hover:bg-slate-200 transition text-sm"
          >
            📋 {t('checkin.historyBtn')}
          </button>
        </div>

        {error && <div className="mt-3 bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>}
        {success && <div className="mt-3 bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{success}</div>}
      </div>

      {showHistory && (
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-4">📋 {t('checkin.recentRecords')}</h3>
          {history.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">{t('checkin.noRecords')}</p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {history.map((item, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div>
                    <span className="font-medium text-sm text-slate-800">{item.loinc_name || item.name || item.code}</span>
                    <span className="text-xs text-slate-400 ml-2">{item.source || ''}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold">
                      {item.value_numeric != null ? `${item.value_numeric} ${item.value_unit || ''}` : item.value_string || '—'}
                    </span>
                    {item.is_abnormal && <span className="text-xs text-red-500 ml-2">⚠️</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="pt-2">
        <SelfCheck />
      </div>
    </div>
  );
}
