import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

export default function Share() {
  const { t } = useTranslation();
  const [generating, setGenerating] = useState(false);
  const [shareResult, setShareResult] = useState(null);
  const [shares, setShares] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchMyShares();
  }, []);

  async function fetchMyShares() {
    try {
      const resp = await api.myShares();
      const data = await resp.json();
      if (data?.success) setShares(data.data?.items || []);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }

  async function handleShare() {
    setGenerating(true);
    setError(null);
    try {
      const resp = await api.reportShare({ report_type: 'health_summary', expires_days: 30 });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || t('share.generating'));
      setShareResult(data.data);
      await fetchMyShares();
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  }

  async function copyLink() {
    if (!shareResult) return;
    const url = `${window.location.origin}${shareResult.share_url}`;
    await navigator.clipboard.writeText(url);
  }

  async function revokeShare(reportId) {
    try {
      await api.revokeShare(reportId);
      setShares((prev) => prev.filter((s) => s.id !== reportId));
      if (shareResult?.id === reportId) setShareResult(null);
    } catch {
      setError(t('share.revokeFailed'));
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">{t('share.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">{t('share.subtitle')}</p>
      </div>

      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg">{error}</div>}

      {/* Generate Share Link */}
      <div className="bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 mb-4">生成分享链接</h3>
        <button
          onClick={handleShare}
          disabled={generating}
          className="bg-emerald-600 text-white px-6 py-3 rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition-colors"
        >
          {generating ? t('share.generating') : t('share.shareBtn')}
        </button>

        {shareResult && (
          <div className="mt-4 p-4 bg-emerald-50 rounded-lg">
            <div className="flex items-center gap-3">
              <input
                type="text"
                readOnly
                value={`${window.location.origin}${shareResult.share_url}`}
                className="flex-1 bg-white border border-emerald-200 rounded-lg px-3 py-2 text-sm text-slate-600"
              />
              <button
                onClick={copyLink}
                className="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-emerald-700"
              >
                {t('share.copyBtn')}
              </button>
            </div>
            <div className="mt-2 text-xs text-slate-500">
              {t('share.expiresIn')} {shareResult.expires_at ? new Date(shareResult.expires_at).toLocaleDateString() : '—'}
            </div>
          </div>
        )}
      </div>

      {/* My Shares */}
      <div className="bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 mb-4">{t('share.myShares')}</h3>
        {loading ? (
          <div className="text-center py-8 text-slate-400">{t('common.loading')}</div>
        ) : shares.length === 0 ? (
          <div className="text-center py-8 text-slate-400">{t('share.noShares')}</div>
        ) : (
          <div className="space-y-3">
            {shares.map((share) => (
              <div key={share.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                <div>
                  <div className="font-medium text-slate-800">{share.title}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    {t('share.shareCount')} {share.view_count} {t('share.times')} · {t('share.expiresIn')} {share.expires_at ? new Date(share.expires_at).toLocaleDateString() : '长期'}
                  </div>
                </div>
                <button
                  onClick={() => revokeShare(share.id)}
                  className="text-red-500 text-sm hover:text-red-700"
                >
                  {t('share.revokeBtn')}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
