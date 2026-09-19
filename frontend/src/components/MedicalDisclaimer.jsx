import { useState } from 'react';

/**
 * Medical Disclaimer Component
 * Required at feature level per Apple App Store Review Guidelines 1.4.1
 * and EU MDR requirements for wellness apps.
 *
 * Usage: <MedicalDisclaimer />
 * Renders a dismissable banner at the top of health-related pages.
 * State persists in sessionStorage so it doesn't nag on every page load.
 */
export default function MedicalDisclaimer({
  text = '本页面提供的信息仅供参考和一般健康参考，不构成医疗诊断、治疗建议或处方。如有健康问题，请咨询专业医生。',
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
            This information is for general wellness reference only and does not constitute medical advice, diagnosis, or treatment. Please consult a qualified healthcare professional for personal medical questions.
          </p>
        )}
      </div>
      {dismissable && (
        <button
          onClick={onDismiss}
          className="text-amber-600 hover:text-amber-800 shrink-0 text-lg leading-none"
          aria-label="Dismiss disclaimer"
        >
          ✕
        </button>
      )}
    </div>
  );
}
