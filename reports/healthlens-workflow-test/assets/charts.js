(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var danger = style.getPropertyValue('--danger').trim();
  var success = style.getPropertyValue('--success').trim();
  var warning = style.getPropertyValue('--warning').trim();

  // Chart 1: Module pass rate radar
  var chart1 = echarts.init(document.getElementById('chart-radar'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    tooltip: { trigger: 'item', appendToBody: true },
    radar: {
      indicator: [
        { name: '认证', max: 100 },
        { name: '健康档案', max: 100 },
        { name: '健康数据', max: 100 },
        { name: '中医体质', max: 100 },
        { name: '健康目标', max: 100 },
        { name: '仪表盘/修复', max: 100 },
        { name: '通知反馈', max: 100 },
        { name: '报告', max: 100 }
      ],
      shape: 'polygon',
      radius: '65%',
      axisName: { color: ink, fontSize: 12 },
      splitArea: { areaStyle: { color: ['rgba(0,0,0,0.02)', 'rgba(0,0,0,0.04)'] } },
      splitLine: { lineStyle: { color: rule } },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: [100, 100, 40, 50, 50, 0, 50, 100],
          name: '通过率',
          areaStyle: { color: accent + '30' },
          lineStyle: { color: accent },
          itemStyle: { color: accent },
          symbol: 'circle',
          symbolSize: 6
        }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // Chart 2: Issue severity distribution
  var chart2 = echarts.init(document.getElementById('chart-severity'), null, { renderer: 'svg' });
  chart2.setOption({
    animation: false,
    tooltip: { trigger: 'item', appendToBody: true, formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { color: muted, fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['42%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: bg2, borderWidth: 2 },
      label: { show: true, color: ink, fontSize: 12 },
      labelLine: { lineStyle: { color: rule } },
      data: [
        { value: 3, name: '严重 (500错误)', itemStyle: { color: danger } },
        { value: 8, name: '接口字段不匹配 (422)', itemStyle: { color: warning } },
        { value: 1, name: '功能缺陷 (401)', itemStyle: { color: '#e67e22' } },
        { value: 6, name: '正常通过', itemStyle: { color: success } }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // Chart 3: Issue category breakdown
  var chart3 = echarts.init(document.getElementById('chart-categories'), null, { renderer: 'svg' });
  chart3.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    grid: { left: 120, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'value', max: 5, axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule, type: 'dashed' } } },
    yAxis: {
      type: 'category',
      data: ['数据库表缺失', '时区混用', '字段名不匹配', '接口设计缺陷', '密码错误格式', '认证缺陷', 'Swagger文档'],
      axisLabel: { color: ink, fontSize: 11 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 3, itemStyle: { color: danger } },
        { value: 2, itemStyle: { color: danger } },
        { value: 5, itemStyle: { color: warning } },
        { value: 2, itemStyle: { color: warning } },
        { value: 1, itemStyle: { color: '#e67e22' } },
        { value: 1, itemStyle: { color: '#e67e22' } },
        { value: 1, itemStyle: { color: '#3498db' } }
      ],
      barWidth: 18,
      itemStyle: { borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: ink, fontSize: 12, formatter: '{c}个' }
    }]
  });
  window.addEventListener('resize', function() { chart3.resize(); });
})();
