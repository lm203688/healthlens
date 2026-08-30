import { useState, useEffect } from 'react';
import { api } from '../api/client';

const METRICS = [
  { code: '8867-4', name: '血压 (收缩压)', unit: 'mmHg', refLow: 90, refHigh: 140, type: 'number' },
  { code: '8480-6', name: '血压 (舒张压)', unit: 'mmHg', refLow: 60, refHigh: 90, type: 'number' },
  { code: '8867-4', name: '心率', unit: 'bpm', refLow: 60, refHigh: 100, type: 'number' },
  { code: '2339-0', name: '空腹血糖', unit: 'mmol/L', refLow: 3.9, refHigh: 6.1, type: 'number' },
  { code: '2160-0', name: '体重', unit: 'kg', refLow: 0, refHigh: 999, type: 'number' },
  { code: '8302-2', name: '体温', unit: '°C', refLow: 36.1, refHigh: 37.2, type: 'number' },
  { code: '8932-2', name: '血氧饱和度', unit: '%', refLow: 95, refHigh: 100, type: 'number' },
  { code: 'custom', name: '睡眠质量', unit: '', refLow: 0, refHigh: 5, type: 'string', options: ['很差', '较差', '一般', '较好', '很好'] },
  { code: 'custom', name: '情绪状态', unit: '', refLow: 0, refHigh: 5, type: 'string', options: ['很差', '较差', '一般', '较好', '很好'] },
  { code: 'custom', name: '精力水平', unit: '', refLow: 0, refHigh: 5, type: 'string', options: ['很差', '较差', '一般', '较好', '很好'] },
];

export default function CheckIn() {
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    fetchHistory();
  }, []);

  async function fetchHistory() {
    try {
      const resp = await api.observations();
      const data = await resp.json();
      const items = data.results || data.items || data.data || data.observations || (Array.isArray(data) ? data : []);
      if (Array.isArray(items)) setHistory(items.slice(0, 20));
    } catch {
      // silent
    }
  }

  function setMetricValue(code, value) {
    setValues(p => ({ ...p, [code]: value }));
  }

  async function submitCheckIn() {
    const entries = Object.entries(values).filter(([, v]) => v !== '' && v != null);
    if (entries.length === 0) {
      setError('请至少填写一项指标');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    const payloads = entries.map(([code, value]) => {
      const metric = METRICS.find(m => m.code === code);
      const payload = {
        loinc_code: metric ? metric.code : 'custom',
        loinc_name: metric ? metric.name : code,
        value_unit: metric ? metric.unit : '',
        source: 'manual',
      };

      if (metric && metric.options) {
        payload.value_string = String(value);
        payload.value_numeric = metric.options.indexOf(String(value));
      } else {
        payload.value_numeric = parseFloat(value);
      }

      if (metric) {
        payload.reference_range_low = metric.refLow;
        payload.reference_range_high = metric.refHigh;
      }

      return payload;
    });

    try {
      const now = new Date().toISOString();
      const endpoint = entries.length > 1 ? api.observationsBatch : api.observationPost;
      const payload = entries.length > 1
        ? { items: payloads.map(p => ({ ...p, recorded_at: now })) }
        : { ...payloads[0], recorded_at: now };
      const resp = await endpoint(payload);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.message || '提交失败');
      setSuccess(`✅ 成功记录 ${entries.length} 项指标`);
      setValues({});
      fetchHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">📅 每日健康打卡</h2>
        <p className="text-slate-500 text-sm mt-1">记录您的健康指标，长期跟踪变化趋势</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {METRICS.map((m, i) => (
            <div key={i} className="space-y-1">
              <label className="text-sm font-medium text-slate-700">
                {m.name} {m.unit ? <span className="text-xs text-slate-400">({m.unit})</span> : ''}
              </label>
              {m.type === 'number' ? (
                <input
                  type="number"
                  step="any"
                  placeholder={m.name === '空腹血糖' ? '如 5.2' : m.name === '体重' ? '如 65' : ''}
                  value={values[m.code] || ''}
                  onChange={(e) => setMetricValue(m.code, e.target.value)}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none text-sm"
                />
              ) : (
                <div className="flex gap-1.5 flex-wrap">
                  {m.options.map(opt => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setMetricValue(m.code, opt)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition
                        ${values[m.code] === opt
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
              {m.refLow > 0 && m.refHigh < 999 && (
                <p className="text-xs text-slate-400">参考范围：{m.refLow}–{m.refHigh} {m.unit}</p>
              )}
            </div>
          ))}
        </div>

        <div className="mt-6 flex gap-3">
          <button
            onClick={submitCheckIn}
            disabled={loading || Object.keys(values).length === 0}
            className="bg-emerald-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {loading ? '提交中…' : `📤 提交 (${Object.keys(values).length} 项)`}
          </button>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="bg-slate-100 text-slate-700 px-4 py-2.5 rounded-lg font-medium hover:bg-slate-200 transition text-sm"
          >
            📋 历史记录
          </button>
        </div>

        {error && <div className="mt-3 bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>}
        {success && <div className="mt-3 bg-emerald-50 text-emerald-700 text-sm p-3 rounded-lg">{success}</div>}
      </div>

      {showHistory && (
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h3 className="font-semibold text-slate-800 mb-4">📋 最近记录</h3>
          {history.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">暂无记录</p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {history.map((item, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div>
                    <span className="font-medium text-sm text-slate-800">{item.loinc_name || item.name || item.code}</span>
                    <span className="text-xs text-slate-400 ml-2">{item.source || ''}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold">
                      {item.value_numeric != null ? `${item.value_numeric} ${item.value_unit || ''}` : item.value_string || '—'}
                    </span>
                    {item.is_abnormal && <span className="text-xs text-red-500 ml-2">⚠️</span>}
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
