import { useState, useEffect } from 'react';
import { api } from '../api/client';

// 结构化健康自评：按身体系统分维度，选项为频率量表
const SECTIONS = [
  {
    key: 'energy',
    title: '精力与睡眠',
    icon: '🌙',
    questions: [
      '近 2 周，您是否经常感到白天疲惫、提不起精神？',
      '您的睡眠质量如何（入睡困难 / 易醒 / 早醒）？',
      '您是否常觉得睡够时间仍恢复不过来？',
    ],
  },
  {
    key: 'mood',
    title: '情绪与压力',
    icon: '🧠',
    questions: [
      '您是否经常感到焦虑、紧张或情绪低落？',
      '面对压力时，您是否容易出现心慌、易怒？',
      '您是否觉得注意力难以集中、记忆力下降？',
    ],
  },
  {
    key: 'digest',
    title: '消化与代谢',
    icon: '🍵',
    questions: [
      '您是否常有腹胀、消化不良或食欲不稳？',
      '您是否容易上火、口舌生疮或便秘/腹泻交替？',
      '您的体重是否近期明显波动或难以控制？',
    ],
  },
  {
    key: 'immune',
    title: '免疫与体质',
    icon: '🛡️',
    questions: [
      '您是否比周围人更容易感冒或感染？',
      '您是否怕冷、手脚冰凉或畏风？',
      '换季时您的身体是否更容易出现不适？',
    ],
  },
  {
    key: 'body',
    title: '运动与体态',
    icon: '🏃',
    questions: [
      '您每周规律运动（中等强度 30 分钟以上）少于 2 次吗？',
      '您是否常久坐、颈肩腰背不适？',
      '您是否觉得自己体能明显下降？',
    ],
  },
];

const OPTIONS = ['很少', '偶尔', '经常', '总是'];

const HEALTH_EXAMPLES = [
  { label: '疲劳乏力、没精神', icon: '🔋' },
  { label: '失眠、睡不好', icon: '🌙' },
  { label: '怕冷、手脚冰凉', icon: '🧊' },
  { label: '焦虑、压力大', icon: '🧠' },
  { label: '消化不良、腹胀', icon: '🍵' },
  { label: '易感冒、体质弱', icon: '🛡️' },
];

export default function Dashboard() {
  const [phase, setPhase] = useState('quiz'); // quiz | loading | results
  const [answers, setAnswers] = useState({}); // { 'energy-0': '经常', ... }
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [hasHistory, setHasHistory] = useState(false);
  const [historyData, setHistoryData] = useState(null);

  useEffect(() => {
    api.dashboard().then((r) => r.json()).then((data) => {
      if (data?.success && data.data?.overview?.weak_axes?.length) {
        setHasHistory(true);
        setHistoryData(data.data);
      }
    }).catch(() => {});
  }, []);

  if (hasHistory && historyData) {
    return <HistoryDashboard data={historyData} onNewQuiz={() => setPhase('quiz')} />;
  }
  if (phase === 'loading') return <LoadingState />;
  if (phase === 'results' && result) {
    return <ResultsView data={result} onRetry={() => setPhase('quiz')} />;
  }

  const totalQuestions = SECTIONS.reduce((n, s) => n + s.questions.length, 0);
  const answered = Object.keys(answers).length;
  const progress = Math.round((answered / totalQuestions) * 100);

  function pick(sectionKey, qi, opt) {
    setAnswers((p) => ({ ...p, [`${sectionKey}-${qi}`]: opt }));
  }

  function buildInput() {
    const lines = [];
    for (const s of SECTIONS) {
      for (let i = 0; i < s.questions.length; i++) {
        const a = answers[`${s.key}-${i}`];
        if (a) lines.push(`【${s.title}】${s.questions[i]} 答:${a}`);
      }
    }
    if (answers._free) lines.push(`自由描述:${answers._free}`);
    return `健康自评（近2周）:\n${lines.join('\n')}`;
  }

  function startAnalysis() {
    if (answered < 3 && !answers._free) {
      setError('请至少回答 3 个问题，或描述您的情况');
      return;
    }
    setError(null);
    setPhase('loading');
    api.agentFusion({ user_input: buildInput() })
      .then((r) => r.json())
      .then(setResult)
      .then(() => setPhase('results'))
      .catch((err) => { setError(err.message || '分析失败，请重试'); setPhase('quiz'); });
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center mb-6">
        <h2 className="text-2xl font-bold text-slate-800">3 分钟健康自评</h2>
        <p className="text-slate-500 mt-2">从 5 大身体系统评估您的状态，AI 融合引擎将给出可执行的调理建议</p>
      </div>

      <div className="card p-5 mb-5">
        <div className="flex items-center justify-between mb-2 text-sm">
          <span className="text-slate-500">已完成 {answered}/{totalQuestions}</span>
          <span className="text-brand-600 font-medium">{progress}%</span>
        </div>
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div className="h-full bg-brand-500 rounded-full transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="space-y-4">
        {SECTIONS.map((s) => (
          <div key={s.key} className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xl">{s.icon}</span>
              <h3 className="font-semibold text-slate-800">{s.title}</h3>
            </div>
            <div className="space-y-4">
              {s.questions.map((q, qi) => (
                <div key={qi}>
                  <p className="text-sm font-medium text-slate-700 mb-2">{q}</p>
                  <div className="grid grid-cols-4 gap-2">
                    {OPTIONS.map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => pick(s.key, qi, opt)}
                        className={`py-2 rounded-lg text-sm font-medium transition border
                          ${answers[`${s.key}-${qi}`] === opt
                            ? 'bg-brand-600 text-white border-brand-600 shadow-sm'
                            : 'bg-white text-slate-600 border-slate-200 hover:border-brand-300 hover:bg-brand-50'}`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="card p-5 mt-4">
        <h3 className="font-semibold text-slate-800 mb-1">或描述您的情况</h3>
        <p className="text-sm text-slate-500 mb-3">点击下方常见问题，或在框中自由输入</p>
        <div className="flex flex-wrap gap-2 mb-3">
          {HEALTH_EXAMPLES.map((ex, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setAnswers((p) => ({ ...p, _free: ex.label }))}
              className={`chip border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 ${answers._free === ex.label ? 'ring-2 ring-brand-400' : ''}`}
            >
              {ex.icon} {ex.label}
            </button>
          ))}
        </div>
        <textarea
          value={answers._free || ''}
          onChange={(e) => setAnswers((p) => ({ ...p, _free: e.target.value }))}
          rows={3}
          placeholder="例如：最近容易疲劳，晚上睡不好，胃口也一般…"
          className="input-base resize-none"
        />
      </div>

      <div className="text-center mt-6">
        <button onClick={startAnalysis} disabled={answered < 3 && !answers._free}
          className="btn-primary text-lg px-10">
          开始 AI 分析
        </button>
        {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="text-center py-20">
      <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-brand-200 border-t-brand-600 mb-4" />
      <h3 className="text-xl font-semibold text-slate-800">AI 融合引擎分析中</h3>
      <p className="text-slate-500 mt-2">正在从基因、通路、中医与食养多维度评估您的健康</p>
      <div className="mt-6 flex justify-center gap-3">
        {['风险评分', '安全闸门', '融合推荐', '证据分级'].map((s) => (
          <span key={s} className="px-3 py-1 bg-slate-100 text-slate-500 text-xs rounded-full">{s}</span>
        ))}
      </div>
    </div>
  );
}

function ResultsView({ data, onRetry }) {
  const recs = data?.recommendations || [];
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center mb-2">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-brand-100 text-brand-600 text-2xl mb-3">✓</div>
        <h2 className="text-2xl font-bold text-slate-800">分析完成</h2>
        <p className="text-slate-500 mt-1">以下是基于您自评的个性化健康建议</p>
      </div>

      {data?.banner && (
        <div className="card p-4 border-brand-200 bg-brand-50">
          <p className="text-brand-800 font-medium">{data.banner}</p>
        </div>
      )}

      {data?.weak_axes?.length > 0 && (
        <div className="card p-5">
          <h3 className="font-semibold text-slate-800 mb-3">⚠️ 重点关注维度</h3>
          <div className="flex flex-wrap gap-2">
            {data.weak_axes.map((a, i) => (
              <span key={i} className="px-3 py-1.5 bg-amber-100 text-amber-800 text-sm font-medium rounded-lg">{a}</span>
            ))}
          </div>
        </div>
      )}

      {recs.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold text-slate-800">个性化建议（{recs.length} 条）</h3>
          {recs.map((r, i) => (
            <div key={i} className={`card p-4 ${r.gate_passed ? '' : 'border-red-200 bg-red-50'}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${r.gate_passed ? 'bg-brand-100 text-brand-700' : 'bg-red-100 text-red-700'}`}>
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

      {data?.evidence_chain?.length > 0 && (
        <details className="card p-5">
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

      {data?.post_findings?.length > 0 && (
        <div className="card p-4 border-amber-200 bg-amber-50">
          <p className="text-amber-800 font-medium">⚠️ 以下建议需要额外注意：</p>
          {data.post_findings.map((f, i) => (
            <p key={i} className="text-sm text-amber-700 mt-1">• {f.description}</p>
          ))}
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button onClick={() => { window.location.href = '/assess'; }} className="btn-primary flex-1">详细健康评估 →</button>
        <button onClick={onRetry} className="btn-ghost flex-1">重新评估</button>
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
          <h2 className="text-2xl font-bold text-slate-800">欢迎回来</h2>
          <p className="text-slate-500 text-sm">以下是您的健康概览</p>
        </div>
        <button onClick={onNewQuiz} className="btn-primary text-sm">重新评估</button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="重点关注维度" value={overview.weak_axes || '—'} color="bg-amber-50 border-amber-200" />
        <StatCard label="融合评分" value={overview.fusion_score ?? '—'} color="bg-brand-50 border-brand-200" />
        <StatCard label="风险等级" value={overview.risk_level || '—'} color="bg-rose-50 border-rose-200" />
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
    <a href={to} className="card p-5 hover:shadow-md transition block">
      <div className="text-2xl mb-2">{icon}</div>
      <p className="font-semibold text-slate-800">{label}</p>
      <p className="text-sm text-slate-500 mt-0.5">{desc}</p>
    </a>
  );
}
