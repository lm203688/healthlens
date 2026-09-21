import { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { api } from '../api/client';

/** 验证器 App 绑定管理（需已登录）。
 * 流程：enroll 生成 provisioning_uri + 密钥 → 用户在 App 中添加 → 输入动态码 confirm 启用。
 * 启用后可切换为首选登录方式或禁用。 */
export default function TotpManager() {
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
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || '绑定失败');
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
    if (code.trim().length !== 6) { setErr('请输入验证器 App 显示的 6 位动态码'); return; }
    setBusy(true); setErr(null);
    try {
      const resp = await api.totpConfirm({ code: code.trim() });
      const d = await resp.json();
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || '验证失败');
      setEnabled(true); setEnrolling(false);
      setUri(''); setSecret(''); setCode('');
      setMsg('验证器已启用，下次可用动态码登录');
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
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || '操作失败');
      setEnabled(false); setMsg('验证器已禁用');
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
      if (!resp.ok) throw new Error(d?.detail?.message || d?.message || '操作失败');
      setMsg('已设为验证器优先登录方式');
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <h3 className="font-semibold text-slate-800 mb-1">验证器 App 绑定</h3>
      <p className="text-xs text-slate-500 mb-4">
        绑定后可用 Google Authenticator / FreeOTP 等生成的动态码登录，无需短信验证码。
      </p>

      {!enrolling && !enabled && (
        <button
          onClick={startEnroll}
          disabled={busy}
          className="px-4 py-2.5 bg-emerald-600 text-white text-sm rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
        >
          {busy ? '处理中…' : '＋ 绑定验证器 App'}
        </button>
      )}

      {enrolling && (
        <div className="space-y-3">
          <div className="bg-slate-50 rounded-lg p-4 flex flex-col items-center gap-3">
            <p className="text-sm text-slate-600 text-center">
              用 Google Authenticator / FreeOTP 扫描下方二维码，或手动输入密钥：
            </p>
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
                密钥（手动输入用）：
                <span className="font-mono text-slate-700 text-sm tracking-wide">{secret}</span>
              </p>
              {account && <p className="text-xs text-slate-400 mt-1">账号：{account}</p>}
              <a href={uri} className="block text-xs text-emerald-700 underline break-all mt-1">
                otpauth 链接（备用）
              </a>
            </div>
          </div>
          <div className="flex gap-2">
            <input
              value={code}
              onChange={(e) => { setCode(e.target.value.replace(/\D/g, '')); setErr(null); }}
              maxLength={6}
              inputMode="numeric"
              placeholder="输入 App 显示的 6 位码"
              className="flex-1 px-4 py-2 border rounded-lg text-sm tracking-widest focus:ring-2 focus:ring-emerald-500 outline-none"
            />
            <button
              onClick={confirmEnroll}
              disabled={busy || code.length !== 6}
              className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
            >
              {busy ? '验证中…' : '确认启用'}
            </button>
          </div>
          <button
            onClick={() => { setEnrolling(false); setUri(''); setSecret(''); setCode(''); }}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            取消
          </button>
        </div>
      )}

      {enabled && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-emerald-700">
            <span className="w-2 h-2 rounded-full bg-emerald-500" /> 已启用验证器 App
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={disable}
              disabled={busy}
              className="px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition"
            >
              禁用
            </button>
            <button
              onClick={setPreferred}
              disabled={busy}
              className="px-4 py-2 text-sm rounded-lg border border-emerald-300 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-50 transition"
            >
              设为首选登录方式
            </button>
          </div>
        </div>
      )}

      {err && <div className="mt-3 bg-red-50 text-red-600 text-sm p-3 rounded-lg">{err}</div>}
      {msg && <div className="mt-3 bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{msg}</div>}
    </div>
  );
}
