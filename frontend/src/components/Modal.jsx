import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

/** 轻量受控弹窗。用法：<Modal open={open} title="..." onClose={...}>内容</Modal>
 * 点击遮罩或按 Esc 关闭；打开时锁定背景滚动。 */
export default function Modal({ open, title, onClose, children, maxWidth = 'max-w-lg' }) {
  const { t } = useTranslation();
  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) {
      if (e.key === 'Escape') onClose?.();
    }
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4 py-10"
      onClick={onClose}
    >
      <div
        className={`w-full ${maxWidth} max-h-[85vh] overflow-y-auto bg-white rounded-2xl shadow-xl`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 sticky top-0 bg-white rounded-t-2xl">
          <h3 className="font-semibold text-slate-800">{title}</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 text-xl leading-none"
            aria-label={t('modal.close')}
          >
            ✕
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}
