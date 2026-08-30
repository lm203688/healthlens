/** 登录 / 注册 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

export default function Login() {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const navigate = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const body = mode === 'login' ? { email, password } : { email, password, phone };
      const resp = await api[mode](body);
      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.detail || data.message || '请求失败');
      }

      const { access_token, refresh_token, user } = data.data;
      localStorage.setItem('token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('user_email', user.email);
      setSuccess(mode === 'login' ? '登录成功，正在跳转…' : '注册成功，正在跳转…');
      setTimeout(() => navigate('/'), 800);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-50 via-white to-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-emerald-700">Health<span className="text-slate-800">Lens</span></h1>
          <p className="text-slate-500 mt-2">融合引擎 · 中医古籍 · 智能体</p>
        </div>

        <div className="bg-white rounded-2xl shadow-lg p-8">
          <div className="flex gap-2 mb-6 bg-slate-100 p-1 rounded-xl">
            <button
              onClick={() => { setMode('login'); setError(null); setSuccess(null); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition
                ${mode === 'login' ? 'bg-white text-emerald-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            >
              登录
            </button>
            <button
              onClick={() => { setMode('register'); setError(null); setSuccess(null); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition
                ${mode === 'register' ? 'bg-white text-emerald-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            >
              注册
            </button>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">邮箱</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none"
                required
              />
            </div>

            {mode === 'register' && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">手机号（可选）</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="138xxxx0000"
                  className="w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">密码</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === 'register' ? '至少 6 位密码' : '您的密码'}
                className="w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none"
                required
                minLength={6}
              />
            </div>

            {error && <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>}
            {success && <div className="bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{success}</div>}

            <button
              type="submit"
              disabled={loading || !email.trim() || !password.trim()}
              className="w-full bg-emerald-600 text-white py-2.5 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
            >
              {loading ? '处理中…' : mode === 'login' ? '登录' : '注册'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-slate-400 mt-6">
          使用前请阅读《用户协议》与《隐私政策》
        </p>
      </div>
    </div>
  );
}
