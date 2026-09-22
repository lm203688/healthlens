import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function HealthDisclaimer({
  text,
  dismissable = true,
  compact = false,
}) {
  const { t } = useTranslation();
  const displayText = text || t('disclaimer.defaultText');
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
        <p className="text-amber-800 leading-relaxed">{displayText}</p>
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
          aria-label={t('disclaimer.closeHint')}
        >
          ✕
        </button>
      )}
    </div>
  );
}