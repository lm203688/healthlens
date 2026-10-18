import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import CheckinHeatmap from '../components/CheckinHeatmap';

/* 留存闭环页：健康目标 / 通知中心 / 依从追踪
 * 后端三支柱已就绪（/api/v1/goals、/notifications、/adherence），此前前端无入口。
 * 本页把「设目标 → 收提醒 → 记录执行」串成可回访的闭环。 */

const GOAL_TYPES = ['weight', 'steps', 'bp', 'glucose', 'exercise', 'sleep'];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export default function Retention() {
  const { t } = useTranslation();
  const [tab, setTab] = useState('goals');

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">{t('retention.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">{t('retention.subtitle')}</p>
      </div>

      <div className="flex gap-2 bg-slate-100 p-1 rounded-xl w-fit">
        {[
          { key: 'goals', label: t('retention.tabGoals') },
          { key: 'notifications', label: t('retention.tabNotifications') },
          { key: 'adherence', label: t('retention.tabAdherence') },
        ].map((item) => (
          <button
            key={item.key}
            onClick={() => setTab(item.key)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === item.key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'goals' && <GoalsPanel />}
      {tab === 'notifications' && <NotificationsPanel />}
      {tab === 'adherence' && <AdherencePanel />}
    </div>
  );
}

/* ------------------------------- 健康目标 ------------------------------- */

function GoalsPanel() {
  const { t } = useTranslation();
  const [goals, setGoals] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    goal_type: 'steps',
    goal_name: '',
    target_value: '',
    unit: '步',
    target_date: todayISO(),
  });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [listResp, statsResp] = await Promise.all([api.goalsList(), api.goalsStats()]);
      const listData = await listResp.json();
      if (listData?.success) setGoals(listData.data || []);
      const statsData = await statsResp.json();
      if (statsData?.success) setStats(statsData.data);
    } catch {
      // 网络异常不阻塞页面渲染
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const resp = await api.goalCreate({
        goal_type: form.goal_type,
        goal_name: form.goal_name,
        target_value: Number(form.target_value),
        unit: form.unit,
        target_date: new Date(form.target_date || todayISO()).toISOString(),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || t('retention.createFailed'));
      setShowForm(false);
      setForm({ goal_type: 'steps', goal_name: '', target_value: '', unit: '步', target_date: todayISO() });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function recordProgress(goal) {
    const raw = window.prompt(t('retention.progressPrompt', { name: goal.goal_name }), String(goal.current_value ?? ''));
    if (raw === null || raw.trim() === '') return;
    try {
      await api.goalProgress(goal.id, { value: Number(raw) });
      await load();
    } catch {
      setError(t('retention.saveFailed'));
    }
  }

  async function removeGoal(id) {
    try {
      await api.goalDelete(id);
      setGoals((prev) => prev.filter((g) => g.id !== id));
      await load();
    } catch {
      setError(t('retention.deleteFailed'));
    }
  }

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg text-sm">{error}</div>}

      <div className="grid grid-cols-3 gap-4">
        <StatCard label={t('retention.statTotal')} value={stats?.total ?? 0} tone="slate" />
        <StatCard label={t('retention.statActive')} value={stats?.active ?? 0} tone="emerald" />
        <StatCard label={t('retention.statCompleted')} value={stats?.completed ?? 0} tone="indigo" />
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-slate-800">{t('retention.myGoals')}</h3>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            {showForm ? t('common.cancel') : t('retention.newGoal')}
          </button>
        </div>

        {showForm && (
          <form onSubmit={handleCreate} className="grid grid-cols-2 gap-3 mb-6 p-4 bg-slate-50 rounded-xl">
            <select
              value={form.goal_type}
              onChange={(e) => setForm({ ...form, goal_type: e.target.value })}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white"
            >
              {GOAL_TYPES.map((gt) => (
                <option key={gt} value={gt}>{t(`retention.goalType.${gt}`)}</option>
              ))}
            </select>
            <input
              required
              value={form.goal_name}
              onChange={(e) => setForm({ ...form, goal_name: e.target.value })}
              placeholder={t('retention.goalNamePlaceholder')}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
            <input
              required
              type="number"
              step="any"
              value={form.target_value}
              onChange={(e) => setForm({ ...form, target_value: e.target.value })}
              placeholder={t('retention.targetPlaceholder')}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
            <input
              required
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              placeholder={t('retention.unitPlaceholder')}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
            <input
              required
              type="date"
              value={form.target_date}
              onChange={(e) => setForm({ ...form, target_date: e.target.value })}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm col-span-2"
            />
            <button
              type="submit"
              disabled={saving}
              className="col-span-2 bg-indigo-600 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? t('common.saving') : t('retention.saveGoal')}
            </button>
          </form>
        )}

        {loading ? (
          <div className="text-center py-8 text-slate-400">{t('common.loading')}</div>
        ) : goals.length === 0 ? (
          <div className="text-center py-8 text-slate-400">{t('retention.noGoals')}</div>
        ) : (
          <div className="space-y-3">
            {goals.map((goal) => (
              <div key={goal.id} className="p-4 bg-slate-50 rounded-xl">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-slate-800">{goal.goal_name}</div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {t(`retention.goalType.${goal.goal_type}`, goal.goal_type)} · {goal.current_value ?? 0} / {goal.target_value} {goal.unit}
                      {goal.target_date ? ` · ${t('retention.dueBy')} ${new Date(goal.target_date).toLocaleDateString()}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-1 rounded-full ${
                      goal.status === 'completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-indigo-100 text-indigo-700'
                    }`}>
                      {t(`retention.status.${goal.status}`, goal.status)}
                    </span>
                    <button onClick={() => recordProgress(goal)} className="text-indigo-600 text-sm hover:text-indigo-800">
                      {t('retention.record')}
                    </button>
                    <button onClick={() => removeGoal(goal.id)} className="text-red-500 text-sm hover:text-red-700">
                      {t('common.delete')}
                    </button>
                  </div>
                </div>
                <div className="mt-3 h-2 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all"
                    style={{ width: `${Math.min(100, Math.max(0, goal.progress || 0))}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------- 通知中心 ------------------------------- */

const SEVERITY_STYLE = {
  info: 'border-l-indigo-400 bg-indigo-50/50',
  warning: 'border-l-amber-400 bg-amber-50/50',
  critical: 'border-l-red-400 bg-red-50/50',
};

function NotificationsPanel() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const resp = await api.notifications();
      const data = await resp.json();
      if (data?.success) {
        setItems(data.data || []);
        setUnread(data.meta?.unread_count ?? 0);
      }
    } catch {
      // 静默失败，页面仍可交互
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function markRead(id) {
    await api.notificationRead(id);
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    setUnread((v) => Math.max(0, v - 1));
  }

  async function markAllRead() {
    await api.notificationsReadAll();
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnread(0);
  }

  async function remove(id) {
    await api.notificationDelete(id);
    setItems((prev) => prev.filter((n) => n.id !== id));
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-slate-800">
          {t('retention.inbox')}
          {unread > 0 && (
            <span className="ml-2 text-xs bg-red-500 text-white px-2 py-0.5 rounded-full">{unread}</span>
          )}
        </h3>
        {unread > 0 && (
          <button onClick={markAllRead} className="text-indigo-600 text-sm hover:text-indigo-800">
            {t('retention.markAllRead')}
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-center py-8 text-slate-400">{t('common.loading')}</div>
      ) : items.length === 0 ? (
        <div className="text-center py-8 text-slate-400">{t('retention.noNotifications')}</div>
      ) : (
        <div className="space-y-3">
          {items.map((n) => (
            <div
              key={n.id}
              className={`p-4 rounded-xl border-l-4 ${SEVERITY_STYLE[n.severity] || SEVERITY_STYLE.info} ${
                n.is_read ? 'opacity-60' : ''
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-slate-800 text-sm">{n.title}</div>
                  <div className="text-sm text-slate-600 mt-1 whitespace-pre-wrap break-words">{n.content}</div>
                  <div className="text-xs text-slate-400 mt-2">
                    {n.category} · {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  {!n.is_read && (
                    <button onClick={() => markRead(n.id)} className="text-indigo-600 text-xs hover:text-indigo-800">
                      {t('retention.markRead')}
                    </button>
                  )}
                  {n.action_url && (
                    <a href={n.action_url} className="text-xs text-emerald-600 hover:text-emerald-800">
                      {n.action_label || t('retention.viewDetail')}
                    </a>
                  )}
                  <button onClick={() => remove(n.id)} className="text-slate-400 text-xs hover:text-red-500">
                    {t('common.delete')}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------- 依从追踪 ------------------------------- */

const ADHERENCE_STATUS = ['pending', 'taken', 'missed', 'skipped'];

function AdherencePanel() {
  const { t } = useTranslation();
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({ medication_name: '', prescribed_dose: '', scheduled_at: '' });

  const load = useCallback(async () => {
    try {
      const [listResp, statsResp] = await Promise.all([api.adherenceList(), api.adherenceStats()]);
      const listData = await listResp.json();
      if (listData?.success) setRecords(listData.data || []);
      const statsData = await statsResp.json();
      if (statsData?.success) setStats(statsData.data);
    } catch {
      // 静默
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const adherenceHeatmap = useMemo(() => {
    const byDate = {};
    records.forEach((r) => {
      const d = (r.scheduled_at || r.taken_at || '').slice(0, 10);
      if (!d) return;
      const v = r.status === 'taken' ? 1 : r.status === 'pending' ? 0.5 : 0;
      if (!byDate[d]) byDate[d] = { sum: 0, n: 0 };
      byDate[d].sum += v;
      byDate[d].n += 1;
    });
    return Object.entries(byDate).map(([date, o]) => ({ date, value: o.sum / o.n }));
  }, [records]);

  async function handleCreate(e) {
    e.preventDefault();
    setError(null);
    try {
      const resp = await api.adherenceCreate({
        medication_name: form.medication_name,
        prescribed_dose: form.prescribed_dose || null,
        scheduled_at: new Date(form.scheduled_at || Date.now()).toISOString(),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || t('retention.createFailed'));
      setForm({ medication_name: '', prescribed_dose: '', scheduled_at: '' });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function updateStatus(id, status) {
    try {
      await api.adherenceUpdate(id, { status });
      await load();
    } catch {
      setError(t('retention.saveFailed'));
    }
  }

  return (
    <div className="space-y-4">
      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg text-sm">{error}</div>}

      <div className="grid grid-cols-3 gap-4">
        <StatCard label={t('retention.statAdherenceRate')} value={stats?.adherence_rate != null ? `${Math.round(stats.adherence_rate)}%` : '—'} tone="emerald" />
        <StatCard label={t('retention.statTaken')} value={stats?.total_taken ?? 0} tone="indigo" />
        <StatCard label={t('retention.statMissed')} value={stats?.total_missed ?? 0} tone="amber" />
      </div>

      {/* 依从热力图（零依赖 SVG） */}
      <div className="bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 mb-3">{t('retention.adherenceHeatmap')}</h3>
        {adherenceHeatmap.length > 0 ? (
          <CheckinHeatmap data={adherenceHeatmap} weeks={12} />
        ) : (
          <p className="text-sm text-slate-400">{t('retention.noAdherenceData')}</p>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6">
        <h3 className="font-semibold text-slate-800 mb-4">{t('retention.addPlan')}</h3>
        <form onSubmit={handleCreate} className="grid grid-cols-2 gap-3 mb-6">
          <input
            required
            value={form.medication_name}
            onChange={(e) => setForm({ ...form, medication_name: e.target.value })}
            placeholder={t('retention.medNamePlaceholder')}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            value={form.prescribed_dose}
            onChange={(e) => setForm({ ...form, prescribed_dose: e.target.value })}
            placeholder={t('retention.dosePlaceholder')}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            required
            type="datetime-local"
            value={form.scheduled_at}
            onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <button type="submit" className="bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700">
            {t('retention.addPlanBtn')}
          </button>
        </form>

        {loading ? (
          <div className="text-center py-8 text-slate-400">{t('common.loading')}</div>
        ) : records.length === 0 ? (
          <div className="text-center py-8 text-slate-400">{t('retention.noRecords')}</div>
        ) : (
          <div className="space-y-3">
            {records.map((r) => (
              <div key={r.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                <div>
                  <div className="font-medium text-slate-800 text-sm">
                    {r.medication_name}
                    {r.prescribed_dose ? <span className="text-slate-500 font-normal"> · {r.prescribed_dose}</span> : null}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {r.scheduled_at ? new Date(r.scheduled_at).toLocaleString() : ''}
                    {r.is_late ? ` · ${t('retention.late')}` : ''}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    r.status === 'taken' ? 'bg-emerald-100 text-emerald-700'
                      : r.status === 'missed' ? 'bg-red-100 text-red-700'
                      : r.status === 'skipped' ? 'bg-slate-200 text-slate-600'
                      : 'bg-indigo-100 text-indigo-700'
                  }`}>
                    {t(`retention.adherenceStatus.${r.status}`, r.status)}
                  </span>
                  {r.status === 'pending' && (
                    <>
                      <button onClick={() => updateStatus(r.id, 'taken')} className="text-emerald-600 text-sm hover:text-emerald-800">
                        {t('retention.markTaken')}
                      </button>
                      <button onClick={() => updateStatus(r.id, 'missed')} className="text-slate-500 text-sm hover:text-red-600">
                        {t('retention.markMissed')}
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------- 通用组件 ------------------------------- */

const TONE_CLASS = {
  slate: 'text-slate-800',
  emerald: 'text-emerald-600',
  indigo: 'text-indigo-600',
  amber: 'text-amber-600',
};

function StatCard({ label, value, tone = 'slate' }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${TONE_CLASS[tone] || TONE_CLASS.slate}`}>{value}</div>
    </div>
  );
}
