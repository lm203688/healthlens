import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

const PROVIDER_ICONS = {
  garmin: '⌚', oura: '💍', whoop: '📿', polar: '⌚', suunto: '⌚',
  strava: '🏃', fitbit: '⌚', ultrahuman: '💍', withings: '⚖️', google_health: '📱',
};

export default function WearableDevices() {
  const { t } = useTranslation();
  const token = localStorage.getItem('token');
  const [connections, setConnections] = useState([]);
  const [providers, setProviders] = useState([]);
  const [owStatus, setOwStatus] = useState('unknown');
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState(null);
  const [showSelect, setShowSelect] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.connections().then(r => r.json()).catch(() => null),
      fetch(`/api/v1/connections/open-wearables/providers`, {
        headers: { 'Authorization': `Bearer ${token}` },
      }).then(r => r.json()).catch(() => null),
    ]).then(([connRes, providerRes]) => {
      const all = connRes?.data || [];
      setConnections(all.filter(c => c.source_type === 'open_wearables'));
      if (providerRes?.data) {
        setProviders(providerRes.data.providers || []);
        setOwStatus(providerRes.data.ow_status || 'unknown');
      }
    }).finally(() => setLoading(false));
  }, [token]);

  async function handleConnect() {
    if (!selectedProvider) return;
    setConnecting(true);
    setError(null);
    try {
      const resp = await fetch('/api/v1/connections/open-wearables/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ provider: selectedProvider }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || t('wearable.connectFailed'));
      setShowSelect(false);
      const all = await api.connections().then(r => r.json());
      setConnections((all?.data || []).filter(c => c.source_type === 'open_wearables'));
      setSyncMsg(t('wearable.connected', { provider: selectedProvider }));
      setSelectedProvider('');
    } catch (err) {
      setError(err.message);
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect(id) {
    setError(null);
    try {
      const resp = await fetch(`/api/v1/connections/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || t('wearable.disconnectFailed'));
      setConnections(prev => prev.filter(c => c.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSyncAll() {
    setSyncing(true);
    setSyncMsg(null);
    setError(null);
    try {
      const resp = await fetch('/api/v1/connections/open-wearables/sync-all', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || t('wearable.syncFailed'));
      setSyncMsg(t('wearable.syncDone', { count: data?.data?.synced || 0 }));
    } catch (err) {
      setError(err.message);
    } finally {
      setSyncing(false);
    }
  }

  if (loading) return null;

  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-slate-800">⌚ {t('wearable.title')}</h3>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            owStatus === 'online' ? 'bg-green-100 text-green-700' :
            owStatus === 'mock' ? 'bg-amber-100 text-amber-700' :
            'bg-slate-100 text-slate-500'
          }`}>
            {owStatus === 'online' ? t('wearable.owOnline') : owStatus === 'mock' ? t('wearable.owMock') : t('wearable.owOffline')}
          </span>
          {connections.length > 0 && (
            <button
              onClick={handleSyncAll}
              disabled={syncing}
              className="text-xs bg-emerald-600 text-white px-3 py-1 rounded-lg hover:bg-emerald-700 disabled:opacity-50"
            >
              {syncing ? t('common.syncing') : t('wearable.syncAll')}
            </button>
          )}
        </div>
      </div>

      {/* 已连接设备 */}
      {connections.length > 0 && (
        <div className="mb-4 space-y-2">
          {connections.map(conn => (
            <div key={conn.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center gap-2">
                <span className="text-lg">{conn.source_type === 'open_wearables' ? '⌚' : '🔌'}</span>
                <div>
                  <p className="text-sm font-medium text-slate-800">Open Wearables</p>
                  <p className="text-xs text-slate-400">
                    {conn.last_sync_at ? t('wearable.lastSync', { time: new Date(conn.last_sync_at).toLocaleString() }) : t('wearable.notSynced')}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  conn.sync_status === 'completed' ? 'bg-green-100 text-green-700' :
                  conn.sync_status === 'failed' ? 'bg-red-100 text-red-700' :
                  'bg-slate-100 text-slate-500'
                }`}>
                  {conn.sync_status || 'pending'}
                </span>
                <button
                  onClick={() => handleDisconnect(conn.id)}
                  className="text-xs text-red-500 hover:text-red-700"
                >
                  {t('wearable.disconnect')}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 添加设备 */}
      <button
        onClick={() => setShowSelect(true)}
        className="w-full border-2 border-dashed border-slate-300 rounded-lg py-3 text-sm text-slate-500 hover:border-emerald-400 hover:text-emerald-600 transition"
      >
        + {t('wearable.addDevice')}
      </button>

      {/* 提供商选择弹窗 */}
      {showSelect && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setShowSelect(false)}>
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-4">{t('wearable.selectProvider')}</h3>
            <div className="grid grid-cols-2 gap-3 mb-4">
              {providers.map(p => (
                <button
                  key={p.id}
                  onClick={() => setSelectedProvider(p.id)}
                  className={`p-3 rounded-lg border text-left transition ${
                    selectedProvider === p.id
                      ? 'border-emerald-500 bg-emerald-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <span className="text-2xl">{p.icon || PROVIDER_ICONS[p.id] || '⌚'}</span>
                  <p className="text-sm font-medium mt-1">{p.name}</p>
                  {p.type && <p className="text-xs text-slate-400">{p.type}</p>}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowSelect(false)}
                className="flex-1 py-2 border rounded-lg text-sm hover:bg-slate-50"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleConnect}
                disabled={!selectedProvider || connecting}
                className="flex-1 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50"
              >
                {connecting ? t('common.connecting') : t('wearable.connect')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 消息 */}
      {syncMsg && <div className="mt-3 bg-emerald-50 text-emerald-700 p-3 rounded-lg text-sm">{syncMsg}</div>}
      {error && <div className="mt-3 bg-red-50 text-red-600 p-3 rounded-lg text-sm">{error}</div>}
    </div>
  );
}
