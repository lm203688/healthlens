import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import MedicalDisclaimer from '../components/HealthDisclaimer';

export default function Reports() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    fetchReports();
  }, []);

  async function fetchReports() {
    setLoading(true);
    try {
      const resp = await api.reports();
      const d = await resp.json();
      setData(d);
      // Also load observation summary
      try {
        const obsResp = await api.observationSummary();
        const obsData = await obsResp.json();
        setData((prev) => ({ ...prev, observations: obsData }));
      } catch {
        // non-fatal
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <MedicalDisclaimer />
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">{t('reports.title')}</h2>
          <p className="text-slate-500 text-sm mt-1">{t('reports.subtitle')}</p>
        </div>
        <button
          onClick={fetchReports}
          disabled={loading}
          className="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
        >
          {loading ? t('reports.loading') : `🔄 ${t('reports.refreshBtn')}`}
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg">{error}</div>}
      {loading && <div className="text-center py-8 text-slate-500">{t('reports.loadingReport')}</div>}

      {data && !error && !loading && <ReportContent data={data} />}

      {!data && !error && !loading && (
        <div className="text-center py-12 text-slate-400">
          <div className="text-4xl mb-3">📊</div>
          <p>{t('reports.noReportData')}</p>
          <a href="/assess" className="text-emerald-600 underline mt-2 inline-block">{t('reports.goToAssess')}</a>
        </div>
      )}
    </div>
  );
}

function ReportContent({ data }) {
  const { t } = useTranslation();
  const overview = data.overview || data.data || data;
  const obs = data.observations;

  return (
    <div className="space-y-6">
      <OverviewCard data={overview} />

      {obs && <ObservationSummary data={obs} />}

      <details className="bg-white rounded-xl shadow-sm p-5">
        <summary className="cursor-pointer font-medium text-slate-700">📋 {t('reports.rawData')}</summary>
        <pre className="mt-3 text-xs text-slate-600 bg-slate-50 rounded-lg p-3 overflow-auto max-h-72">
          {JSON.stringify(data, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function OverviewCard({ data }) {
  const { t } = useTranslation();
  const axes = data.weak_axes || data.axes || data.axis_scores || {};
  const score = data.fusion_score || data.score || data.total_score;
  const risk = data.risk_level || data.risk || '—';
  const tcm = data.tcm_type || data.constitution || '—';

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <h3 className="font-semibold text-slate-800 mb-4">📈 {t('reports.overviewTitle')}</h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MiniStat label={t('reports.scoreLabel')} value={score} color="emerald" />
        <MiniStat label={t('reports.riskLabel')} value={risk} color="rose" />
        <MiniStat label={t('reports.tcmLabel')} value={tcm} color="blue" />
        <MiniStat label={t('reports.focusLabel')} value={Array.isArray(axes) ? axes.join(', ') : Object.keys(axes).join(', ')} color="amber" />
      </div>

      {typeof axes === 'object' && !Array.isArray(axes) && Object.keys(axes).length > 0 && (
        <div className="mt-5">
          <h4 className="text-sm font-medium text-slate-600 mb-2">{t('reports.axesTitle')}</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(axes).map(([key, val]) => (
              <div key={key} className="flex items-center gap-2">
                <span className="text-xs text-slate-500 w-8">{key}</span>
                <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full transition-all"
                    style={{ width: `${Math.min(100, Math.max(0, val * 100))}%` }}
                  />
                </div>
                <span className="text-xs text-slate-600 w-8 text-right">{val}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, color }) {
  const colors = {
    emerald: 'bg-emerald-50 text-emerald-700',
    rose: 'bg-rose-50 text-rose-700',
    blue: 'bg-blue-50 text-blue-700',
    amber: 'bg-amber-50 text-amber-700',
  };
  return (
    <div className={`${colors[color] || 'bg-slate-50'} rounded-xl p-3`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-sm font-bold mt-1 break-all">{value || '—'}</p>
    </div>
  );
}

function ObservationSummary({ data }) {
  const { t } = useTranslation();
  const total = data.total_items || data.total || 0;
  const abnormal = data.abnormal_count || data.abnormal || 0;
  const categories = data.categories || [];

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <h3 className="font-semibold text-slate-800 mb-4">📋 {t('reports.observationTitle')}</h3>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-slate-50 rounded-xl p-3">
          <p className="text-xs text-slate-500">{t('reports.recordedCount')}</p>
          <p className="text-xl font-bold">{total}</p>
        </div>
        <div className="bg-amber-50 rounded-xl p-3">
          <p className="text-xs text-slate-500">{t('reports.abnormalCount')}</p>
          <p className="text-xl font-bold text-amber-700">{abnormal}</p>
        </div>
      </div>

      {categories.length > 0 && (
        <div className="space-y-2">
          {categories.map((cat, i) => (
            <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div>
                <span className="font-medium text-sm text-slate-800">{cat.name}</span>
                <span className="text-xs text-slate-400 ml-2">({cat.code})</span>
              </div>
              <div className="text-right">
                <span className="text-sm font-bold">{cat.latest} {cat.unit || ''}</span>
                {cat.is_abnormal && <span className="text-xs text-red-500 ml-2">⚠️ {t('reports.abnormal')}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {categories.length === 0 && (
        <p className="text-sm text-slate-400 text-center py-4">{t('reports.noObservationData')}</p>
      )}
    </div>
  );
}
