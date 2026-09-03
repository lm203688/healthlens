/** 统一登录 / 注册 —— 用户可自由选择「邮箱」或「手机号」登录，首次使用自动创建账号 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

export default function Login() {
  const [method, setMethod] = useState('phone'); // 'phone' | 'email' — 国内默认手机号，其他地区切邮箱
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const navigate = useNavigate();

  function buildBodies() {
    if (method === 'email') {
      const email = identifier.trim();
      return {
        login: { account: email, password },
        register: { email, password },
      };
    }
    const phone = identifier.trim();
    return {
      login: { account: phone, password },
      // 手机号注册时以 phone@healthlens.cc 作为内部占位邮箱，保证唯一性
      register: { email: `${phone}@healthlens.cc`, phone, password },
    };
  }

  async function persist(data) {
    const { access_token, refresh_token, user } = data.data;
    localStorage.setItem('token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
    localStorage.setItem('user_email', user?.email || identifier);
  }

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    const bodies = buildBodies();
    try {
      let resp = await api.login(bodies.login);
      if (resp.status === 401) {
        // 账号不存在 -> 自动注册；若返回 409 说明是密码错误
        const reg = await api.register(bodies.register);
        if (reg.status === 409) {
          throw new Error('账号或密码错误');
        }
        if (!reg.ok) {
          const d = await reg.json().catch(() => ({}));
          throw new Error(d.detail || '注册失败，请稍后重试');
        }
        resp = await api.login(bodies.login);
      }
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.message || '登录失败');
      }
      await persist(data);
      setSuccess('登录成功，正在跳转…');
      setTimeout(() => navigate('/'), 800);
    } catch (err) {
      setError(err.message || '请求失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 via-white to-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand-600 text-white text-2xl shadow-soft mb-4">
            🔬
          </div>
          <h1 className="text-3xl font-bold text-slate-800">
            Health<span className="text-brand-600">Lens</span>
          </h1>
          <p className="text-slate-500 mt-2 text-sm">融合引擎 · 中医古籍 · 智能体</p>
        </div>

        <div className="card p-8">
          <div className="flex gap-1 mb-6 bg-slate-100 p-1 rounded-xl">
            {[
              { key: 'email', label: '邮箱登录' },
              { key: 'phone', label: '手机号登录' },
            ].map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => { setMethod(m.key); setError(null); setSuccess(null); }}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${
                  method === m.key ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {method === 'email' ? '邮箱地址' : '手机号'}
              </label>
              <input
                type={method === 'email' ? 'email' : 'tel'}
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder={method === 'email' ? 'you@example.com' : '138 0000 0000'}
                className="input-base"
                required
                autoComplete="username"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">密码</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 8 位，含字母和数字"
                className="input-base"
                required
                minLength={8}
                autoComplete="current-password"
              />
            </div>

            {error && <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>}
            {success && <div className="bg-brand-50 text-brand-700 text-sm p-3 rounded-lg">{success}</div>}

            <button
              type="submit"
              disabled={loading || !identifier.trim() || !password.trim()}
              className="btn-primary w-full"
            >
              {loading ? '处理中…' : '登录 / 注册'}
            </button>

            <p className="text-center text-xs text-slate-400 mt-1">
              首次使用将自动创建账号
            </p>
          </form>
        </div>

        <p className="text-center text-xs text-slate-400 mt-6">
          使用前请阅读《用户协议》与《隐私政策》
        </p>
      </div>
    </div>
  );
}
