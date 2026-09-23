import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

export default function Payment() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [packages, setPackages] = useState([]);
  const [balance, setBalance] = useState(0);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    Promise.all([
      api.paymentFeatures().then(r => r.json()).catch(() => null),
      api.paymentBalance().then(r => r.json()).catch(() => null),
    ]).then(([featRes, balRes]) => {
      if (featRes?.success) {
        const premium = featRes.data?.premium_features || [];
        setPackages(Array.isArray(premium) ? premium : Object.values(premium));
      }
      if (balRes?.success) {
        setBalance(balRes.data?.balance || 0);
      }
    }).finally(() => setLoading(false));
  }, []);

  async function handlePayment(packageCode) {
    setCreating(true);
    setError(null);
    try {
      const resp = await api.paymentCreate({ package_code: packageCode, currency: 'CNY' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || t('payment.paymentFailed'));
      if (data?.data?.checkout_url) {
        window.location.href = data.data.checkout_url;
      } else {
        setSuccess(t('payment.processing'));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleCreemCheckout(packageCode) {
    setCreating(true);
    setError(null);
    try {
      const resp = await api.paymentCreate({ package_code: packageCode, currency: 'USD' });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || t('payment.paymentFailed'));
      if (data?.data?.checkout_url) {
        window.location.href = data.data.checkout_url;
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <div className="text-center py-12">{t('common.loading')}</div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">{t('payment.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">{t('payment.subtitle')}</p>
      </div>

      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg">{error}</div>}
      {success && <div className="bg-green-50 text-green-700 p-4 rounded-lg">{success}</div>}

      <div className="grid md:grid-cols-3 gap-4">
        {/* Free Plan */}
        <div className="bg-white rounded-2xl shadow-sm p-6 border-2 border-slate-100">
          <div className="text-sm text-slate-500 mb-1">{t('payment.freePlan')}</div>
          <div className="text-3xl font-bold mb-4">¥0</div>
          <ul className="space-y-2 text-sm text-slate-600">
            <li>✓ {t('payment.featureAxes')}</li>
            <li>✓ {t('payment.featureReports')}</li>
            <li className="text-slate-400">— {t('payment.featureGenome')}</li>
            <li className="text-slate-400">— {t('payment.featureShare')}</li>
            <li className="text-slate-400">— {t('payment.featurePriority')}</li>
          </ul>
          <div className="mt-6 text-xs text-slate-400">{t('payment.currentPlan')}</div>
        </div>

        {/* Pro Plan */}
        <div className="bg-gradient-to-br from-emerald-50 to-teal-50 rounded-2xl shadow-sm p-6 border-2 border-emerald-200 relative">
          <div className="absolute -top-3 right-4 bg-emerald-500 text-white text-xs px-3 py-1 rounded-full">
            {t('payment.recommended')}
          </div>
          <div className="text-sm text-emerald-600 mb-1">{t('payment.proPlan')}</div>
          <div className="text-3xl font-bold mb-1">¥39.9<span className="text-sm font-normal text-slate-500">/月</span></div>
          <div className="text-xs text-slate-500 mb-4 line-through">¥79.9/月</div>
          <ul className="space-y-2 text-sm text-slate-700">
            <li>✓ {t('payment.featureAxes')}</li>
            <li>✓ {t('payment.featureGenome')}</li>
            <li>✓ {t('payment.featureReports')}</li>
            <li>✓ {t('payment.featureShare')}</li>
            <li>✓ {t('payment.featurePriority')}</li>
          </ul>
          <button
            onClick={() => handlePayment('basic')}
            disabled={creating}
            className="w-full mt-6 bg-emerald-600 text-white py-3 rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {creating ? t('payment.processing') : t('payment.payBtn')}
          </button>
          <button
            onClick={() => handleCreemCheckout('basic')}
            disabled={creating}
            className="w-full mt-2 bg-white text-emerald-600 border border-emerald-200 py-2 rounded-xl text-sm font-medium hover:bg-emerald-50 disabled:opacity-50 transition-colors"
          >
            {t('payment.payWithCreem')}
          </button>
        </div>

        {/* Lifetime Plan */}
        <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl shadow-sm p-6 border-2 border-amber-200 md:col-span-3">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <div className="text-sm text-amber-600 mb-1">{t('payment.lifetimePlan')}</div>
              <div className="text-3xl font-bold">¥199<span className="text-sm font-normal text-slate-500"> {t('payment.oneTime')}</span></div>
              <div className="text-xs text-slate-500 mt-1">{t('payment.saveCalc', { saved: '¥279' })}</div>
            </div>
            <button
              onClick={() => handlePayment('ultimate')}
              disabled={creating}
              className="bg-amber-500 text-white px-8 py-3 rounded-xl font-semibold hover:bg-amber-600 disabled:opacity-50 transition-colors"
            >
              {creating ? t('payment.processing') : t('payment.payBtn')}
            </button>
          </div>
        </div>
      </div>

      {/* Features list */}
      {packages.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-4">{t('payment.features')}</h3>
          <div className="grid md:grid-cols-2 gap-3">
            {packages.map((f, i) => (
              <div key={i} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                <span className="text-emerald-500">✓</span>
                <span className="text-sm text-slate-700">{f.name || f}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Points balance */}
      <div className="bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 mb-2">{t('payment.currentBalance')}</h3>
        <div className="text-2xl font-bold text-emerald-600">{balance}</div>
        <p className="text-sm text-slate-500 mt-1">{t('payment.pointsBalance', { balance })}</p>
      </div>
    </div>
  );
}
