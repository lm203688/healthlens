import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

/** Subjective health self-check (SIIV V-end)
 * Dimensions: energy / digestion / sleep, each 1-5; optional note and date.
 * Long-term tracking for observing personal change trends (data flywheel). Not a medical exam or diagnosis. */
const DIMENSIONS = [
  { key: 'energy_score',   labelKey: 'selfCheck.dimEnergy',   emoji: '⚡' },
  { key: 'digestion_score', labelKey: 'selfCheck.dimDigestion', emoji: '🍃' },
  { key: 'sleep_score',    labelKey: 'selfCheck.dimSleep',    emoji: '🌙' },
];

function ScorePicker({ value, onChange, t }) {
  return (
    <div className="flex gap-1.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className={`w-9 h-9 rounded-lg text-sm font-semibold transition ${
            value === n
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-50 text-slate-500 border border-slate-200 hover:bg-slate-100'
          }`}
          aria-label={t('selfCheck.scoreLabel', { n })}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

export default function SelfCheck() {
  const { t, i18n } = useTranslation();
  const [scores, setScores] = useState({ energy_score: 3, digestion_score: 3, sleep_score: 3 });
  const [note, setNote] = useState('');
  const [date, setDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    loadSummary();
    loadHistory();
  }, []);

  async function loadSummary() {
    try {
      const resp = await api.checkinSummary();
      const data = await resp.json();
      if (data?.success) setSummary(data.data);
    } catch { /* silent */ }
  }

  async function loadHistory() {
    try {
      const resp = await api.checkinHistory({ limit: 12 });
      const data = await resp.json();
      if (data?.success) setHistory(data.data.items || []);
    } catch { /* silent */ }
  }

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);
    const payload = {
      ...scores,
      note: note.trim() || null,
      checkin_date: date ? new Date(date).toISOString() : null,
    };
    try {
      const resp = await api.checkinPost(payload);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail?.message || data?.message || data?.detail || t('selfCheck.submitFailed'));
      setSuccess(data.message || t('selfCheck.recorded'));
      setNote('');
      setDate('');
      loadSummary();
      loadHistory();
    } catch (err) {
      setError(err.message || t('selfCheck.submitFailed'));
    } finally {
      setLoading(false);
    }
  }

  const trend = summary?.trend;
  const dateLocale = i18n.language === 'zh' ? 'zh-CN' : 'en-US';

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
      <div>
        <h3 className="font-semibold text-slate-800">{t('selfCheck.title')}</h3>
        <p className="text-xs text-slate-500 mt-1">
          {t('selfCheck.subtitle')}
        </p>
      </div>

      <form onSubmit={submit} className="space-y-4">
        {DIMENSIONS.map((d) => (
          <div key={d.key} className="flex items-center justify-between gap-4">
            <span className="text-sm font-medium text-slate-700">
              {d.emoji} {t(d.labelKey)}
            </span>
            <ScorePicker
              value={scores[d.key]}
              onChange={(n) => setScores((p) => ({ ...p, [d.key]: n }))}
              t={t}
            />
          </div>
        ))}

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('selfCheck.noteLabel')}</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
            rows={2}
            placeholder={t('selfCheck.notePlaceholder')}
            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('selfCheck.dateLabel')}</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={loading}
            className="bg-emerald-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {loading ? t('selfCheck.submitting') : t('selfCheck.submitBtn')}
          </button>
          <button
            type="button"
            onClick={() => setShowHistory(!showHistory)}
            className="bg-slate-100 text-slate-700 px-4 py-2.5 rounded-lg font-medium hover:bg-slate-200 transition text-sm"
          >
            📋 {t('selfCheck.historyBtn')}
          </button>
        </div>

        {error && <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>}
        {success && <div className="mt-3 bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{success}</div>}
      </form>

      {/* Trend overview */}
      {summary && summary.count > 0 && (
        <div className="border-t border-slate-100 pt-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">
              {t('selfCheck.trendTitle', { count: summary.count })}
            </span>
            {summary.averages?.overall != null && (
              <span className="text-lg font-bold text-emerald-700">
                {summary.averages.overall}
                <span className="text-xs font-normal text-slate-400"> / 5</span>
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {DIMENSIONS.map((d) => (
              <div key={d.key} className="bg-slate-50 rounded-lg py-2">
                <p className="text-[11px] text-slate-500">{t(d.labelKey)}</p>
                <p className="text-sm font-semibold text-slate-800">
                  {summary.averages?.[d.key] ?? '—'}
                  {trend && (
                    <span className={`ml-1 text-[11px] ${trend[d.key] > 0 ? 'text-emerald-600' : trend[d.key] < 0 ? 'text-red-500' : 'text-slate-400'}`}>
                      {trend[d.key] > 0 ? '▲' : trend[d.key] < 0 ? '▼' : '—'}
                      {trend[d.key] !== 0 ? Math.abs(trend[d.key]) : ''}
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>
          {!trend && summary.count < 4 && (
            <p className="text-xs text-slate-400">{t('selfCheck.trendHint', { count: summary.count })}</p>
          )}
        </div>
      )}

      {/* History */}
      {showHistory && (
        <div className="border-t border-slate-100 pt-4">
          <h4 className="text-sm font-medium text-slate-700 mb-3">{t('selfCheck.historyTitle')}</h4>
          {history.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-6">{t('selfCheck.noRecords')}</p>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {history.map((h) => (
                <div key={h.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg text-sm">
                  <span className="text-xs text-slate-500">
                    {h.checkin_date ? new Date(h.checkin_date).toLocaleDateString(dateLocale) : ''}
                  </span>
                  <div className="flex gap-3 text-slate-700">
                    <span>⚡{h.energy_score}</span>
                    <span>🍃{h.digestion_score}</span>
                    <span>🌙{h.sleep_score}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
