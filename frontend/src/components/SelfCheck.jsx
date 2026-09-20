import { useState, useEffect } from 'react';
import { api } from '../api/client';

/** 主观健康感受自评（SIIV 自测闭环 V 端）
 * 维度：精力 / 消化 / 睡眠，各 1-5 分；可选备注与日期。
 * 长期记录用于观察自身变化趋势（数据飞轮）。非体检、非诊断。 */
const DIMENSIONS = [
  { key: 'energy_score',   label: '精力 / 活力',  emoji: '⚡' },
  { key: 'digestion_score', label: '消化 / 肠胃',  emoji: '🍃' },
  { key: 'sleep_score',    label: '睡眠 / 休息',  emoji: '🌙' },
];

function ScorePicker({ value, onChange }) {
  return (
    <div className="flex gap-1.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className={`w-9 h-9 rounded-lg text-sm font-semibold transition ${
            value === n
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-50 text-slate-500 border border-slate-200 hover:bg-slate-100'
          }`}
          aria-label={`${n} 分`}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

export default function SelfCheck() {
  const [scores, setScores] = useState({ energy_score: 3, digestion_score: 3, sleep_score: 3 });
  const [note, setNote] = useState('');
  const [date, setDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    loadSummary();
    loadHistory();
  }, []);

  async function loadSummary() {
    try {
      const resp = await api.checkinSummary();
      const data = await resp.json();
      if (data?.success) setSummary(data.data);
    } catch { /* silent */ }
  }

  async function loadHistory() {
    try {
      const resp = await api.checkinHistory({ limit: 12 });
      const data = await resp.json();
      if (data?.success) setHistory(data.data.items || []);
    } catch { /* silent */ }
  }

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);
    const payload = {
      ...scores,
      note: note.trim() || null,
      checkin_date: date ? new Date(date).toISOString() : null,
    };
    try {
      const resp = await api.checkinPost(payload);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail?.message || data?.message || data?.detail || '提交失败');
      setSuccess(data.message || '自测已记录');
      setNote('');
      setDate('');
      loadSummary();
      loadHistory();
    } catch (err) {
      setError(err.message || '提交失败');
    } finally {
      setLoading(false);
    }
  }

  const trend = summary?.trend;

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
      <div>
        <h3 className="font-semibold text-slate-800">每周健康自测</h3>
        <p className="text-xs text-slate-500 mt-1">
          凭主观感受给精力 / 消化 / 睡眠打分（1–5）。坚持记录可观察自身变化趋势，非体检、非诊断。
        </p>
      </div>

      <form onSubmit={submit} className="space-y-4">
        {DIMENSIONS.map((d) => (
          <div key={d.key} className="flex items-center justify-between gap-4">
            <span className="text-sm font-medium text-slate-700">
              {d.emoji} {d.label}
            </span>
            <ScorePicker
              value={scores[d.key]}
              onChange={(n) => setScores((p) => ({ ...p, [d.key]: n }))}
            />
          </div>
        ))}

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">备注（可选）</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
            rows={2}
            placeholder="今天的状态、饮食、情绪等"
            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">日期（可选，默认今天）</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={loading}
            className="bg-emerald-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {loading ? '提交中…' : '记录本次自测'}
          </button>
          <button
            type="button"
            onClick={() => setShowHistory(!showHistory)}
            className="bg-slate-100 text-slate-700 px-4 py-2.5 rounded-lg font-medium hover:bg-slate-200 transition text-sm"
          >
            📋 历史记录
          </button>
        </div>

        {error && <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>}
        {success && <div className="bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{success}</div>}
      </form>

      {/* 趋势概览 */}
      {summary && summary.count > 0 && (
        <div className="border-t border-slate-100 pt-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">
              近 {summary.count} 次均值
            </span>
            {summary.averages?.overall != null && (
              <span className="text-lg font-bold text-emerald-700">
                {summary.averages.overall}
                <span className="text-xs font-normal text-slate-400"> / 5</span>
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {DIMENSIONS.map((d) => (
              <div key={d.key} className="bg-slate-50 rounded-lg py-2">
                <p className="text-[11px] text-slate-500">{d.label}</p>
                <p className="text-sm font-semibold text-slate-800">
                  {summary.averages?.[d.key] ?? '—'}
                  {trend && (
                    <span className={`ml-1 text-[11px] ${trend[d.key] > 0 ? 'text-emerald-600' : trend[d.key] < 0 ? 'text-red-500' : 'text-slate-400'}`}>
                      {trend[d.key] > 0 ? '▲' : trend[d.key] < 0 ? '▼' : '—'}
                      {trend[d.key] !== 0 ? Math.abs(trend[d.key]) : ''}
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>
          {!trend && summary.count < 4 && (
            <p className="text-xs text-slate-400">累计 4 次后可显示变化趋势（目前 {summary.count} 次）。</p>
          )}
        </div>
      )}

      {/* 历史 */}
      {showHistory && (
        <div className="border-t border-slate-100 pt-4">
          <h4 className="text-sm font-medium text-slate-700 mb-3">最近自测</h4>
          {history.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-6">暂无记录</p>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {history.map((h) => (
                <div key={h.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg text-sm">
                  <span className="text-xs text-slate-500">
                    {h.checkin_date ? new Date(h.checkin_date).toLocaleDateString('zh-CN') : ''}
                  </span>
                  <div className="flex gap-3 text-slate-700">
                    <span>⚡{h.energy_score}</span>
                    <span>🍃{h.digestion_score}</span>
                    <span>🌙{h.sleep_score}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
