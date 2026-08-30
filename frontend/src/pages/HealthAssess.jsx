import { useState } from 'react';
import { api } from '../api/client';

const SYMPTOM_CATEGORIES = [
  {
    title: '🌙 睡眠与精力',
    items: ['失眠多梦', '早醒', '入睡困难', '白天疲劳', '精力不足', '嗜睡'],
  },
  {
    title: '🧊 寒热与体温',
    items: ['怕冷', '手脚冰凉', '上火', '口舌生疮', '口干舌燥', '手足心热'],
  },
  {
    title: '🍵 消化与饮食',
    items: ['食欲不振', '腹胀', '腹泻', '便秘', '反酸', '消化不良'],
  },
  {
    title: '🧠 情绪与心理',
    items: ['焦虑', '情绪低落', '烦躁易怒', '注意力不集中', '压力大', '失眠焦虑'],
  },
  {
    title: '💊 慢性症状',
    items: ['慢性咳嗽', '颈肩疼痛', '头痛', '关节痛', '慢性炎症', '免疫力低'],
  },
  {
    title: '🩸 代谢与体重',
    items: ['体重超标', '血脂异常', '血糖偏高', '血压偏高', '尿酸高', '水肿'],
  },
];

const LIFESTYLE_TAGS = [
  { label: '久坐办公', icon: '💺' },
  { label: '熬夜', icon: '🌙' },
  { label: '缺乏运动', icon: '🛋️' },
  { label: '饮食不规律', icon: '🍕' },
  { label: '吸烟', icon: '🚬' },
  { label: '饮酒', icon: '🍺' },
  { label: '长期用药', icon: '💊' },
  { label: '家族病史', icon: '🧬' },
];

export default function HealthAssess() {
  const [step, setStep] = useState(1);
  const [symptoms, setSymptoms] = useState([]);
  const [lifestyle, setLifestyle] = useState([]);
  const [freeText, setFreeText] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function toggleSymptom(item) {
    setSymptoms(p => p.includes(item) ? p.filter(s => s !== item) : [...p, item]);
  }

  function toggleLifestyle(item) {
    setLifestyle(p => p.includes(item) ? p.filter(s => s !== item) : [...p, item]);
  }

  async function submit() {
    if (symptoms.length === 0 && lifestyle.length === 0 && !freeText.trim()) {
      setError('请至少选择一项症状/习惯或描述您的情况');
      return;
    }

    setLoading(true);
    setError(null);
    const parts = [];
    if (freeText.trim()) parts.push(freeText.trim());
    if (symptoms.length) parts.push('症状：' + symptoms.join('、'));
    if (lifestyle.length) parts.push('生活习惯：' + lifestyle.join('、'));

    try {
      const resp = await api.agentFusion({ user_input: parts.join(' | ') });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.message || '分析失败');
      setResult(data);
      setStep(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (step === 1) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h2 className="text-2xl font-bold">🩺 详细健康评估</h2>
          <p className="text-slate-500 text-sm mt-1">选择您的症状和生活习惯，AI 融合引擎将从 8 个维度深度分析</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-4">选择您的主要症状</h3>
          <div className="space-y-4">
            {SYMPTOM_CATEGORIES.map((cat, ci) => (
              <div key={ci} className="space-y-2">
                <p className="text-sm font-medium text-slate-700">{cat.title}</p>
                <div className="flex flex-wrap gap-2">
                  {cat.items.map(item => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => toggleSymptom(item)}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition
                        ${symptoms.includes(item)
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-4">您的生活习惯</h3>
          <div className="flex flex-wrap gap-2 mb-4">
            {LIFESTYLE_TAGS.map(tag => (
              <button
                key={tag.label}
                type="button"
                onClick={() => toggleLifestyle(tag.label)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition flex items-center gap-1.5
                  ${lifestyle.includes(tag.label)
                    ? 'bg-amber-100 text-amber-800 border border-amber-300'
                    : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
              >
                <span>{tag.icon}</span> {tag.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-400">生活习惯信息有助于更精准的风险评估，请放心填写</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-3">补充描述（可选）</h3>
          <textarea
            rows={3}
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            placeholder="例如：最近工作压力大，晚上12点以后才能睡，早上起来总觉得累..."
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none text-sm"
          />
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => setStep(2)}
            disabled={symptoms.length === 0 && lifestyle.length === 0 && !freeText.trim()}
            className="flex-1 bg-emerald-600 text-white py-3 rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            开始评估 →
          </button>
        </div>
        {error && <p className="text-red-500 text-sm text-center">{error}</p>}
      </div>
    );
  }

  if (step === 2) {
    return (
      <div className="text-center py-16 space-y-4">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-emerald-200 border-t-emerald-600" />
        <h3 className="text-xl font-semibold text-slate-800">AI 融合引擎分析中</h3>
        <p className="text-slate-500">正在从 8 个维度评估您的健康状况</p>
        <div className="flex justify-center gap-3 mt-4">
          {['症状分析', '风险评分', '安全闸门', '融合推荐'].map(s => (
            <span key={s} className="px-3 py-1 bg-slate-100 text-slate-500 text-xs rounded-full">{s}</span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-emerald-700">评估完成</h2>
          <p className="text-slate-500 text-sm mt-1">以下是您的个性化健康分析报告</p>
        </div>
        <button
          onClick={() => { setStep(1); setResult(null); setSymptoms([]); setLifestyle([]); setFreeText(''); }}
          className="bg-slate-100 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-200 transition"
        >
          重新评估
        </button>
      </div>

      {result?.banner && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
          <p className="text-emerald-800 font-medium">{result.banner}</p>
        </div>
      )}

      {result?.weak_axes && result.weak_axes.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-3">⚠️ 重点关注维度</h3>
          <div className="flex flex-wrap gap-2">
            {result.weak_axes.map((a, i) => (
              <span key={i} className="px-3 py-1.5 bg-amber-100 text-amber-800 text-sm font-medium rounded-lg">
                {a}
              </span>
            ))}
          </div>
        </div>
      )}

      {result?.recommendations && result.recommendations.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold text-slate-800">个性化建议（{result.recommendations.length} 条）</h3>
          {result.recommendations.map((r, i) => (
            <div key={i} className={`rounded-xl p-4 shadow-sm ${r.gate_passed ? 'bg-white' : 'bg-red-50 border border-red-200'}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${r.gate_passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                  {r.gate_passed ? '✅ 通过' : '🚫 需警惕'}
                </span>
                <span className="font-medium text-slate-800">{r.name || `建议 ${i + 1}`}</span>
              </div>
              {r.prescription && <p className="text-sm text-slate-600 mt-1">{r.prescription}</p>}
              {r.monitor_markers && <p className="text-xs text-slate-400 mt-1">📊 监测指标：{r.monitor_markers}</p>}
              {r.evidence_level && <p className="text-xs text-slate-400 mt-0.5">📚 证据等级：{r.evidence_level}</p>}
            </div>
          ))}
        </div>
      )}

      {result?.evidence_chain && result.evidence_chain.length > 0 && (
        <details className="bg-white rounded-2xl shadow-sm p-6">
          <summary className="cursor-pointer font-medium text-slate-800">📚 证据链（{result.evidence_chain.length} 条）</summary>
          <ul className="mt-3 space-y-1 text-sm text-slate-600">
            {result.evidence_chain.map((c, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-xs text-slate-400 mt-0.5 shrink-0">[{c.evidence_level}]</span>
                <span>{c.name} — {c.tcm_source || c.gene_relevance || '（通用推荐）'}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
