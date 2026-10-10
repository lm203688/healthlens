/**
 * CheckinHeatmap — 打卡/依从日历热力图（零依赖纯 SVG）
 * 用于留存模块把「每日依从 / 打卡」强度以 GitHub 式热力图呈现，
 * 给用户一个直观的「坚持度」视觉反馈。
 *
 * props:
 *  - data:   [{ date: 'YYYY-MM-DD', value: number(0-1) }]
 *  - weeks:  number   （展示最近多少周，默认 12）
 *  - color:  string   （基色，默认 emerald）
 */
import { useTranslation } from 'react-i18next';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function parseDate(s) {
  // 兼容 YYYY-MM-DD 与 ISO 串
  const d = new Date(s.length > 10 ? s.slice(0, 10) : s + 'T00:00:00');
  return isNaN(d) ? null : d;
}

export default function CheckinHeatmap({ data = [], weeks = 12, color = '#10b981' }) {
  const { t } = useTranslation();
  const map = {};
  data.forEach((d) => { map[d.date] = Math.max(0, Math.min(1, Number(d.value) || 0)); });

  // 以今天为右端，向前铺 weeks*7 天
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const totalDays = weeks * 7;
  const start = new Date(today);
  start.setDate(start.getDate() - (totalDays - 1));

  // 对齐到周一开头
  const startDow = (start.getDay() + 6) % 7; // 0=Mon
  const gridStart = new Date(start);
  gridStart.setDate(gridStart.getDate() - startDow);

  const cells = [];
  const cursor = new Date(gridStart);
  for (let i = 0; i < weeks * 7 + 7; i++) {
    const key = cursor.toISOString().slice(0, 10);
    const inRange = cursor >= start && cursor <= today;
    cells.push({
      key,
      date: cursor,
      inRange,
      value: map[key] ?? (inRange ? 0 : null),
      col: Math.floor((i + startDow) / 7),
      row: (i + startDow) % 7,
    });
    cursor.setDate(cursor.getDate() + 1);
  }

  const cell = 13, gap = 3, padL = 26, padT = 16;
  const cols = Math.ceil((cells.length - startDow) / 7);
  const svgW = padL + cols * (cell + gap) + 4;
  const svgH = padT + 7 * (cell + gap) + 4;
  const shade = (v) => {
    if (v === null) return 'transparent';
    if (v <= 0) return '#f1f5f9';
    // 透明度随强度
    const alpha = 0.25 + 0.75 * v;
    return color + Math.round(alpha * 255).toString(16).padStart(2, '0');
  };

  return (
    <div className="overflow-x-auto">
      <svg width={svgW} height={svgH} role="img" aria-label={t('viz.heatmapAria')}>
        {WEEKDAYS.map((wd, r) => (
          <text key={wd} x={padL - 4} y={padT + r * (cell + gap) + cell - 2} textAnchor="end" fontSize="9" fill="#94a3b8">
            {wd}
          </text>
        ))}
        {cells.map((c) => {
          if (!c.date) return null;
          const x = padL + c.col * (cell + gap);
          const y = padT + c.row * (cell + gap);
          return (
            <rect
              key={c.key}
              x={x} y={y} width={cell} height={cell} rx="2"
              fill={shade(c.value)}
              stroke={c.inRange ? '#e2e8f0' : 'transparent'}
              strokeWidth="0.5"
            >
              <title>{`${c.key}: ${c.value === null ? '—' : Math.round(c.value * 100) + '%'}`}</title>
            </rect>
          );
        })}
      </svg>
      <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
        <span>{t('viz.less')}</span>
        <span className="inline-block w-3 h-3 rounded-sm" style={{ background: '#f1f5f9' }} />
        <span className="inline-block w-3 h-3 rounded-sm" style={{ background: shade(0.4) }} />
        <span className="inline-block w-3 h-3 rounded-sm" style={{ background: shade(0.7) }} />
        <span className="inline-block w-3 h-3 rounded-sm" style={{ background: shade(1) }} />
        <span>{t('viz.more')}</span>
      </div>
    </div>
  );
}
