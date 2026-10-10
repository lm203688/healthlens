/**
 * TrendChart — 多序列折线/面积趋势图（零依赖纯 SVG）
 * 用于把 wellness_simulator 的周步推演轨迹（projection.trajectory[].scores）
 * 叠加成一张「八轴信号演化」曲线图。
 *
 * props:
 *  - series: [{ key: string, label: string, color: string, points: number[] }]
 *  - xLabels: string[]        （可选，x 轴刻度标签，默认按索引）
 *  - height: number
 *  - yMin / yMax: number      （默认 0-100）
 */
import { useTranslation } from 'react-i18next';

export default function TrendChart({ series = [], xLabels = null, height = 220, yMin = 0, yMax = 100, width = 640 }) {
  const { t } = useTranslation();
  if (!series.length) return null;
  const n = Math.max(...series.map((s) => s.points.length), 0);
  if (n < 2) return <p className="text-xs text-slate-400">{t('viz.needTwoPoints')}</p>;

  const padL = 36, padR = 12, padT = 12, padB = 24;
  const w = width, h = height;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const xOf = (i) => padL + (i / (n - 1)) * plotW;
  const yOf = (v) => padT + (1 - (v - yMin) / (yMax - yMin)) * plotH;

  const yTicks = [yMin, (yMin + yMax) / 2, yMax];
  const visibleSeries = series.filter((s) => s.points && s.points.length >= 2);

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t('viz.trendAria')} className="overflow-visible">
        {/* y 网格 + 刻度 */}
        {yTicks.map((yt, i) => (
          <g key={i}>
            <line x1={padL} y1={yOf(yt)} x2={w - padR} y2={yOf(yt)} stroke="#eef2f7" strokeWidth="1" />
            <text x={padL - 6} y={yOf(yt)} textAnchor="end" dominantBaseline="middle" fontSize="10" fill="#94a3b8">
              {Math.round(yt)}
            </text>
          </g>
        ))}
        {/* x 轴标签 */}
        {xLabels &&
          xLabels.map((xl, i) => (
            <text key={i} x={xOf(i)} y={h - 8} textAnchor="middle" fontSize="10" fill="#94a3b8">
              {xl}
            </text>
          ))}
        {/* 序列折线 */}
        {visibleSeries.map((s) => {
          const d = s.points
            .map((v, i) => `${i === 0 ? 'M' : 'L'}${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`)
            .join(' ');
          return (
            <path
              key={s.key}
              d={d}
              fill="none"
              stroke={s.color || '#10b981'}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}
      </svg>
      {/* 图例 */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-slate-600">
        {visibleSeries.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-1 rounded" style={{ background: s.color || '#10b981' }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
