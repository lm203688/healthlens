import { useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('search');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [count, setCount] = useState(0);

  const endpoints = {
    search: { fn: (q) => api.knowledgeSearch(q), labelKey: 'knowledge.searchFullText', descKey: 'knowledge.descFullText' },
    food:   { fn: (q) => api.knowledgeFood(q),   labelKey: 'knowledge.searchFood', descKey: 'knowledge.descFood' },
    methods:{ fn: (q) => api.knowledgeMethods(q), labelKey: 'knowledge.searchMethods', descKey: 'knowledge.descMethods' },
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

  const placeholder = tab === 'food'
    ? t('knowledge.searchPlaceholderFood')
    : tab === 'methods' ? t('knowledge.searchPlaceholderMethods')
    : t('knowledge.searchPlaceholderFull');

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold">{t('knowledge.title')}</h2>
        <p className="text-slate-500 text-sm mt-1">{t('knowledge.subtitle')}</p>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex gap-2">
          {Object.entries(endpoints).map(([k, { labelKey, descKey }]) => (
            <button
              key={k}
              onClick={() => { setTab(k); setResults(null); setCount(0); }}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition text-center
                ${tab === k ? 'bg-emerald-100 text-emerald-800' : 'text-slate-500 hover:bg-slate-100'}`}
              title={t(descKey)}
            >
              <div>{t(labelKey)}</div>
              <div className="text-xs opacity-70 mt-0.5">{t(descKey)}</div>
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder={placeholder}
            className="flex-1 px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-emerald-400 outline-none"
          />
          <button
            onClick={search}
            disabled={loading || !query.trim()}
            className="bg-emerald-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? t('knowledge.searching') : t('knowledge.searchBtn')}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-slate-400 self-center mr-1">{t('knowledge.popularSearches')}</span>
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
      {loading && <p className="text-slate-500 text-center">{t('knowledge.searching')}</p>}

      {results && !error && !loading && (
        <div className="space-y-4">
          <div className="text-sm text-slate-500">
            {t('knowledge.resultsCount', { count })}
          </div>
          <KnowledgeCards data={results} tab={tab} />
        </div>
      )}

      {!results && !error && !loading && (
        <div className="text-center py-12 text-slate-400">
          <div className="text-4xl mb-3">📚</div>
          <p>{t('knowledge.emptyHint')}</p>
        </div>
      )}
    </div>
  );
}

function KnowledgeCards({ data, tab }) {
  const { t } = useTranslation();
  const items = data.results || data.items || data.data || (Array.isArray(data) ? data : [data]);
  if (!Array.isArray(items)) return <div className="bg-slate-50 p-3 rounded-lg text-sm text-slate-600">{JSON.stringify(data, null, 2)}</div>;

  if (items.length === 0) return <p className="text-slate-500 text-center py-8">{t('knowledge.noResults')}</p>;

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
            <span className="font-medium">{t('knowledge.usageLabel')}</span>
            {item.ingredients ? `${t('knowledge.ingredientsLabel')}${item.ingredients.join('、')}` : ''}
            {item.recipe ? item.recipe : ''}
            {item.preparation ? item.preparation : ''}
          </div>
        )}
        {item.source || item.reference ? (
          <p className="text-xs text-slate-400">📖 {t('knowledge.sourceLabel')}: {item.source || item.reference}</p>
        ) : null}
        {item.tags && item.tags.length > 0 ? (
          <div className="flex gap-1 flex-wrap">
            {item.tags.map((tag, j) => (
              <span key={j} className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded">{tag}</span>
            ))}
          </div>
        ) : null}
      </div>
    );
  });
}
