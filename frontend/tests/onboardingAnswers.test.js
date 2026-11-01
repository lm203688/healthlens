/* P0-FE-01 回归测试（2026-10-27）：锁定 Onboarding 答案键「写键=key、读键=key」。
 *
 * 背景：Onboarding.jsx 曾按 `answers[i]` 索引读取（i 是问题序号），但 `pick()`
 * 按 `answers[q.key]`（sleep/energy/mood）写入——读键与写键不一致，三题答完仍
 * undefined，提交按钮恒禁用，首启价值无法交付。修复改为统一按 q.key 读。
 *
 * 本测试直接验证纯函数语义：三种答案组合下 chosenQuestions/allAnswered/
 * buildUserInput/buildPartialScores 的行为，防止「读键=索引」再次混入。
 */
import { describe, it, expect } from "vitest";
import {
  QUICK_QUESTIONS,
  LOCKED_AXES,
  chosenQuestions,
  allAnswered,
  buildUserInput,
  buildPartialScores,
} from "../src/lib/onboardingAnswers";

describe("onboardingAnswers", () => {
  it("QUICK_QUESTIONS 有 3 题，键分别为 sleep/energy/mood", () => {
    expect(QUICK_QUESTIONS.map((q) => q.key)).toEqual(["sleep", "energy", "mood"]);
    expect(QUICK_QUESTIONS).toHaveLength(3);
  });

  it("LOCKED_AXES 为剩余 5 轴（A/B/C/E/F）", () => {
    expect(LOCKED_AXES).toEqual(["A", "B", "C", "E", "F"]);
  });

  it("写键=key 时，chosenQuestions 能全部命中（此前按索引读会返回空）", () => {
    const answers = {
      sleep: { key: "b", score: 55, symptom: "early_wake" },
      energy: { key: "c", score: 80, symptom: "" },
      mood: { key: "a", score: 30, symptom: "anxiety,low_mood,irritable" },
    };
    expect(chosenQuestions(answers)).toHaveLength(3);
  });

  it("allAnswered：三题全答 true；缺任一题 false（提交按钮可用性）", () => {
    const full = {
      sleep: { key: "a", score: 30, symptom: "insomnia,fatigue" },
      energy: { key: "b", score: 60, symptom: "daytime_fatigue" },
      mood: { key: "c", score: 78, symptom: "" },
    };
    expect(allAnswered(full)).toBe(true);
    expect(allAnswered({ sleep: full.sleep })).toBe(false);
    expect(allAnswered({ sleep: full.sleep, energy: full.energy })).toBe(false);
  });

  it("buildUserInput：带症状的答案拼成 | 分隔；全无症状回退 baseline", () => {
    const withSymptoms = {
      sleep: { key: "a", score: 30, symptom: "insomnia,fatigue" },
      energy: { key: "b", score: 60, symptom: "daytime_fatigue" },
      mood: { key: "a", score: 30, symptom: "anxiety,low_mood,irritable" },
    };
    const input = buildUserInput(withSymptoms);
    expect(input).toContain("insomnia,fatigue");
    expect(input).toContain("daytime_fatigue");
    expect(input).toContain("anxiety,low_mood,irritable");
    expect(input.split(" | ")).toHaveLength(3);

    const noSymptoms = {
      sleep: { key: "c", score: 75, symptom: "" },
      energy: { key: "d", score: 92, symptom: "" },
      mood: { key: "d", score: 90, symptom: "" },
    };
    expect(buildUserInput(noSymptoms)).toBe("baseline");
  });

  it("buildPartialScores：只把 G/D/H 三轴写成答案分，其余为 0", () => {
    const answers = {
      sleep: { key: "a", score: 30, symptom: "insomnia,fatigue" },
      energy: { key: "c", score: 80, symptom: "" },
      mood: { key: "d", score: 90, symptom: "" },
    };
    const scores = buildPartialScores(answers);
    expect(scores).toEqual({ A: 0, B: 0, C: 0, D: 80, E: 0, F: 0, G: 30, H: 90 });
  });

  it("buildPartialScores：空答案时八轴全 0（不把未测量误显示为确定分）", () => {
    const scores = buildPartialScores({});
    expect(Object.values(scores)).toEqual([0, 0, 0, 0, 0, 0, 0, 0]);
  });
});
