/* P0-FE-01（2026-10-27 回归保护）：Onboarding 三题答案键逻辑的纯函数抽取。
 *
 * 背景：Onboarding.jsx 曾按 `answers[i]` 索引读取答案（i 是问题序号），但
 * `pick()` 按 `answers[q.key]`（q.key 是 sleep/energy/mood）写入——读键与写键
 * 不一致导致三题全部答完仍 `undefined`，提交按钮恒被禁用、无法进入预览。
 * 修复改为统一按 `q.key` 读；本模块把该逻辑抽成纯函数，供组件复用并加回归测试，
 * 防止「写键=key、读键=索引」的错位再次混入。
 */

/* 3 道快速题，每题 3-4 个选项，映射到 H/D/G 三轴 */
export const QUICK_QUESTIONS = [
  {
    key: "sleep",
    icon: "😴",
    titleKey: "onboarding.q1Title",
    options: [
      { key: "a", labelKey: "onboarding.q1a", score: 30, symptom: "insomnia,fatigue" },
      { key: "b", labelKey: "onboarding.q1b", score: 55, symptom: "early_wake" },
      { key: "c", labelKey: "onboarding.q1c", score: 75, symptom: "" },
      { key: "d", labelKey: "onboarding.q1d", score: 90, symptom: "" },
    ],
  },
  {
    key: "energy",
    icon: "⚡",
    titleKey: "onboarding.q2Title",
    options: [
      { key: "a", labelKey: "onboarding.q2a", score: 35, symptom: "fatigue,low_energy" },
      { key: "b", labelKey: "onboarding.q2b", score: 60, symptom: "daytime_fatigue" },
      { key: "c", labelKey: "onboarding.q2c", score: 80, symptom: "" },
      { key: "d", labelKey: "onboarding.q2d", score: 92, symptom: "" },
    ],
  },
  {
    key: "mood",
    icon: "🙂",
    titleKey: "onboarding.q3Title",
    options: [
      { key: "a", labelKey: "onboarding.q3a", score: 30, symptom: "anxiety,low_mood,irritable" },
      { key: "b", labelKey: "onboarding.q3b", score: 55, symptom: "stress" },
      { key: "c", labelKey: "onboarding.q3c", score: 78, symptom: "" },
      { key: "d", labelKey: "onboarding.q3d", score: 90, symptom: "" },
    ],
  },
];

/* 未解锁轴列表（Step 2 提示语用） */
export const LOCKED_AXES = ["A", "B", "C", "E", "F"];

/* 已作答的问题（按 q.key 读——P0-FE-01 修复后的语义） */
export function chosenQuestions(answers) {
  return QUICK_QUESTIONS.filter((q) => answers[q.key]);
}

/* 是否三题全部作答（提交按钮可用性） */
export function allAnswered(answers) {
  return QUICK_QUESTIONS.every((q) => answers[q.key]);
}

/* 把答案拼成 /agent/fusion 的 user_input 片段 */
export function buildUserInput(answers) {
  // P0-FE-01 回归保护：症状在「选中的选项」answers[q.key].symptom 上，
  // 不在问题对象 q 顶层——原实现 `chosen[0].symptom` 恒为 undefined，
  // 导致即使三题带症状也永远拼出 "baseline"，fusion 拿不到真实症状。
  const chosen = chosenQuestions(answers);
  const parts = [];
  for (const q of chosen) {
    const opt = answers[q.key];
    if (opt && opt.symptom) parts.push(opt.symptom);
  }
  // 无具体症状也走一次 fusion，走"泛基线"（返回未测量 8 轴，前端展示"3 轴已测"是产品层）
  return parts.join(" | ") || "baseline";
}

/* 部分八轴评分（仅 3 轴有值，其余为 0，用颜色区分） */
export function buildPartialScores(answers) {
  const scores = { A: 0, B: 0, C: 0, D: 0, E: 0, F: 0, G: 0, H: 0 };
  if (answers.sleep) scores.G = answers.sleep.score;
  if (answers.energy) scores.D = answers.energy.score;
  if (answers.mood) scores.H = answers.mood.score;
  return scores;
}
