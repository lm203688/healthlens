import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function Profile() {
  const [user, setUser] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError] = useState(null);
  const [token] = useState(localStorage.getItem('token'));

  const [form, setForm] = useState({
    name: '',
    age: '',
    gender: '',
    height: '',
    weight: '',
    occupation: '',
    allergies: '',
    chronic_conditions: '',
    medications: '',
    notes: '',
  });

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.me().then(r => r.json()),
      api.profiles().then(r => r.json()).catch(() => null),
    ]).then(([userRes, profileRes]) => {
      const userData = userRes?.data || userRes;
      setUser(userData);

      if (profileRes?.data) {
        const p = profileRes.data;
        setProfile(p);
        setForm({
          name: p.name || '',
          age: p.age ?? '',
          gender: p.gender || '',
          height: p.height ?? '',
          weight: p.weight ?? '',
          occupation: p.occupation || '',
          allergies: p.allergies || '',
          chronic_conditions: p.chronic_conditions || '',
          medications: p.medications || '',
          notes: p.notes || '',
        });
      }
    }).catch(() => setError('获取用户信息失败')).finally(() => setLoading(false));
  }, [token]);

  async function saveProfile() {
    setSaving(true);
    setError(null);
    setSuccess(null);

    const body = {
      name: form.name,
      age: form.age ? parseInt(form.age) : null,
      gender: form.gender || null,
      height: form.height ? parseFloat(form.height) : null,
      weight: form.weight ? parseFloat(form.weight) : null,
      occupation: form.occupation || null,
      allergies: form.allergies || null,
      chronic_conditions: form.chronic_conditions || null,
      medications: form.medications || null,
      notes: form.notes || null,
    };

    try {
      const resp = await fetch('/api/v1/profiles', {
        method: profile ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.message || '保存失败');
      setSuccess('健康档案已保存');
      setProfile(data.data || data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-center py-16 text-slate-400">加载中…</div>;
  if (!user) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-600">请先<a href="/login" className="text-emerald-600 font-medium">登录</a>后查看个人档案</p>
      </div>
    );
  }

  const { name: userName, age, gender, height, weight } = profile || {};
  const bmi = height && weight ? (weight / ((height / 100) ** 2)).toFixed(1) : null;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">👤 个人健康档案</h2>
        <p className="text-slate-500 text-sm mt-1">完善您的基本信息，让 AI 评估更精准</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6">
        <div className="flex items-center gap-4 pb-4 border-b border-slate-100 mb-4">
          <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center text-xl font-bold text-emerald-700">
            {(user.name || user.email || 'U')[0]}
          </div>
          <div>
            <p className="font-semibold text-slate-800">{user.name || user.email}</p>
            <p className="text-sm text-slate-500">{user.email}</p>
            {user.phone && <p className="text-xs text-slate-400">{user.phone}</p>}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            type="text"
            placeholder="姓名"
            value={form.name}
            onChange={(e) => setForm(p => ({ ...p, name: e.target.value }))}
            className="px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
          />
          <div className="flex gap-2">
            <select
              value={form.gender}
              onChange={(e) => setForm(p => ({ ...p, gender: e.target.value }))}
              className="flex-1 px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            >
              <option value="">性别</option>
              <option value="male">男</option>
              <option value="female">女</option>
              <option value="other">其他</option>
            </select>
            <input
              type="number"
              placeholder="年龄"
              value={form.age}
              onChange={(e) => setForm(p => ({ ...p, age: e.target.value }))}
              className="w-24 px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            />
          </div>
          <input
            type="number"
            placeholder="身高 (cm)"
            value={form.height}
            onChange={(e) => setForm(p => ({ ...p, height: e.target.value }))}
            className="px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
          />
          <input
            type="number"
            placeholder="体重 (kg)"
            value={form.weight}
            onChange={(e) => setForm(p => ({ ...p, weight: e.target.value }))}
            className="px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
          />
          {bmi && (
            <div className="flex items-center gap-2 px-4 py-2 bg-slate-50 rounded-lg">
              <span className="text-sm text-slate-500">BMI</span>
              <span className={`font-bold ${parseFloat(bmi) >= 28 ? 'text-red-600' : parseFloat(bmi) >= 24 ? 'text-amber-600' : 'text-emerald-600'}`}>
                {bmi}
              </span>
            </div>
          )}
          <input
            type="text"
            placeholder="职业"
            value={form.occupation}
            onChange={(e) => setForm(p => ({ ...p, occupation: e.target.value }))}
            className="px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none md:col-span-2"
          />
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 mb-4">健康状况</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">过敏史</label>
            <input
              type="text"
              placeholder="如：青霉素、花生等（无则留空）"
              value={form.allergies}
              onChange={(e) => setForm(p => ({ ...p, allergies: e.target.value }))}
              className="w-full px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">慢性疾病</label>
            <input
              type="text"
              placeholder="如：高血压、糖尿病等（无则留空）"
              value={form.chronic_conditions}
              onChange={(e) => setForm(p => ({ ...p, chronic_conditions: e.target.value }))}
              className="w-full px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">正在服用的药物</label>
            <textarea
              rows={2}
              placeholder="如：阿司匹林、降压药等（无则留空）"
              value={form.medications}
              onChange={(e) => setForm(p => ({ ...p, medications: e.target.value }))}
              className="w-full px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">其他备注</label>
            <textarea
              rows={2}
              placeholder="其他您想告诉我们的健康信息…"
              value={form.notes}
              onChange={(e) => setForm(p => ({ ...p, notes: e.target.value }))}
              className="w-full px-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-emerald-400 outline-none"
            />
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <button
          onClick={saveProfile}
          disabled={saving}
          className="flex-1 bg-emerald-600 text-white py-3 rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition"
        >
          {saving ? '保存中…' : '💾 保存档案'}
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-600 p-4 rounded-lg text-sm">{error}</div>}
      {success && <div className="bg-emerald-50 text-emerald-700 p-4 rounded-lg text-sm">{success}</div>}
    </div>
  );
}
