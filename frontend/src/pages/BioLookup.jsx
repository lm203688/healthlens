/** 文献与结构查询 — RCSB PDB / PubChem / UniProt / AlphaFold
 *
 * 设计原则（与后端契约对齐）：
 *  - 后端错误是结构化的 {code, detail}，这里按 code 给不同提示，不做字符串匹配；
 *  - AlphaFold 结果必须显式标注"预测、非实验证据"，不能与 PDB 混为一谈；
 *  - 查无此项显示"未收录"，不显示空表格冒充成功。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

const TABS = [
  { key: 'target', icon: '🎯', labelKey: 'bio.tabTarget' },
  { key: 'structure', icon: '🧬', labelKey: 'bio.tabStructure' },
  { key: 'compound', icon: '⚗️', labelKey: 'bio.tabCompound' },
];

export default function BioLookup() {
  const { t } = useTranslation();
  const [tab, setTab] = useState('target');

  return (
    <div className="max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold text-slate-800">🔬 {t('bio.title')}</h2>
      <p className="text-slate-500 mt-1 text-sm">{t('bio.subtitle')}</p>

      <div className="flex gap-2 mt-5 mb-4">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition border ${
              tab === item.key
                ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm'
                : 'bg-white text-slate-600 border-slate-200 hover:border-emerald-300'
            }`}
          >
            {item.icon} {t(item.labelKey)}
          </button>
        ))}
      </div>

      {tab === 'target' && <TargetPanel />}
      {tab === 'structure' && <StructurePanel />}
      {tab === 'compound' && <CompoundPanel />}

      <p className="text-xs text-slate-400 mt-8 leading-relaxed">
        {t('bio.footerNote')}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 通用部件                                                             */
/* ------------------------------------------------------------------ */

function ErrorBox({ error }) {
  const { t } = useTranslation();
  if (!error) return null;
  return (
    <div className="card p-4 border-amber-200 bg-amber-50 mt-4">
      <p className="text-sm font-medium text-amber-800">
        ⚠️ {error.message || t('bio.errorGeneric')}
      </p>
      <p className="text-xs text-amber-700 mt-1 break-all">
        <span className="font-mono">[{error.code}]</span> {error.detail}
      </p>
    </div>
  );
}

function SearchBar({ value, onChange, onSubmit, placeholder, loading, buttonKey }) {
  const { t } = useTranslation();
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <input
        className="input-base flex-1"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      <button type="submit" className="btn-primary px-6" disabled={loading || !value.trim()}>
        {loading ? t('bio.searching') : t(buttonKey)}
      </button>
    </form>
  );
}

async function parseResponse(resp) {
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = body?.detail;
    if (detail && typeof detail === 'object') throw detail;
    throw { code: 'http_' + resp.status, detail: JSON.stringify(body).slice(0, 200) };
  }
  return body.data;
}

/* ------------------------------------------------------------------ */
/* 靶点全景                                                             */
/* ------------------------------------------------------------------ */

function TargetPanel() {
  const { t } = useTranslation();
  const [gene, setGene] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function search() {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      setData(await parseResponse(await api.bioTarget(gene.trim(), 8)));
    } catch (e) {
      setError(e);
    }
    setLoading(false);
  }

  const protein = data?.protein;
  const structures = data?.experimental_structures;
  const predicted = data?.predicted_structure;

  return (
    <div>
      <SearchBar
        value={gene}
        onChange={setGene}
        onSubmit={search}
        placeholder={t('bio.genePlaceholder')}
        loading={loading}
        buttonKey="bio.search"
      />
      <ErrorBox error={error} />

      {protein && (
        <div className="card p-5 mt-4">
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="text-lg font-semibold text-slate-800">{protein.protein_name}</span>
            <span className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-mono">
              {protein.accession}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            {protein.organisms || protein.organism} · {protein.length} aa
            {protein.genes?.length ? ` · ${protein.genes.join(', ')}` : ''}
          </p>
        </div>
      )}

      {structures?.ok && (
        <div className="card p-5 mt-4">
          <h3 className="font-semibold text-slate-800 mb-1">
            🧬 {t('bio.experimentalStructures')}
            <span className="text-sm font-normal text-slate-500 ml-2">
              {structures.data.total_count}
            </span>
          </h3>
          <p className="text-xs text-slate-400 mb-3">{t('bio.experimentalNote')}</p>
          {structures.data.details?.length > 0 ? (
            <ul className="space-y-2">
              {structures.data.details.map((s) => (
                <li key={s.pdb_id} className="flex items-start gap-2 text-sm">
                  <a
                    href={s.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-emerald-700 hover:underline shrink-0"
                  >
                    {s.pdb_id}
                  </a>
                  <span className="text-slate-600 flex-1">{s.title}</span>
                  <span className="text-xs text-slate-400 shrink-0">
                    {s.experimental_methods?.[0]} · {s.resolution_angstrom ?? '—'} Å
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">{t('bio.noStructures')}</p>
          )}
        </div>
      )}

      {structures && !structures.ok && (
        <ErrorBox error={structures.error} />
      )}

      {predicted?.ok && predicted.data.best_model && (
        <div className="card p-5 mt-4 border-blue-200 bg-blue-50/40">
          <h3 className="font-semibold text-slate-800 mb-1">
            🔮 {t('bio.predictedStructure')}
            <span className="text-xs font-normal ml-2 px-2 py-0.5 rounded bg-blue-100 text-blue-700">
              {t('bio.predictedBadge')}
            </span>
          </h3>
          <p className="text-sm text-slate-600 mt-1">
            {predicted.data.best_model.entry_id} · pLDDT{' '}
            <span className="font-medium">{predicted.data.best_model.plddt}</span> (
            {predicted.data.best_model.plddt_band})
          </p>
          <p className="text-xs text-slate-500 mt-1">{predicted.data.best_model.plddt_note}</p>
          <p className="text-xs text-slate-400 mt-2">{predicted.data.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* PDB 结构                                                             */
/* ------------------------------------------------------------------ */

function StructurePanel() {
  const { t } = useTranslation();
  const [pdbId, setPdbId] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function search() {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      setData(await parseResponse(await api.bioPdb(pdbId.trim())));
    } catch (e) {
      setError(e);
    }
    setLoading(false);
  }

  return (
    <div>
      <SearchBar
        value={pdbId}
        onChange={setPdbId}
        onSubmit={search}
        placeholder={t('bio.pdbPlaceholder')}
        loading={loading}
        buttonKey="bio.search"
      />
      <ErrorBox error={error} />

      {data && (
        <>
          <div className="card p-5 mt-4">
            <h3 className="font-semibold text-slate-800">{data.title}</h3>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-600 mt-2">
              <span>PDB <span className="font-mono">{data.pdb_id}</span></span>
              <span>{data.experimental_methods?.join(' / ')}</span>
              {data.resolution_angstrom && <span>{data.resolution_angstrom} Å</span>}
              {data.molecular_weight_kda && <span>{data.molecular_weight_kda} kDa</span>}
              {data.released_at && <span>{String(data.released_at).slice(0, 10)}</span>}
            </div>
            {data.authors?.length > 0 && (
              <p className="text-xs text-slate-400 mt-2">{data.authors.slice(0, 6).join(', ')}</p>
            )}
          </div>

          {data.polymer_entities?.length > 0 && (
            <div className="card p-5 mt-4">
              <h4 className="font-medium text-slate-800 mb-2">
                {t('bio.polymerEntities')}（{data.polymer_entities.length}）
              </h4>
              <ul className="space-y-1.5 text-sm">
                {data.polymer_entities.map((p) => (
                  <li key={p.entity_id} className="flex flex-wrap gap-x-2">
                    <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                      {p.chains.join(',')}
                    </span>
                    <span className="text-slate-700">{p.description}</span>
                    <span className="text-slate-400 text-xs">
                      {p.length} aa · {p.organisms?.map((o) => o.scientific_name).join(' / ')}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.ligands?.length > 0 && (
            <div className="card p-5 mt-4">
              <h4 className="font-medium text-slate-800 mb-2">
                {t('bio.ligands')}（{data.ligands.length}）
              </h4>
              <div className="flex flex-wrap gap-2">
                {data.ligands.map((l) => (
                  <span
                    key={l.entity_id}
                    className="px-2 py-1 rounded bg-amber-50 border border-amber-200 text-xs text-amber-800"
                    title={l.formula || ''}
                  >
                    <span className="font-mono font-medium">{l.comp_id}</span> {l.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 化合物                                                               */
/* ------------------------------------------------------------------ */

function CompoundPanel() {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function search() {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      setData(await parseResponse(await api.bioCompound(query.trim())));
    } catch (e) {
      setError(e);
    }
    setLoading(false);
  }

  const c = data?.compound;

  return (
    <div>
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={search}
        placeholder={t('bio.compoundPlaceholder')}
        loading={loading}
        buttonKey="bio.search"
      />
      <ErrorBox error={error} />

      {c && (
        <>
          <div className="card p-5 mt-4">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-lg font-semibold text-slate-800">{c.iupac_name || data.query}</span>
              <a
                href={c.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-mono"
              >
                CID {c.cid}
              </a>
            </div>
            {data.ambiguous && (
              <p className="text-xs text-amber-700 mt-1">
                {t('bio.ambiguous')}：{data.all_cids.slice(0, 5).join(', ')}
              </p>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              <Stat label={t('bio.formula')} value={c.molecular_formula} />
              <Stat label={t('bio.mw')} value={c.molecular_weight} />
              <Stat label="XLogP" value={c.xlogp} />
              <Stat label="TPSA" value={c.tpsa} />
              <Stat label="HBD" value={c.h_bond_donors} />
              <Stat label="HBA" value={c.h_bond_acceptors} />
              <Stat label={t('bio.rotatable')} value={c.rotatable_bonds} />
              <Stat label={t('bio.heavyAtoms')} value={c.heavy_atoms} />
            </div>
            <p className="text-xs text-slate-400 mt-3">{c.property_note}</p>
          </div>

          {data.cas_numbers?.length > 0 && (
            <div className="card p-5 mt-4">
              <h4 className="font-medium text-slate-800 mb-2">CAS</h4>
              <div className="flex flex-wrap gap-2">
                {data.cas_numbers.map((n) => (
                  <span key={n} className="px-2 py-1 rounded bg-slate-100 text-xs font-mono text-slate-700">
                    {n}
                  </span>
                ))}
              </div>
            </div>
          )}

          {data.synonyms?.length > 0 && (
            <details className="card p-5 mt-4">
              <summary className="cursor-pointer font-medium text-slate-800">
                {t('bio.synonyms')}（{data.synonyms.length}）
              </summary>
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                {data.synonyms.join(' · ')}
              </p>
            </details>
          )}

          {c.canonical_smiles && (
            <div className="card p-5 mt-4">
              <h4 className="font-medium text-slate-800 mb-2">SMILES</h4>
              <code className="text-xs break-all text-slate-600">{c.canonical_smiles}</code>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-lg px-3 py-2">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-sm font-medium text-slate-800 break-all">{value ?? '—'}</p>
    </div>
  );
}