/**
 * AxisRadar — 八轴稳态雷达图（零依赖纯 SVG）
 * 用于把 fusion_engine 的 8 轴评分（0-100）一次性可视化，
 * 直观呈现「短板轴」与整体稳态轮廓。
 *
 * props:
 *  - scores: { A: number, B: number, ... }  （缺失轴按 0 处理）
 *  - colors: { A: '#hex', ... }              （可选，缺省用渐变灰）
 *  - size:    number                        （画布边长，默认 300）
 *  - max:     number                        （评分上限，默认 100）
 */
import { useTranslation } from 'react-i18next';

const AXIS_ORDER = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

export default function AxisRadar({ scores = {}, colors = {}, size = 300, max = 100 }) {
  const { t } = useTranslation();
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 42; // 留出标签空间
  const n = AXIS_ORDER.length;

  // 第 i 个轴的角度：从正上方开始，顺时针
  const angleOf = (i) => (-90 + (360 / n) * i) * (Math.PI / 180);
  const pointAt = (i, r) => [cx + r * Math.cos(angleOf(i)), cy + r * Math.sin(angleOf(i))];

  const rings = [0.25, 0.5, 0.75, 1];
  const dataPts = AXIS_ORDER.map((ax, i) => {
    const v = Math.max(0, Math.min(max, Number(scores?.[ax]) || 0));
    return pointAt(i, (v / max) * radius);
  });
  const dataPath = dataPts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ') + ' Z';

  const hasData = AXIS_ORDER.some((ax) => (scores?.[ax] ?? 0) > 0);

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} role="img" aria-label={t('viz.radarAria')} className="overflow-visible">
        {/* 同心网格 */}
        {rings.map((r, ri) => {
          const poly = AXIS_ORDER.map((_, i) => pointAt(i, r * radius).join(',')).join(' ');
          return <polygon key={ri} points={poly} fill="none" stroke="#e2e8f0" strokeWidth="1" />;
        })}
        {/* 轴线 + 轴标签 */}
        {AXIS_ORDER.map((ax, i) => {
          const [ex, ey] = pointAt(i, radius);
          const [lx, ly] = pointAt(i, radius + 22);
          const color = colors[ax] || '#64748b';
          return (
            <g key={ax}>
              <line x1={cx} y1={cy} x2={ex} y2={ey} stroke="#e2e8f0" strokeWidth="1" />
              <text
                x={lx} y={ly}
                textAnchor="middle" dominantBaseline="middle"
                fontSize="12" fontWeight="600" fill={color}
              >
                {ax}
              </text>
            </g>
          );
        })}
        {/* 数据多边形 */}
        {hasData && (
          <polygon points={dataPts.map((p) => p.join(',')).join(' ')} fill="rgba(16,185,129,0.18)" stroke="#10b981" strokeWidth="2" />
        )}
        {/* 数据顶点 */}
        {hasData && dataPts.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r="3" fill={colors[AXIS_ORDER[i]] || '#10b981'} />
        ))}
        {/* 中心 */}
        <circle cx={cx} cy={cy} r="2" fill="#94a3b8" />
        <title>{t('viz.radarTitle')}</title>
      </svg>
      {/* 图例：轴名 + 分值 */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-xs text-slate-600">
        {AXIS_ORDER.map((ax) => (
          <div key={ax} className="flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: colors[ax] || '#64748b' }} />
            <span className="font-medium">{ax}</span>
            <span className="text-slate-400">·</span>
            <span>{t(`axis.${ax.toLowerCase()}`)}</span>
            <span className="ml-auto font-semibold tabular-nums">{Math.round(scores?.[ax] ?? 0)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
