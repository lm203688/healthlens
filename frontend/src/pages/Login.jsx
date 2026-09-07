/** 验证码登录 —— 登录与注册是同一件事
 *
 * 一个入口：输入手机号（国内）或邮箱（其他地区）→ 获取验证码 → 输入验证码 → 进入应用。
 * 账号不存在时后端自动创建，用户不需要先"注册"再"登录"，也不需要设置密码。
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

const PHONE_RE = /^1[3-9]\d{9}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** 判断输入是手机号还是邮箱，返回 'phone' | 'email' | null */
function detectKind(value) {
  const v = (value || '').trim();
  if (!v) return null;
  if (v.includes('@')) return EMAIL_RE.test(v) ? 'email' : null;
  return PHONE_RE.test(v) ? 'phone' : null;
}

function maskAccount(value, kind) {
  if (kind === 'phone') return `${value.slice(0, 3)}****${value.slice(-4)}`;
  const [name, domain] = value.split('@');
  const head = name.length <= 2 ? name[0] : `${name.slice(0, 2)}***`;
  return `${head}@${domain}`;
}

/** 后端 4xx 的 detail 可能是字符串，也可能是 { message, retry_after } */
async function readError(resp) {
  let payload = {};
  try {
    payload = await resp.json();
  } catch {
    return '网络异常，请稍后重试';
  }
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return payload?.message || '请求失败，请稍后重试';
}

export default function Login() {
  const [account, setAccount] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);   // 是否已发出验证码
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const codeRef = useRef(null);
  const navigate = useNavigate();

  const kind = detectKind(account);

  // 重发倒计时
  useEffect(() => {
    if (countdown <= 0) return undefined;
    const timer = setTimeout(() => setCountdown((n) => n - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  // 进入验证码输入态后自动聚焦
  useEffect(() => {
    if (sent) codeRef.current?.focus();
  }, [sent]);

  async function handleSendCode() {
    setError(null);
    setNotice(null);
    if (!kind) {
      setError(account.includes('@') ? '邮箱格式不正确' : '请输入正确的手机号或邮箱');
      return;
    }
    setSending(true);
    try {
      const resp = await api.otpSend({ account: account.trim() });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(await readError(resp));

      const payload = data.data || {};
      setSent(true);
      setCountdown(60);
      setCode('');

      // 后端开启 OTP_DEV_ECHO 时直接回填，方便无短信服务商时自测
      if (payload.dev_code) {
        setCode(String(payload.dev_code));
        setNotice(
          payload.channel === 'email'
            ? `验证码已发往 ${maskAccount(account.trim(), kind)}（当前为自测模式，已自动填入）`
            : `验证码已发往 ${maskAccount(account.trim(), kind)}（当前为自测模式，已自动填入）`
        );
      } else {
        setNotice(
          payload.channel === 'email'
            ? `验证码已发送至邮箱 ${maskAccount(account.trim(), kind)}，5 分钟内有效`
            : `验证码已短信发送至 ${maskAccount(account.trim(), kind)}，5 分钟内有效`
        );
      }
    } catch (err) {
      setError(err.message || '验证码发送失败');
    } finally {
      setSending(false);
    }
  }

  async function handleVerify(e) {
    e.preventDefault();
    setError(null);
    if (code.trim().length < 4) {
      setError('请输入收到的验证码');
      return;
    }
    setVerifying(true);
    try {
      const resp = await api.otpVerify({ account: account.trim(), code: code.trim() });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(await readError(resp));

      const { access_token, refresh_token, user } = data.data || {};
      localStorage.setItem('token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('user_email', user?.email || account.trim());
      setNotice('验证成功，正在进入…');
      setTimeout(() => navigate('/'), 600);
    } catch (err) {
      setError(err.message || '验证失败');
    } finally {
      setVerifying(false);
    }
  }

  function resetAccount() {
    setSent(false);
    setCode('');
    setCountdown(0);
    setNotice(null);
    setError(null);
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-50 via-white to-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-emerald-600 text-white text-2xl shadow-sm mb-4">
            🔬
          </div>
          <h1 className="text-3xl font-bold text-slate-800">
            Health<span className="text-emerald-600">Lens</span>
          </h1>
          <p className="text-slate-500 mt-2 text-sm">融合引擎 · 中医古籍 · 智能体</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-8">
          <h2 className="text-lg font-semibold text-slate-800 mb-1">
            {sent ? '输入验证码' : '验证码登录'}
          </h2>
          <p className="text-sm text-slate-500 mb-6">
            无需注册，验证后即自动创建账号
          </p>

          <form onSubmit={sent ? handleVerify : (e) => { e.preventDefault(); handleSendCode(); }} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                手机号 / 邮箱
              </label>
              <div className="relative">
                <input
                  type={kind === 'email' ? 'email' : 'tel'}
                  value={account}
                  onChange={(e) => { setAccount(e.target.value); setError(null); }}
                  onKeyDown={(e) => { if (e.key === 'Enter' && sent) handleVerify(e); }}
                  placeholder="国内请输入手机号，其他地区请输入邮箱"
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent pr-20"
                  disabled={sent}
                  autoComplete="username"
                  required
                />
                {sent && (
                  <button
                    type="button"
                    onClick={resetAccount}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-emerald-600 hover:text-emerald-700 px-2 py-1"
                  >
                    更换
                  </button>
                )}
              </div>
              {account && !kind && (
                <p className="mt-1 text-xs text-amber-600">
                  请输入 11 位手机号或正确的邮箱地址
                </p>
              )}
            </div>

            {sent && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">验证码</label>
                <div className="flex gap-2">
                  <input
                    ref={codeRef}
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="6 位数字"
                    className="flex-1 px-4 py-2.5 border border-slate-200 rounded-lg text-sm tracking-widest focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                    autoComplete="one-time-code"
                    required
                  />
                  <button
                    type="button"
                    onClick={handleSendCode}
                    disabled={countdown > 0 || sending}
                    className="px-4 py-2.5 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed whitespace-nowrap"
                  >
                    {countdown > 0 ? `${countdown}s` : sending ? '发送中…' : '重新发送'}
                  </button>
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>
            )}
            {notice && !error && (
              <div className="bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{notice}</div>
            )}

            <button
              type="submit"
              disabled={
                !kind ||
                (sent ? verifying || code.trim().length < 4 : sending)
              }
              className="w-full py-2.5 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition"
            >
              {sent
                ? verifying ? '验证中…' : '进入应用'
                : sending ? '发送中…' : '获取验证码'}
            </button>
          </form>

          <p className="text-center text-xs text-slate-400 mt-4">
            首次验证将自动创建账号，无需设置密码
          </p>
        </div>

        <p className="text-center text-xs text-slate-400 mt-6">
          使用前请阅读《用户协议》与《隐私政策》
        </p>
      </div>
    </div>
  );
}
