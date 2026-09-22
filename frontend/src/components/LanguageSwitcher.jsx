/** 语言切换器 — 中文/英文切换，持久化到 localStorage */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import i18n, { setLocale } from '../i18n';

export default function LanguageSwitcher({ className = '' }) {
  const { i18n: i18nInstance } = useTranslation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (!e.target.closest('[data-lang-switch]')) setOpen(false); };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [open]);

  const locales = [
    { code: 'zh', label: '中文', flag: '🇨🇳' },
    { code: 'en', label: 'English', flag: '🇺🇸' },
  ];

  const current = locales.find(l => l.code === i18nInstance.language) || locales[0];

  function switchLocale(code) {
    setLocale(code);
    setOpen(false);
  }

  return (
    <div className={`relative ${className}`} data-lang-switch>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className="flex items-center gap-1 px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition"
        aria-label={i18nInstance.t('nav.language')}
      >
        <span>{current.flag}</span>
        <svg className="w-3 h-3 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-40 bg-white rounded-xl shadow-lg border border-slate-100 py-1 z-50">
          {locales.map((l) => (
            <button
              key={l.code}
              onClick={(e) => { e.stopPropagation(); switchLocale(l.code); }}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-slate-50 transition ${
                l.code === i18nInstance.language ? 'text-emerald-600 font-medium' : 'text-slate-600'
              }`}
            >
              <span>{l.flag}</span>
              <span>{l.label}</span>
              {l.code === i18nInstance.language && (
                <svg className="w-4 h-4 ml-auto text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
