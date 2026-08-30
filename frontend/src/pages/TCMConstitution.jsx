import { useState, useEffect } from 'react';
import { api } from '../api/client';

const NINE_TYPES = {
  pinghe:   { name: '平和质', color: 'bg-emerald-50 border-emerald-300',  dot: 'text-emerald-600', desc: '阴阳调和、体态适中、面色红润、精力充沛。是最理想体质，患病率低。' },
  qixu:     { name: '气虚质', color: 'bg-blue-50 border-blue-300',        dot: 'text-blue-600',    desc: '元气不足，易疲乏、气短、自汗，肌肉松软，抗病力弱。' },
  yangxu:   { name: '阳虚质', color: 'bg-orange-50 border-orange-300',    dot: 'text-orange-600',  desc: '阳气不足，畏寒怕冷、手足不温，喜热饮食，易腹泻。' },
  yinxu:    { name: '阴虚质', color: 'bg-red-50 border-red-300',          dot: 'text-red-600',     desc: '阴液亏少，口燥咽干、手足心热、失眠、大便干结。' },
  tanshi:   { name: '痰湿质', color: 'bg-slate-50 border-slate-300',      dot: 'text-slate-600',   desc: '痰湿凝聚，体形肥胖、腹部肥满、皮肤油脂多、易困倦。' },
  shire:    { name: '湿热质', color: 'bg-amber-50 border-amber-300',      dot: 'text-amber-600',   desc: '湿热内蕴，面垢油光、易生痤疮、口苦口干、身重困倦。' },
  xueyu:    { name: '血瘀质', color: 'bg-purple-50 border-purple-300',    dot: 'text-purple-600',  desc: '血行不畅，肤色晦暗、易出血、疼痛固定、唇色暗紫。' },
  qiyu:     { name: '气郁质', color: 'bg-indigo-50 border-indigo-300',    dot: 'text-indigo-600',  desc: '气机郁滞，神情抑郁、忧虑脆弱、胸肋胀痛、喉中异物感。' },
  tebing:   { name: '特禀质', color: 'bg-pink-50 border-pink-300',        dot: 'text-pink-600',    desc: '先天失常，易过敏（药物、食物、花粉）、易患哮喘/湿疹/荨麻疹。' },
};

const QUESTIONNAIRE = [
  { q: '您平时容易感到疲乏或精力不足吗？', key: 'fatigue' },
  { q: '您容易怕冷，手脚冰凉吗？', key: 'cold' },
  { q: '您容易出汗（不是天气热）吗？', key: 'sweat' },
  { q: '您的睡眠质量如何？', key: 'sleep' },
  { q: '您容易感到焦虑或情绪低落吗？', key: 'mood' },
  { q: '您容易感冒或感染吗？', key: 'infection' },
  { q: '您的食欲和消化如何？', key: 'digest' },
  { q: '您容易口渴或上火吗？', key: 'heat' },
  { q: '您皮肤容易过敏或长疹子吗？', key: 'allergy' },
  { q: '您体型偏胖还是偏瘦？', key: 'body', options: ['偏瘦', '适中', '偏胖'] },
];

export default function TCMConstitution() {
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));

  const scoreMap = { '很少': 0, '偶尔': 1, '经常': 2, '总是': 3, '很好': 3, '一般': 2, '较差': 1, '很差': 0 };

  useEffect(() => {
    loadExisting();
  }, []);

  async function loadExisting() {
    if (!token) return;
    try {
      const resp = await api.tcmConstitution();
      if (resp.ok) {
        const data = await resp.json();
        if (data?.data) {
          setResult(data.data);
        }
      }
    } catch {
      // no existing profile
    }
  }

  async function handleAnalyze() {
    setLoading(true);
    setError(null);
    const questionnaire = {};
    for (const [k, v] of Object.entries(answers)) {
      questionnaire[k] = typeof v === 'string' ? v : scoreMap[v] ?? 0;
    }

    try {
      const resp = await api.tcmConstitutionPost({ questionnaire_data: questionnaire });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.message || '分析失败');
      if (data?.data) setResult(data.data);
      else setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const hasAllAnswers = Object.keys(answers).length >= 6;
  const mainType = result?.constitution_type;
  const typeInfo = mainType ? NINE_TYPES[mainType] : null;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">🏥 中医体质辨识</h2>
        <p className="text-slate-500 text-sm mt-1">
          基于《中医体质分类与判定》标准，从 9 种体质中辨识您的主型体质
        </p>
      </div>

      <form className="space-y-4 bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800">请根据您的实际情况选择</h3>
        {QUESTIONNAIRE.map((item, i) => (
          <div key={i} className="space-y-1.5">
            <p className="text-sm font-medium text-slate-700">{item.q}</p>
            <div className="flex gap-2">
              {(item.options || ['很少', '偶尔', '经常', '总是']).map(opt => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setAnswers(p => ({ ...p, [item.key]: opt }))}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition
                    ${answers[item.key] === opt
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>
        ))}
        <button
          type="button"
          onClick={handleAnalyze}
          disabled={loading || !hasAllAnswers}
          className="bg-emerald-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
        >
          {loading ? '辨识中…' : `辨识体质 (${Object.keys(answers).length}/${QUESTIONNAIRE.length})`}
        </button>
      </form>

      {error && <div className="bg-red-50 text-red-600 p-4 rounded-lg text-sm">{error}</div>}

      {typeInfo && (
        <div className={`${typeInfo.color} border-2 rounded-2xl p-6 space-y-4`}>
          <div className="flex items-center gap-3">
            <span className={`text-3xl ${typeInfo.dot}`}>●</span>
            <div>
              <h3 className="text-2xl font-bold text-slate-800">{typeInfo.name}</h3>
              <p className="text-sm text-slate-600 mt-1">{typeInfo.desc}</p>
            </div>
          </div>

          {result?.constitution_score && (
            <div className="bg-white/80 rounded-xl p-4">
              <h4 className="font-medium text-sm text-slate-700 mb-3">九型体质评分</h4>
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(result.constitution_score).map(([key, score]) => {
                  const info = NINE_TYPES[key];
                  if (!info) return null;
                  const pct = Math.min(100, (typeof score === 'number' ? score : 0) * 100);
                  const isMain = key === mainType;
                  return (
                    <div key={key} className={`text-center p-2 rounded-lg ${isMain ? 'bg-white shadow-sm ring-2 ring-emerald-300' : 'bg-white/50'}`}>
                      <p className={`text-xs font-medium ${isMain ? typeInfo.dot : 'text-slate-500'}`}>{info.name}</p>
                      <div className="w-full bg-slate-200 rounded-full h-1.5 mt-1.5">
                        <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{pct.toFixed(0)}%</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {result?.recommendations && result.recommendations.length > 0 && (
            <div className="bg-white/80 rounded-xl p-4">
              <h4 className="font-medium text-sm text-slate-700 mb-3">调理建议</h4>
              <ul className="space-y-2">
                {result.recommendations.slice(0, 5).map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="text-emerald-600 mt-0.5 shrink-0">●</span>
                    <span>{r.prescription || r.description || r.name || `建议 ${i + 1}`}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {!typeInfo && !loading && !error && (
        <div className="text-center py-8 text-slate-400 text-sm">
          完成问卷后点击上方按钮，查看您的体质类型和个性化调理方案
        </div>
      )}
    </div>
  );
}
