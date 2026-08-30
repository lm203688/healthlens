import { useState } from 'react';
import { api } from '../api/client';

const POPULAR = [
  { tab: 'search', query: '补气' },
  { tab: 'food', query: '黄芪' },
  { tab: 'food', query: '当归' },
  { tab: 'methods', query: '八段锦' },
  { tab: 'search', query: '失眠' },
  { tab: 'methods', query: '艾灸' },
];

export default function Knowledge() {
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('search');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [count, setCount] = useState(0);

  const endpoints = {
    search: { fn: (q) => api.knowledgeSearch(q), label: '全文检索', desc: '搜索中医知识、病症、经络穴位' },
    food:   { fn: (q) => api.knowledgeFood(q),   label: '食疗方',   desc: '查找药食同源食材与食谱' },
    methods:{ fn: (q) => api.knowledgeMethods(q), label: '非药物疗法', desc: '八段锦、太极、艾灸、刮痧等' },
  };

  async function search() {
    setLoading(true);
    setError(null);
    try {
      const resp = await endpoints[tab].fn(query);
      const data = await resp.json();
      setResults(data);
      const items = data.results || data.items || data.data || (Array.isArray(data) ? data : []);
      setCount(Array.isArray(items) ? items.length : 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function quickSearch(item) {
    setTab(item.tab);
    setQuery(item.query);
    setLoading(true);
    setError(null);
    endpoints[item.tab].fn(item.query)
      .then((r) => r.json())
      .then((data) => {
        setResults(data);
        const items = data.results || data.items || data.data || (Array.isArray(data) ? data : []);
        setCount(Array.isArray(items) ? items.length : 1);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">中医知识库</h2>
        <p className="text-slate-500 text-sm mt-1">基于《黄帝内经》《伤寒论》等经典古籍 + 现代非药物疗法</p>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex gap-2">
          {Object.entries(endpoints).map(([k, { label, desc }]) => (
            <button
              key={k}
              onClick={() => { setTab(k); setResults(null); setCount(0); }}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition text-center
                ${tab === k ? 'bg-emerald-100 text-emerald-800' : 'text-slate-500 hover:bg-slate-100'}`}
              title={desc}
            >
              <div>{label}</div>
              <div className="text-xs opacity-70 mt-0.5">{desc}</div>
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder={
              tab === 'food' ? '搜索食疗方（如 黄芪、当归）'
                : tab === 'methods' ? '搜索疗法（如 八段锦、艾灸）'
                : '搜索中医知识（如 补气、失眠）'
            }
            className="flex-1 px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none"
          />
          <button
            onClick={search}
            disabled={loading || !query.trim()}
            className="bg-emerald-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? '搜索中…' : '搜索'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-slate-400 self-center mr-1">热门搜索：</span>
        {POPULAR.map((item, i) => (
          <button
            key={i}
            onClick={() => quickSearch(item)}
            className="px-3 py-1 bg-slate-100 text-slate-600 text-xs rounded-full hover:bg-emerald-100 hover:text-emerald-700 transition"
          >
            {item.query}
          </button>
        ))}
      </div>

      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg">{error}</div>}
      {loading && <p className="text-slate-500 text-center">搜索中…</p>}

      {results && !error && !loading && (
        <div className="space-y-4">
          <div className="text-sm text-slate-500">
            找到 <span className="font-medium text-emerald-700">{count}</span> 条结果
          </div>
          <KnowledgeCards data={results} tab={tab} />
        </div>
      )}

      {!results && !error && !loading && (
        <div className="text-center py-12 text-slate-400">
          <div className="text-4xl mb-3">📚</div>
          <p>输入关键词开始探索中医知识</p>
        </div>
      )}
    </div>
  );
}

function KnowledgeCards({ data, tab }) {
  // Try common response shapes
  const items = data.results || data.items || data.data || (Array.isArray(data) ? data : [data]);
  if (!Array.isArray(items)) return <div className="bg-slate-50 p-3 rounded-lg text-sm text-slate-600">{JSON.stringify(data, null, 2)}</div>;

  if (items.length === 0) return <p className="text-slate-500 text-center py-8">未找到相关结果，请换个关键词试试</p>;

  return items.map((item, i) => {
    if (typeof item === 'string') {
      return <p key={i} className="bg-white rounded-xl shadow-sm p-4 text-sm text-slate-700">{item}</p>;
    }
    return (
      <div key={i} className="bg-white rounded-xl shadow-sm p-4 space-y-2">
        {item.name || item.title || item.keyword ? (
          <h4 className="font-semibold text-slate-800">{item.name || item.title || item.keyword}</h4>
        ) : null}
        {item.description || item.desc || item.summary || item.content ? (
          <p className="text-sm text-slate-600">{item.description || item.desc || item.summary || item.content}</p>
        ) : null}
        {(item.ingredients || item.recipe || item.preparation) && (
          <div className="text-xs text-slate-500">
            <span className="font-medium">用法：</span>
            {item.ingredients ? `食材：${item.ingredients.join('、')}` : ''}
            {item.recipe ? item.recipe : ''}
            {item.preparation ? item.preparation : ''}
          </div>
        )}
        {item.source || item.reference ? (
          <p className="text-xs text-slate-400">📖 {item.source || item.reference}</p>
        ) : null}
        {item.tags && item.tags.length > 0 ? (
          <div className="flex gap-1 flex-wrap">
            {item.tags.map((t, j) => (
              <span key={j} className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded">{t}</span>
            ))}
          </div>
        ) : null}
      </div>
    );
  });
}
