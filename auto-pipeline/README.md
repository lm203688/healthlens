# HealthLens 闭环自动化工作流

## 概述

这是一个完整的自动化工作流系统，实现"情报收集 → 智能分析 → 决策门禁 → 开发生成 → 质量测试 → 部署上架"的完整闭环。

## 工作流阶段

```
情报收集 → 智能分析 → 决策门禁 → 开发生成 → 质量测试 → 部署上架
   ↑                                                          ↓
   └────────────────── 效果反馈 ←──────────────────────────────┘
```

### 阶段1：情报收集 (collect)
- 从多个来源收集竞品动态、技术趋势、学术进展
- 输出：intelligence_report.json
- 触发：每周一 03:00 定时触发

### 阶段2：智能分析 (analyze)
- 对收集到的情报进行评分和分类
- 评分维度：来源数量(40分) + 目标符合度(30分) + 市场验证(20分) + 技术可行性(10分)
- 输出：analysis_report.json
- 触发：收集阶段完成后自动执行

### 阶段3：决策门禁 (decide)
- 基于分析结果做出"批准/观察/放弃"决策
- 批准阈值：≥70分，观察阈值：≥50分
- 为批准项分配具体的内容/开发任务
- 输出：decision_report.json + 更新开发队列
- 触发：分析阶段完成后自动执行

### 阶段4：开发生成 (develop)
- 基于任务队列生成SEO知识页面和用户教育内容
- 包含Schema.org结构化数据、SEO优化
- 输出：HTML内容文件 + 开发报告
- 触发：决策阶段完成后自动执行

### 阶段5：质量测试 (test)
- 医疗用语扫描（防止夸大宣传）
- Schema标记验证
- 链接有效性检查
- 字数检查
- SEO基础检查
- 输出：test_report.json
- 触发：开发阶段完成后自动执行

### 阶段6：部署上架 (deploy)
- 将通过测试的内容部署到服务器
- 更新sitemap.xml
- 提交搜索引擎索引
- 输出：deployment_report.json
- 触发：测试阶段完成后自动执行

## 目录结构

```
auto-pipeline/
├── pipeline_state.json          # 全局状态文件
├── config.json                  # 配置文件
├── scheduler.py                 # 调度器（主入口）
├── README.md                    # 本文档
├── reports/
│   ├── intelligence/            # 情报报告
│   ├── analysis/                # 分析/决策/开发/测试报告
│   └── deployed/                # 部署报告
├── content/
│   └── generated/               # 生成的内容文件
├── scripts/
│   ├── core/
│   │   └── state_manager.py     # 状态管理核心模块
│   ├── phase_1_collect/
│   │   └── run.py
│   ├── phase_2_analyze/
│   │   └── run.py
│   ├── phase_3_decide/
│   │   └── run.py
│   ├── phase_4_develop/
│   │   └── run.py
│   ├── phase_5_test/
│   │   └── run.py
│   └── phase_6_deploy/
│       └── run.py
└── logs/
    └── pipeline_YYYYMMDD.log    # 每日日志
```

## 使用方法

### 查看状态
```bash
python scheduler.py status
```

### 运行全部阶段
从当前位置一直执行到无法继续为止：
```bash
python scheduler.py run
```

### 只运行下一个阶段
```bash
python scheduler.py run-next
```

### 启动新的 pipeline
```bash
python scheduler.py start-new
```

### 重置 pipeline
```bash
python scheduler.py reset
```

## 状态管理

所有阶段共享同一个 `pipeline_state.json` 文件，包含：

- pipeline_id: 流水线标识
- status: 总体状态 (idle/running_*/completed/failed_*)
- phases: 各阶段状态（pending/running/completed/failed）
- approved_queue: 已批准项目队列
- watch_queue: 观察列表
- development_tasks: 开发任务队列
- deployment_history: 部署历史
- feedback_metrics: 效果反馈指标

## 决策门禁算法

综合评分 = 来源分 + 目标符合度分 + 市场验证分 + 可行性分

| 分数区间 | 决策 | 动作 |
|---------|------|------|
| ≥70分 | 批准（approved） | 进入开发队列 |
| 50-69分 | 观察（watch） | 2周后重新评估 |
| <50分 | 放弃（reject） | 归档，后续可重评 |

### 评分权重
- **来源数量 (40%)**: ≥3个独立来源得满分，多类型来源额外+5分
- **目标符合度 (30%)**: 高相关=30分，中相关=18分，低相关=9分
- **市场验证 (20%)**: ≥3个信号=20分，≥2个=14分，≥1个=8分
- **技术可行性 (10%)**: 可行性×10分

## 定时任务配置

推荐的定时任务配置：

| 任务 | 频率 | 命令 |
|------|------|------|
| 周度情报收集 | 每周一 03:00 | `python scheduler.py run` |
| 周中调度检查 | 每周三/五 03:00 | `python scheduler.py run-next` |
| 健康检查 | 每周日 04:00 | `python scheduler.py status` |

## 扩展开发

每个阶段脚本遵循统一的接口规范：

1. 从 `state_manager` 导入 `start_phase`、`complete_phase`、`fail_phase`
2. 在 `run()` 函数中：
   - 调用 `start_phase(phase_name)` 标记开始
   - 读取前置阶段输出（`get_phase_output(prev_phase)`）
   - 执行本阶段逻辑
   - 调用 `complete_phase(phase_name, output_file=..., items_processed=N)` 标记完成
   - 异常时调用 `fail_phase(phase_name, error_msg)`
3. 返回 True/False 表示成功/失败
