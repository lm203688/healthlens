/** i18n 初始化 — react-i18next 配置
 *
 * 支持语言：中文（zh）、英文（en）
 * 持久化：localStorage，key = 'hl_lang'
 * 默认：跟随浏览器语言，无则中文
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zh from './locales/zh.json';
import en from './locales/en.json';

const stored = localStorage.getItem('hl_lang');
const browserLang = (navigator.language || 'zh').toLowerCase().startsWith('zh') ? 'zh' : 'en';
const defaultLang = stored || browserLang;

i18n.use(initReactI18next).init({
  resources: {
    zh: { translation: zh },
    en: { translation: en },
  },
  lng: defaultLang,
  fallbackLng: 'zh',
  interpolation: { escapeValue: false },
  returnEmptyString: false,
});

export function setLocale(lang) {
  i18n.changeLanguage(lang);
  localStorage.setItem('hl_lang', lang);
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
}

export function getLocale() {
  return i18n.language;
}

export default i18n;
