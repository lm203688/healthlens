import { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

export default function TotpManager() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);
  const [enrolling, setEnrolling] = useState(false);
  const [uri, setUri] = useState('');
  const [secret, setSecret] = useState('');
  const [account, setAccount] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.totpStatus()
      .then((r) => r.json())
      .then((d) => { if (d?.success) { setEnabled(d.data.enabled); setAccount(d.data.account || ''); } })
      .catch(() => {});
  }, []);

  async function startEnroll() {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const resp = await api.totpEnroll();
      const d = await resp.json();
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || t('totp.bindFailed'));
      setUri(d.data.provisioning_uri);
      setSecret(d.data.secret);
      setAccount(d.data.account || '');
      setEnrolling(true);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmEnroll() {
    if (code.trim().length !== 6) { setErr(t('totp.codeRequired')); return; }
    setBusy(true); setErr(null);
    try {
      const resp = await api.totpConfirm({ code: code.trim() });
      const d = await resp.json();
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || t('totp.verifyFailed'));
      setEnabled(true); setEnrolling(false);
      setUri(''); setSecret(''); setCode('');
      setMsg(t('totp.enabled'));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true); setErr(null);
    try {
      const resp = await api.totpDisable();
      const d = await resp.json();
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || t('totp.opFailed'));
      setEnabled(false); setMsg(t('totp.disabled'));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function setPreferred() {
    setBusy(true); setErr(null);
    try {
      const resp = await api.totpMethod({ method: 'totp' });
      const d = await resp.json();
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || t('totp.opFailed'));
      setMsg(t('totp.preferredSet'));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <h3 className="font-semibold text-slate-800 mb-1">{t('totp.title')}</h3>
      <p className="text-xs text-slate-500 mb-4">{t('totp.subtitle')}</p>

      {!enrolling && !enabled && (
        <button
          onClick={startEnroll}
          disabled={busy}
          className="px-4 py-2.5 bg-emerald-600 text-white text-sm rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
        >
          {busy ? t('totp.processing') : t('totp.btnEnroll')}
        </button>
      )}

      {enrolling && (
        <div className="space-y-3">
          <div className="bg-slate-50 rounded-lg p-4 flex flex-col items-center gap-3">
            <p className="text-sm text-slate-600 text-center">{t('totp.scanHint')}</p>
            {uri && (
              <div className="bg-white p-3 rounded-lg shadow-sm border border-slate-100">
                <QRCodeSVG
                  value={uri}
                  size={180}
                  level="M"
                  marginSize={2}
                  fgColor="#0f172a"
                  bgColor="#ffffff"
                />
              </div>
            )}
            <div className="w-full text-center">
              <p className="text-xs text-slate-400">
                {t('totp.secretLabel')}
                <span className="font-mono text-slate-700 text-sm tracking-wide">{secret}</span>
              </p>
              {account && <p className="text-xs text-slate-400 mt-1">{t('totp.accountLabel')}{account}</p>}
              <a href={uri} className="block text-xs text-emerald-700 underline break-all mt-1">
                {t('totp.otpauthLink')}
              </a>
            </div>
          </div>
          <div className="flex gap-2">
            <input
              value={code}
              onChange={(e) => { setCode(e.target.value.replace(/\D/g, '')); setErr(null); }}
              maxLength={6}
              inputMode="numeric"
              placeholder={t('totp.codePlaceholder')}
              className="flex-1 px-4 py-2 border rounded-lg text-sm tracking-widest focus:ring-2 focus:ring-emerald-500 outline-none"
            />
            <button
              onClick={confirmEnroll}
              disabled={busy || code.length !== 6}
              className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
            >
              {busy ? t('totp.verifying') : t('totp.btnConfirm')}
            </button>
          </div>
          <button
            onClick={() => { setEnrolling(false); setUri(''); setSecret(''); setCode(''); }}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            {t('totp.cancel')}
          </button>
        </div>
      )}

      {enabled && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-emerald-700">
            <span className="w-2 h-2 rounded-full bg-emerald-500" /> {t('totp.enabledStatus')}
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={disable}
              disabled={busy}
              className="px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition"
            >
              {t('totp.btnDisable')}
            </button>
            <button
              onClick={setPreferred}
              disabled={busy}
              className="px-4 py-2 text-sm rounded-lg border border-emerald-300 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-50 transition"
            >
              {t('totp.btnSetPreferred')}
            </button>
          </div>
        </div>
      )}

      {err && <div className="mt-3 bg-red-50 text-red-600 text-sm p-3 rounded-lg">{err}</div>}
      {msg && <div className="mt-3 bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{msg}</div>}
    </div>
  );
}