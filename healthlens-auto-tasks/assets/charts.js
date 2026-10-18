/* HealthLens Auto Tasks - Gantt Chart */
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();

  var dom = document.getElementById('gantt-chart');
  if (!dom) return;
  var chart = echarts.init(dom, null, { renderer: 'canvas' });

  var phases = [
    'Layer 1: 项目运维',
    '数据库积累',
    'Layer 2: 情报洞察',
    'Layer 3: 推广营销',
    '符合性核对',
    '业务闭环',
    '资金闭环',
    '用户教育'
  ];

  var tasks = {
    'Layer 1: 项目运维': [
      { name: '服务器健康检查 + 告警推送', start: 0, end: 1 },
      { name: 'SSL证书自动续期 + 数据库备份', start: 0, end: 1 },
      { name: '安全漏洞扫描 + 访问日志检测', start: 0.5, end: 1.5 },
      { name: 'pre-commit + CI测试 + 覆盖率门禁', start: 0, end: 2 },
      { name: '自动部署 + Release Notes', start: 0.5, end: 1.5 },
      { name: '医疗用语自动扫描 (CI)', start: 0, end: 1 },
      { name: '性能基准测试 (locust)', start: 2, end: 4 },
      { name: '新功能上线影响追踪(全自动)', start: 2, end: 4 }
    ],
    '数据库积累': [
      { name: '免费数据库抓取+增量同步', start: 1, end: 3 },
      { name: '用户数据匿名化积累', start: 2, end: 4 },
      { name: '数据库质量维护+版本管理', start: 1.5, end: 4 },
      { name: '统一查询接口(SQL+向量)', start: 2, end: 4 },
      { name: '数据资产月度报告', start: 3, end: 12 }
    ],
    'Layer 2: 情报洞察': [
      { name: '健康领域前沿跟踪(8领域)', start: 2, end: 6 },
      { name: '新功能研判报告(>=2来源)', start: 4, end: 12 },
      { name: 'Agent架构能力跟踪(8维度)', start: 3, end: 6 },
      { name: 'Agent能力演进周报', start: 4, end: 12 },
      { name: '竞品与市场动态监控', start: 2, end: 6 },
      { name: '用户反馈与需求信号分析', start: 2, end: 6 }
    ],
    'Layer 3: 推广营销': [
      { name: 'SEO内容工厂+四维矩阵', start: 2, end: 4.5 },
      { name: 'Sitemap+Schema+索引提交', start: 2, end: 3 },
      { name: 'AI引用监控+SEO流量分析', start: 4, end: 7 },
      { name: '转化漏斗+CAC/LTV监控', start: 5, end: 8 },
      { name: '定价A/B测试+限时活动', start: 6, end: 9 },
      { name: '推广策略自动迭代', start: 8, end: 12 },
      { name: '推广技术追踪+评估纳入', start: 4, end: 6 },
      { name: '推广技术月报', start: 5, end: 12 }
    ],
    '符合性核对': [
      { name: '新功能上线符合性核对', start: 3, end: 12 },
      { name: '情报建议上马门禁', start: 4, end: 12 },
      { name: '推广策略符合性检查', start: 5, end: 12 }
    ],
    '业务闭环': [
      { name: '首体验优化+留存率追踪', start: 2, end: 4 },
      { name: '沉默用户唤醒+裂变自动化', start: 3, end: 5 },
      { name: '分析流程监控+效果追踪', start: 2, end: 4 },
      { name: '支付全链路监控+失败重试', start: 3, end: 5 }
    ],
    '资金闭环': [
      { name: '收支自动核算+成本预警', start: 4, end: 6 },
      { name: '单位经济效益+再投资规划', start: 8, end: 12 },
      { name: '基础设施采购提醒(需人工)', start: 4, end: 12 }
    ],
    '用户教育': [
      { name: '典型案例提取+内容生产', start: 5, end: 8 },
      { name: 'SEO教育内容+7天推送序列', start: 5, end: 9 },
      { name: '每周健康知识H5页面', start: 5, end: 12 },
      { name: '月度健康改善报告', start: 6, end: 12 }
    ]
  };

  var phaseColors = {
    'Layer 1: 项目运维':       { bar: '#10b981', bg: 'rgba(16,185,129,0.12)' },
    '数据库积累':              { bar: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
    'Layer 2: 情报洞察':       { bar: '#8b5cf6', bg: 'rgba(139,92,246,0.12)' },
    'Layer 3: 推广营销':       { bar: '#f97316', bg: 'rgba(249,115,22,0.12)' },
    '符合性核对':              { bar: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
    '业务闭环':                { bar: '#0ea5e9', bg: 'rgba(14,165,233,0.12)' },
    '资金闭环':                { bar: '#06b6d4', bg: 'rgba(6,182,212,0.12)' },
    '用户教育':                { bar: '#ec4899', bg: 'rgba(236,72,153,0.12)' }
  };

  var seriesData = [];
  var yAxisData = [];

  phases.forEach(function(phase) {
    var phaseTasks = tasks[phase];
    phaseTasks.forEach(function(task, i) {
      var rowLabel = i === 0 ? phase : '';
      yAxisData.push(rowLabel);
      seriesData.push({
        name: task.name,
        value: [task.start, task.end, phase],
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: phaseColors[phase].bar + 'aa' },
            { offset: 1, color: phaseColors[phase].bar }
          ]),
          borderRadius: [3, 3, 3, 3]
        }
      });
    });
  });

  var markLines = [];
  for (var w = 0; w <= 12; w += 2) {
    markLines.push({
      xAxis: w,
      label: { show: true, formatter: 'W' + w, color: '#94a3b8', fontSize: 10 },
      lineStyle: { color: 'rgba(255,255,255,0.06)', type: 'dashed' }
    });
  }

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15,23,42,0.95)',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#f1f5f9', fontSize: 12 },
      formatter: function(p) {
        var d = p.data.value;
        var s = Math.ceil(d[0]);
        var e = Math.ceil(d[1]);
        return '<b>' + p.data.name + '</b><br/>' +
               d[2] + '<br/>第' + s + '周 ~ 第' + e + '周';
      }
    },
    grid: { left: 220, right: 40, top: 20, bottom: 40 },
    xAxis: {
      type: 'value', min: 0, max: 12,
      name: '周',
      nameTextStyle: { color: '#94a3b8', fontSize: 11 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 10, formatter: function(v) { return 'W' + v; } },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }
    },
    yAxis: {
      type: 'category', data: yAxisData, inverse: true,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        color: function(value, index) {
          var label = yAxisData[index];
          if (!label) return 'transparent';
          var offset = 0;
          for (var p = 0; p < phases.length; p++) {
            if (index >= offset && index < offset + tasks[phases[p]].length) {
              return phaseColors[phases[p]].bar;
            }
            offset += tasks[phases[p]].length;
          }
          return '#94a3b8';
        },
        fontSize: 11, fontWeight: 'bold',
        formatter: function(value) { return value || ''; }
      }
    },
    series: [{
      type: 'custom',
      renderItem: function(params, api) {
        var catIdx = api.value(0);
        var start = api.coord([api.value(1), catIdx]);
        var end = api.coord([api.value(2), catIdx]);
        var height = api.size([0, 1])[1] * 0.5;
        var shape = echarts.graphic.clipRectByRect(
          { x: start[0], y: start[1] - height / 2, width: end[0] - start[0], height: height },
          { x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height }
        );
        return shape && { type: 'rect', transition: ['shape'], shape: shape, style: api.style() };
      },
      encode: { x: [1, 2], y: 0 },
      data: seriesData.map(function(item) {
        var offset = 0;
        for (var p = 0; p < phases.length; p++) {
          if (item.value[2] === phases[p]) break;
          offset += tasks[phases[p]].length;
        }
        var rowOffset = offset + tasks[item.value[2]].findIndex(function(t) { return t.name === item.name; });
        return { value: [rowOffset, item.value[0], item.value[1]], name: item.name, itemStyle: item.itemStyle };
      }),
      markLine: { silent: true, symbol: 'none', data: markLines }
    }]
  });

  window.addEventListener('resize', function() { chart.resize(); });
})();