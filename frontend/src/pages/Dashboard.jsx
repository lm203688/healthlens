import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

// 结构化健康自评：按身体系统分维度，选项为频率量表
// i18n: 使用 key 而非硬编码中文，翻译在 locale JSON 中
const SECTIONS = [
  {
    key: 'energy',
    titleKey: 'dashboard.sectionEnergy',
    icon: '🌙',
    questionKeys: ['dashboard.qEnergy0', 'dashboard.qEnergy1', 'dashboard.qEnergy2'],
  },
  {
    key: 'mood',
    titleKey: 'dashboard.sectionMood',
    icon: '🧠',
    questionKeys: ['dashboard.qMood0', 'dashboard.qMood1', 'dashboard.qMood2'],
  },
  {
    key: 'digest',
    titleKey: 'dashboard.sectionDigest',
    icon: '🍵',
    questionKeys: ['dashboard.qDigest0', 'dashboard.qDigest1', 'dashboard.qDigest2'],
  },
  {
    key: 'immune',
    titleKey: 'dashboard.sectionImmune',
    icon: '🛡️',
    questionKeys: ['dashboard.qImmune0', 'dashboard.qImmune1', 'dashboard.qImmune2'],
  },
  {
    key: 'body',
    titleKey: 'dashboard.sectionBody',
    icon: '🏃',
    questionKeys: ['dashboard.qBody0', 'dashboard.qBody1', 'dashboard.qBody2'],
  },
];

const OPTION_KEYS = ['dashboard.optRarely', 'dashboard.optOccasionally', 'dashboard.optOften', 'dashboard.optAlways'];

const HEALTH_EXAMPLES = [
  { key: 'dashboard.exFatigue', icon: '🔋' },
  { key: 'dashboard.exInsomnia', icon: '🌙' },
  { key: 'dashboard.exCold', icon: '🧊' },
  { key: 'dashboard.exAnxiety', icon: '🧠' },
  { key: 'dashboard.exDigest', icon: '🍵' },
  { key: 'dashboard.exImmune', icon: '🛡️' },
];

export default function Dashboard() {
  const { t } = useTranslation();
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

  const totalQuestions = SECTIONS.reduce((n, s) => n + s.questionKeys.length, 0);
  const answered = Object.keys(answers).length;
  const progress = Math.round((answered / totalQuestions) * 100);

  function pick(sectionKey, qi, optKey) {
    setAnswers((p) => ({ ...p, [`${sectionKey}-${qi}`]: optKey }));
  }

  function buildInput() {
    const lines = [];
    for (const s of SECTIONS) {
      for (let i = 0; i < s.questionKeys.length; i++) {
        const a = answers[`${s.key}-${i}`];
        if (a) lines.push(`【${t(s.titleKey)}】${t(s.questionKeys[i])} 答:${t(a)}`);
      }
    }
    if (answers._free) lines.push(`自由描述:${answers._free}`);
    return `${t('dashboard.quizTitle')}(近2周):\n${lines.join('\n')}`;
  }

  function startAnalysis() {
    if (answered < 3 && !answers._free) {
      setError(t('dashboard.minQuestions'));
      return;
    }
    setError(null);
    setPhase('loading');
    api.agentFusion({ user_input: buildInput() })
      .then((r) => r.json())
      .then(setResult)
      .then(() => setPhase('results'))
      .catch((err) => { setError(err.message || t('dashboard.analysisFailed')); setPhase('quiz'); });
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center mb-6">
        <h2 className="text-2xl font-bold text-slate-800">{t('dashboard.quizTitle')}</h2>
        <p className="text-slate-500 mt-2">{t('dashboard.quizSubtitle')}</p>
      </div>

      <div className="card p-5 mb-5">
        <div className="flex items-center justify-between mb-2 text-sm">
          <span className="text-slate-500">{t('dashboard.completed')} {answered}/{totalQuestions}</span>
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
              <h3 className="font-semibold text-slate-800">{t(s.titleKey)}</h3>
            </div>
            <div className="space-y-4">
              {s.questionKeys.map((qKey, qi) => (
                <div key={qi}>
                  <p className="text-sm font-medium text-slate-700 mb-2">{t(qKey)}</p>
                  <div className="grid grid-cols-4 gap-2">
                    {OPTION_KEYS.map((optKey) => (
                      <button
                        key={optKey}
                        type="button"
                        onClick={() => pick(s.key, qi, optKey)}
                        className={`py-2 rounded-lg text-sm font-medium transition border
                          ${answers[`${s.key}-${qi}`] === optKey
                            ? 'bg-brand-600 text-white border-brand-600 shadow-sm'
                            : 'bg-white text-slate-600 border-slate-200 hover:border-brand-300 hover:bg-brand-50'}`}
                      >
                        {t(optKey)}
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
        <h3 className="font-semibold text-slate-800 mb-1">{t('dashboard.describeSituation')}</h3>
        <p className="text-sm text-slate-500 mb-3">{t('dashboard.describeHint')}</p>
        <div className="flex flex-wrap gap-2 mb-3">
          {HEALTH_EXAMPLES.map((ex, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setAnswers((p) => ({ ...p, _free: t(ex.key) }))}
              className={`chip border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 ${answers._free === t(ex.key) ? 'ring-2 ring-brand-400' : ''}`}
            >
              {ex.icon} {t(ex.key)}
            </button>
          ))}
        </div>
        <textarea
          value={answers._free || ''}
          onChange={(e) => setAnswers((p) => ({ ...p, _free: e.target.value }))}
          rows={3}
          placeholder={t('dashboard.describePlaceholder')}
          className="input-base resize-none"
        />
      </div>

      <div className="text-center mt-6">
        <button onClick={startAnalysis} disabled={answered < 3 && !answers._free}
          className="btn-primary text-lg px-10">
          {t('dashboard.startAnalysis')}
        </button>
        {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
      </div>
    </div>
  );
}

function LoadingState() {
  const { t } = useTranslation();
  return (
    <div className="text-center py-20">
      <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-brand-200 border-t-brand-600 mb-4" />
      <h3 className="text-xl font-semibold text-slate-800">{t('dashboard.analyzing')}</h3>
      <p className="text-slate-500 mt-2">{t('dashboard.analyzingDesc')}</p>
      <div className="mt-6 flex justify-center gap-3">
        {[t('dashboard.stepRisk'), t('dashboard.stepGate'), t('dashboard.stepRecommend'), t('dashboard.stepEvidence')].map((s) => (
          <span key={s} className="px-3 py-1 bg-slate-100 text-slate-500 text-xs rounded-full">{s}</span>
        ))}
      </div>
    </div>
  );
}

function ResultsView({ data, onRetry }) {
  const { t } = useTranslation();
  const recs = data?.recommendations || [];
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center mb-2">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-brand-100 text-brand-600 text-2xl mb-3">✓</div>
        <h2 className="text-2xl font-bold text-slate-800">{t('dashboard.analysisComplete')}</h2>
        <p className="text-slate-500 mt-1">{t('dashboard.analysisCompleteDesc')}</p>
      </div>

      {data?.banner && (
        <div className="card p-4 border-brand-200 bg-brand-50">
          <p className="text-brand-800 font-medium">{data.banner}</p>
        </div>
      )}

      {data?.weak_axes?.length > 0 && (
        <div className="card p-5">
          <h3 className="font-semibold text-slate-800 mb-3">⚠️ {t('dashboard.focusAreas')}</h3>
          <div className="flex flex-wrap gap-2">
            {data.weak_axes.map((a, i) => (
              <span key={i} className="px-3 py-1.5 bg-amber-100 text-amber-800 text-sm font-medium rounded-lg">{a}</span>
            ))}
          </div>
        </div>
      )}

      {recs.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold text-slate-800">{t('dashboard.personalizedRecs')}（{recs.length} {t('dashboard.recCount')}）</h3>
          {recs.map((r, i) => (
            <div key={i} className={`card p-4 ${r.gate_passed ? '' : 'border-red-200 bg-red-50'}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${r.gate_passed ? 'bg-brand-100 text-brand-700' : 'bg-red-100 text-red-700'}`}>
                  {r.gate_passed ? '✅ ' + t('dashboard.gatePassed') : '🚫 ' + t('dashboard.gateFailed')}
                </span>
                <span className="font-medium text-slate-800">{r.name || t('dashboard.recDefault', { n: i + 1 })}</span>
              </div>
              {r.prescription && <p className="text-sm text-slate-600 mt-1">{r.prescription}</p>}
              {r.monitor_markers && <p className="text-xs text-slate-400 mt-1">📊 {t('dashboard.monitorMarkers')}：{r.monitor_markers}</p>}
              {r.evidence_level && <p className="text-xs text-slate-400 mt-0.5">📚 {t('dashboard.evidenceLevel')}：{r.evidence_level}</p>}
            </div>
          ))}
        </div>
      )}

      {data?.evidence_chain?.length > 0 && (
        <details className="card p-5">
          <summary className="cursor-pointer font-medium text-slate-800">📚 {t('dashboard.evidenceChain')}（{data.evidence_chain.length} {t('dashboard.recCount')}）</summary>
          <ul className="mt-3 space-y-1 text-sm text-slate-600">
            {data.evidence_chain.map((c, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-xs text-slate-400 mt-0.5 shrink-0">[{c.evidence_level}]</span>
                <span>{c.name} — {c.tcm_source || c.gene_relevance || t('dashboard.generalRec')}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {data?.post_findings?.length > 0 && (
        <div className="card p-4 border-amber-200 bg-amber-50">
          <p className="text-amber-800 font-medium">⚠️ {t('dashboard.caution')}：</p>
          {data.post_findings.map((f, i) => (
            <p key={i} className="text-sm text-amber-700 mt-1">• {f.description}</p>
          ))}
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button onClick={() => { window.location.href = '/assess'; }} className="btn-primary flex-1">{t('dashboard.detailAssess')} →</button>
        <button onClick={onRetry} className="btn-ghost flex-1">{t('dashboard.reAssess')}</button>
      </div>
    </div>
  );
}

function HistoryDashboard({ data, onNewQuiz }) {
  const { t } = useTranslation();
  const overview = data.overview || {};
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">{t('dashboard.welcomeBack')}</h2>
          <p className="text-slate-500 text-sm">{t('dashboard.healthOverview')}</p>
        </div>
        <button onClick={onNewQuiz} className="btn-primary text-sm">{t('dashboard.reAssess')}</button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label={t('dashboard.focusAreas')} value={overview.weak_axes || '—'} color="bg-amber-50 border-amber-200" />
        <StatCard label={t('dashboard.fusionScore')} value={overview.fusion_score ?? '—'} color="bg-brand-50 border-brand-200" />
        <StatCard label={t('dashboard.riskLevel')} value={overview.risk_level || '—'} color="bg-rose-50 border-rose-200" />
        <StatCard label={t('dashboard.tcmType')} value={overview.tcm_type || '—'} color="bg-blue-50 border-blue-200" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink to="/checkin" icon="📅" label={t('dashboard.dailyCheckin')} desc={t('dashboard.checkinDesc')} />
        <QuickLink to="/reports" icon="📊" label={t('dashboard.healthReports')} desc={t('dashboard.reportsDesc')} />
        <QuickLink to="/agent" icon="🤖" label={t('dashboard.aiChat')} desc={t('dashboard.agentDesc')} />
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
