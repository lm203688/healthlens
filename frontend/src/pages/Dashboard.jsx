import { useState, useEffect } from 'react';
import { api } from '../api/client';

const QUICK_QUESTIONS = [
  { q: '您最近容易感到疲劳吗？', options: ['否', '偶尔', '经常'] },
  { q: '您容易怕冷或手脚冰凉吗？', options: ['否', '偶尔', '经常'] },
  { q: '您的睡眠质量如何？', options: ['很好', '一般', '较差'] },
  { q: '您容易感到焦虑或情绪低落吗？', options: ['否', '偶尔', '经常'] },
  { q: '您容易感冒或感染吗？', options: ['否', '偶尔', '经常'] },
  { q: '您的消化和食欲如何？', options: ['很好', '一般', '较差'] },
];

const HEALTH_EXAMPLES = [
  { label: '最近容易疲劳、乏力', icon: '🔋' },
  { label: '失眠、睡不好', icon: '🌙' },
  { label: '怕冷、手脚冰凉', icon: '🧊' },
  { label: '情绪焦虑、压力大', icon: '🧠' },
  { label: '消化不良、腹胀', icon: '🍵' },
  { label: '上火、口舌生疮', icon: '🔥' },
];

export default function Dashboard() {
  const [phase, setPhase] = useState('quiz'); // quiz | loading | results
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [hasHistory, setHasHistory] = useState(false);
  const [historyData, setHistoryData] = useState(null);

  useEffect(() => {
    // 检查是否有历史记录
    api.dashboard().then((r) => r.json()).then((data) => {
      if (data && data.overview && data.overview.weak_axes) {
        setHasHistory(true);
        setHistoryData(data);
      }
    }).catch(() => {
      // 后端未启动，正常
    });
  }, []);

  if (hasHistory && historyData) {
    return <HistoryDashboard data={historyData} onNewQuiz={() => setPhase('quiz')} />;
  }

  if (phase === 'loading') {
    return <LoadingState />;
  }

  if (phase === 'results' && result) {
    return <ResultsView data={result} onRetry={() => setPhase('quiz')} />;
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-8">
        <h2 className="text-2xl font-bold text-slate-800">3 分钟，了解您的健康状态</h2>
        <p className="text-slate-500 mt-2">回答几个简单问题，AI 融合引擎将从 8 个维度分析您的健康</p>
      </div>

      <div className="flex items-center justify-center gap-2 mb-8">
        {['问卷', '分析', '结果'].map((step, i) => (
          <div key={step} className="flex items-center">
            <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold
              ${i === 0 ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-500'}`}>
              {i + 1}
            </div>
            <span className={`text-sm ml-2 mr-4 ${i === 0 ? 'text-emerald-700 font-medium' : 'text-slate-400'}`}>
              {step}
            </span>
            {i < 2 && <div className="w-8 h-0.5 bg-slate-200" />}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6 mb-6">
        <h3 className="font-semibold text-slate-800 mb-1">快速健康自评</h3>
        <p className="text-sm text-slate-500 mb-4">请根据最近 2 周的感受选择</p>
        <div className="space-y-4">
          {QUICK_QUESTIONS.map((item, i) => (
            <div key={i} className="space-y-2">
              <p className="text-sm font-medium text-slate-700">{item.q}</p>
              <div className="flex gap-2">
                {item.options.map(opt => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setAnswers(p => ({ ...p, [i]: opt }))}
                    className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition
                      ${answers[i] === opt
                        ? 'bg-emerald-600 text-white shadow-sm'
                        : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6 mb-6">
        <h3 className="font-semibold text-slate-800 mb-1">或者直接描述您的情况</h3>
        <p className="text-sm text-slate-500 mb-3">点击常见问题，或输入详细描述</p>
        <div className="flex flex-wrap gap-2 mb-3">
          {HEALTH_EXAMPLES.map((ex, i) => (
            <button
              key={i}
              onClick={() => setAnswers(p => ({ ...p, _free: ex.label }))}
              className="px-3 py-1.5 bg-emerald-50 text-emerald-700 text-sm rounded-lg hover:bg-emerald-100 transition border border-emerald-200"
            >
              {ex.icon} {ex.label}
            </button>
          ))}
        </div>
      </div>

      <div className="text-center">
        <button
          onClick={() => {
            if (Object.keys(answers).length < 2 && !answers._free) {
              setError('请至少回答 2 个问题或描述症状');
              return;
            }
            setError(null);
            setPhase('loading');
            const questionTexts = Object.entries(answers)
              .filter(([k]) => k !== '_free')
              .map(([i, v]) => `${QUICK_QUESTIONS[+i].q} 答:${v}`)
              .join(' | ');
            const freeText = answers._free || '';
            const input = `健康评估：${freeText}${questionTexts ? ' | ' + questionTexts : ''}`;
            api.agentFusion({ user_input: input })
              .then((r) => r.json())
              .then(setResult)
              .then(() => setPhase('results'))
              .catch((err) => { setError(err.message); setPhase('quiz'); });
          }}
          className="bg-emerald-600 text-white px-8 py-3 rounded-xl font-semibold text-lg hover:bg-emerald-700 transition shadow-lg shadow-emerald-100"
        >
          开始分析
        </button>
        {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="text-center py-16">
      <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-emerald-200 border-t-emerald-600 mb-4" />
      <h3 className="text-xl font-semibold text-slate-800">AI 融合引擎分析中</h3>
      <p className="text-slate-500 mt-2">正在从 8 个维度评估您的健康状况</p>
      <div className="mt-6 flex justify-center gap-3">
        {['风险评分', '安全闸门', '融合推荐', '证据分级'].map(s => (
          <span key={s} className="px-3 py-1 bg-slate-100 text-slate-500 text-xs rounded-full">{s}</span>
        ))}
      </div>
    </div>
  );
}

function ResultsView({ data, onRetry }) {
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center mb-4">
        <h2 className="text-2xl font-bold text-emerald-700">分析完成</h2>
        <p className="text-slate-500 mt-1">以下是您的个性化健康建议</p>
      </div>

      {data.banner && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
          <p className="text-emerald-800 font-medium">{data.banner}</p>
        </div>
      )}

      {data.weak_axes && data.weak_axes.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-3">⚠️ 重点关注维度</h3>
          <div className="flex flex-wrap gap-2">
            {data.weak_axes.map((a, i) => (
              <span key={i} className="px-3 py-1.5 bg-amber-100 text-amber-800 text-sm font-medium rounded-lg">
                {a}
              </span>
            ))}
          </div>
        </div>
      )}

      {data.recommendations && data.recommendations.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold text-slate-800">个性化建议（{data.recommendations.length} 条）</h3>
          {data.recommendations.map((r, i) => (
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

      {data.evidence_chain && data.evidence_chain.length > 0 && (
        <details className="bg-white rounded-2xl shadow-sm p-6">
          <summary className="cursor-pointer font-medium text-slate-800">📚 证据链（{data.evidence_chain.length} 条）</summary>
          <ul className="mt-3 space-y-1 text-sm text-slate-600">
            {data.evidence_chain.map((c, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-xs text-slate-400 mt-0.5 shrink-0">[{c.evidence_level}]</span>
                <span>{c.name} — {c.tcm_source || c.gene_relevance || '（通用推荐）'}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {data.post_findings && data.post_findings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-amber-800 font-medium">⚠️ 以下建议需要额外注意：</p>
          {data.post_findings.map((f, i) => (
            <p key={i} className="text-sm text-amber-700 mt-1">• {f.description}</p>
          ))}
        </div>
      )}

      <div className="flex gap-3 pt-4">
        <button
          onClick={() => { window.location.href = '/assess'; }}
          className="flex-1 bg-emerald-600 text-white py-2.5 rounded-xl font-medium hover:bg-emerald-700 transition"
        >
          详细健康评估 →
        </button>
        <button
          onClick={onRetry}
          className="flex-1 bg-slate-100 text-slate-700 py-2.5 rounded-xl font-medium hover:bg-slate-200 transition"
        >
          重新评估
        </button>
      </div>
    </div>
  );
}

function HistoryDashboard({ data, onNewQuiz }) {
  const overview = data.overview || {};
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">欢迎回来</h2>
          <p className="text-slate-500 text-sm">以下是您的健康概览</p>
        </div>
        <button
          onClick={onNewQuiz}
          className="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 transition"
        >
          重新评估
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="八轴弱项" value={overview.weak_axes || '—'} color="bg-amber-50 border-amber-200" />
        <StatCard label="融合评分" value={overview.fusion_score ?? '—'} color="bg-emerald-50 border-emerald-200" />
        <StatCard label="慢病风险" value={overview.risk_level || '—'} color="bg-rose-50 border-rose-200" />
        <StatCard label="中医体质" value={overview.tcm_type || '—'} color="bg-blue-50 border-blue-200" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink to="/checkin" icon="📅" label="每日打卡" desc="记录血压、血糖、体重等指标" />
        <QuickLink to="/reports" icon="📊" label="健康报告" desc="查看历史评估与趋势" />
        <QuickLink to="/agent" icon="🤖" label="AI 对话" desc="向健康顾问提问" />
      </div>
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div className={`${color} border rounded-xl p-4`}>
      <p className="text-sm text-slate-600">{label}</p>
      <p className="text-xl font-bold mt-1 break-all">{value}</p>
    </div>
  );
}

function QuickLink({ to, icon, label, desc }) {
  return (
    <a href={to} className="block bg-white rounded-xl shadow-sm p-5 hover:shadow-md transition">
      <div className="text-2xl mb-2">{icon}</div>
      <p className="font-semibold text-slate-800">{label}</p>
      <p className="text-sm text-slate-500 mt-0.5">{desc}</p>
    </a>
  );
}
