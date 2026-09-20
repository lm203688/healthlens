import { useState } from 'react';

/**
 * Health Disclaimer Component
 * 健康管理类应用所需的免责提示（参考 Apple App Store Review Guidelines 1.4.1
 * 与 EU MDR 对 wellness app 的要求）。
 *
 * 定位说明：HealthLens 为健康管理（wellness）工具，提供养生参考，
 * 不提供医疗诊断、治疗或处方。如有具体健康问题请咨询专业医师。
 *
 * 用法：<HealthDisclaimer />
 * 在健康相关页面顶部展示可关闭的提示条；
 * 关闭状态记录在 sessionStorage，避免每次切换页面都打扰用户。
 */
export default function HealthDisclaimer({
  text = '本页面提供的信息仅供健康管理与养生参考，不构成医疗诊断、治疗建议或处方。如有具体健康问题，请咨询专业医师。',
  dismissable = true,
  compact = false,
}) {
  const key = 'hl-disclaimer-dismissed';
  const [dismissed, setDismissed] = useState(() => {
    if (!dismissable) return false;
    try {
      return sessionStorage.getItem(key) === '1';
    } catch {
      return false;
    }
  });

  if (dismissed) return null;

  function onDismiss() {
    try {
      sessionStorage.setItem(key, '1');
    } catch {}
    setDismissed(true);
  }

  return (
    <div
      className={`mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 flex items-start gap-3 ${
        compact ? 'text-xs' : 'text-sm'
      }`}
      role="alert"
    >
      <span className="text-amber-600 mt-0.5 shrink-0">⚠️</span>
      <div className="flex-1 min-w-0">
        <p className="text-amber-800 leading-relaxed">{text}</p>
        {!compact && (
          <p className="text-amber-600 text-xs mt-1">
            This information is provided for general wellness reference only and does not constitute medical advice, diagnosis, or treatment. Please consult a qualified healthcare professional for personal health questions.
          </p>
        )}
      </div>
      {dismissable && (
        <button
          onClick={onDismiss}
          className="text-amber-600 hover:text-amber-800 shrink-0 text-lg leading-none"
          aria-label="关闭提示"
        >
          ✕
        </button>
      )}
    </div>
  );
}
