(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var danger = style.getPropertyValue('--danger').trim();
  var warning = style.getPropertyValue('--warning').trim();
  var success = style.getPropertyValue('--success').trim();

  // --- Chart: 健康评分雷达图 ---
  var radar = echarts.init(document.getElementById('chart-radar'), null, { renderer: 'svg' });
  radar.setOption({
    animation: false,
    tooltip: { appendToBody: true, trigger: 'item' },
    radar: {
      indicator: [
        { name: '外网服务', max: 100 },
        { name: '代码质量', max: 100 },
        { name: '安全合规', max: 100 },
        { name: 'CI/CD', max: 100 },
        { name: '依赖管理', max: 100 },
        { name: '日志健康', max: 100 }
      ],
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: muted, fontSize: 12 },
      splitLine: { lineStyle: { color: rule } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      data: [{
        value: [10, 35, 40, 45, 35, 60],
        name: '当前评分',
        areaStyle: { color: accent + '33' },
        lineStyle: { color: accent, width: 2 },
        itemStyle: { color: accent }
      }]
    }]
  });
  window.addEventListener('resize', function() { radar.resize(); });

  // --- Chart: 问题严重程度分布 ---
  var severity = echarts.init(document.getElementById('chart-severity'), null, { renderer: 'svg' });
  severity.setOption({
    animation: false,
    tooltip: { appendToBody: true, trigger: 'item', formatter: '{b}: {c} 项 ({d}%)' },
    legend: { bottom: 0, textStyle: { color: muted, fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: bg2, borderWidth: 2 },
      label: { show: true, color: ink, formatter: '{b}\n{c} 项' },
      data: [
        { value: 5, name: '严重', itemStyle: { color: danger } },
        { value: 5, name: '警告', itemStyle: { color: warning } },
        { value: 5, name: '建议', itemStyle: { color: accent2 } }
      ]
    }]
  });
  window.addEventListener('resize', function() { severity.resize(); });

  // --- Chart: 日志错误趋势 ---
  var logTrend = echarts.init(document.getElementById('chart-log-trend'), null, { renderer: 'svg' });
  logTrend.setOption({
    animation: false,
    tooltip: { appendToBody: true, trigger: 'axis' },
    grid: { top: 30, right: 20, bottom: 30, left: 40 },
    xAxis: {
      type: 'category',
      data: ['7月20日', '7月21日', '7月22日'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted }
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 7, itemStyle: { color: danger } },
        { value: 3, itemStyle: { color: warning } },
        { value: 2, itemStyle: { color: warning } }
      ],
      barWidth: '40%',
      label: { show: true, position: 'top', color: ink, formatter: '{c} errors' }
    }]
  });
  window.addEventListener('resize', function() { logTrend.resize(); });
})();
