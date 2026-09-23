import { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

const UPLOAD_TYPES = [
  {
    key: 'genome',
    titleKey: 'upload.genomeFile',
    descKey: 'upload.genomeDesc',
    formatKey: 'upload.genomeFormat',
    icon: '🧬',
    accept: '.vcf,.txt',
  },
  {
    key: 'apple_health',
    titleKey: 'upload.appleHealth',
    descKey: 'upload.appleDesc',
    formatKey: 'upload.appleFormat',
    icon: '🍎',
    accept: '.xml',
  },
  {
    key: 'google_fit',
    titleKey: 'upload.googleFit',
    descKey: 'upload.googleDesc',
    formatKey: 'upload.googleFormat',
    icon: '🤖',
    accept: '.json',
  },
];

export default function Upload() {
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [pgxProfile, setPgxProfile] = useState(null);
  const fileInputRef = useRef(null);

  async function handleUpload(file, type) {
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('source_type', type);

      let resp;
      if (type === 'apple_health') {
        resp = await fetch('/api/v1/connections/upload', {
          method: 'POST',
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
          body: formData,
        });
      } else {
        resp = await api.genomeUpload(formData);
      }

      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || t('upload.uploadFailed'));
      setResult({ type, data });
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function fetchPgx() {
    try {
      const resp = await api.genomePgx();
      const data = await resp.json();
      if (data?.success) setPgxProfile(data.data);
    } catch {
      // non-fatal
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">{t('upload.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">{t('upload.subtitle')}</p>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {UPLOAD_TYPES.map((item) => (
          <div
            key={item.key}
            className="bg-white rounded-2xl shadow-sm p-5 border border-slate-100 hover:border-emerald-200 transition-colors"
          >
            <div className="text-3xl mb-3">{item.icon}</div>
            <h3 className="font-semibold text-slate-800 mb-2">{t(item.titleKey)}</h3>
            <p className="text-sm text-slate-500 mb-2">{t(item.descKey)}</p>
            <p className="text-xs text-slate-400 mb-4">{t(item.formatKey)}</p>
            <input
              type="file"
              accept={item.accept}
              className="hidden"
              ref={(el) => {
                if (el) {
                  el.onchange = (e) => {
                    const file = e.target.files[0];
                    if (file) handleUpload(file, item.key);
                  };
                }
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="w-full bg-slate-100 text-slate-700 py-2 rounded-lg text-sm font-medium hover:bg-emerald-50 hover:text-emerald-700 disabled:opacity-50 transition-colors"
            >
              {t('upload.selectFile')}
            </button>
          </div>
        ))}
      </div>

      {uploading && (
        <div className="bg-blue-50 text-blue-700 p-4 rounded-lg text-center">
          {t('upload.uploading')}
        </div>
      )}

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-lg">{error}</div>
      )}

      {result && (
        <div className="bg-green-50 text-green-700 p-4 rounded-lg">
          {t('upload.uploadSuccess')}
          <pre className="mt-2 text-xs bg-white rounded p-2 overflow-auto max-h-48">
            {JSON.stringify(result.data, null, 2)}
          </pre>
        </div>
      )}

      {/* PGx Report */}
      <div className="bg-white rounded-2xl shadow-sm p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-800">{t('upload.genomeReport')}</h3>
            <p className="text-sm text-slate-500 mt-1">{t('upload.genomeReportDesc')}</p>
          </div>
          <button
            onClick={fetchPgx}
            className="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-emerald-700"
          >
            {t('upload.viewReport')}
          </button>
        </div>
        {pgxProfile && (
          <pre className="mt-4 text-xs bg-slate-50 rounded p-3 overflow-auto max-h-64">
            {JSON.stringify(pgxProfile, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
