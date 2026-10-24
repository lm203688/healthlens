/* P1-1（2026-10-24）：首启引导——「先给一半，再要数据」。
 *
 * 报告定位：当前流程"先要 15 题，再给 1/8"顺序反了，是首日流失的结构性原因。
 * 设计：
 *   Step 0  欢迎屏（10 秒）：一句话价值主张 + 3 步预告
 *   Step 1  30 秒 3 题快速评估（睡眠 / 精力 / 情绪，各单选）→ 立刻出「3 轴已测 + 5 轴待解锁」雷达
 *   Step 2  数据换价值：连设备 / 传化验单解锁剩余 5 轴
 *   Step 3  完整评估入口 + 结束
 *
 * 无新增后端调用——3 题走现有 /agent/fusion，"3 轴已测"是产品层展示（H 轴 = 情绪、D 轴 = 精力、G 轴 = 睡眠），
 * 其余 5 轴标灰标"待解锁"，避免用户误以为"没测到"就是"没数据"。
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import MedicalDisclaimer from "../components/HealthDisclaimer";
import AxisRadar from "../components/AxisRadar";
import { track } from "../lib/track";

/* 3 道快速题，每题 3-4 个选项，映射到 H/D/G 三轴 */
const QUICK_QUESTIONS = [
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
const LOCKED_AXES = ["A", "B", "C", "E", "F"];

export default function Onboarding() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState({}); // { sleep: {key, score, symptom}, ... }
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState(null);
  const [skipped, setSkipped] = useState(false);

  // 老用户直接进入 Dashboard
  useEffect(() => {
    if (localStorage.getItem("onboarding_completed") === "1") {
      navigate("/", { replace: true });
    }
  }, [navigate]);

  function markComplete() {
    localStorage.setItem("onboarding_completed", "1");
  }

  /* Step 0：欢迎屏 → Step 1 */
  function start() {
    try { track("onboarding_started"); } catch {}
    setStep(1);
  }

  /* 选择某个选项 */
  function pick(qi, opt) {
    setAnswers((p) => ({ ...p, [QUICK_QUESTIONS[qi].key]: opt }));
  }

  /* Step 1 完成：把 3 题拼成 user_input 调 /agent/fusion，得到部分八轴评分 */
  async function submitQuick() {
    const chosen = QUICK_QUESTIONS.filter((_, i) => answers[i]);
    if (chosen.length < 3) return;

    setAnalyzing(true);
    try {
      const parts = [];
      if (chosen[0].symptom) parts.push(chosen[0].symptom);
      if (chosen[1].symptom) parts.push(chosen[1].symptom);
      if (chosen[2].symptom) parts.push(chosen[2].symptom);
      // 无具体症状也走一次 fusion，走"泛基线"（会返回未测量 8 轴，前端展示"3 轴已测"是产品层）
      const resp = await api.agentFusion({ user_input: parts.join(" | ") || "baseline" });
      const data = await resp.json();
      if (resp.ok) {
        setResult(data);
      } else {
        // 网络/接口错——降级：直接展示 3 轴已测的产品层展示
        setResult({ degraded: true });
      }
    } catch {
      setResult({ degraded: true });
    } finally {
      setAnalyzing(false);
      setStep(2);
      try { track("onboarding_quick_done", { quick_answers: 3 }); } catch {}
    }
  }

  /* Step 2：显示部分雷达 + 引导连设备 */
  function goConnectDevice() {
    navigate("/pulse");
    try { track("onboarding_device_cta_clicked"); } catch {}
  }
  function goUploadLab() {
    navigate("/upload");
    try { track("onboarding_upload_cta_clicked"); } catch {}
  }
  function goFullAssess() {
    markComplete();
    navigate("/assess");
    try { track("onboarding_full_assess_cta_clicked"); } catch {}
  }
  function goHome() {
    markComplete();
    navigate("/");
    try { track("onboarding_skipped"); } catch {}
  }

  /* Step 1 未完成时的按钮态 */
  const readyForSubmit = QUICK_QUESTIONS.every((_, i) => answers[i]);

  /* 部分八轴评分（仅 3 轴有值，其余为 0，用颜色区分） */
  function buildPartialScores() {
    const scores = { A: 0, B: 0, C: 0, D: 0, E: 0, F: 0, G: 0, H: 0 };
    if (answers.sleep) scores.G = answers.sleep.score;
    if (answers.energy) scores.D = answers.energy.score;
    if (answers.mood) scores.H = answers.mood.score;
    return scores;
  }
  const partialColors = {
    A: "#cbd5e1", B: "#cbd5e1", C: "#cbd5e1",
    D: "#06b6d4", E: "#cbd5e1", F: "#cbd5e1",
    G: "#84cc16", H: "#ef4444",
  };

  /* ========== 渲染 ========== */

  if (step === 0) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <MedicalDisclaimer />
        <div className="bg-gradient-to-br from-emerald-50 to-cyan-50 rounded-2xl p-8 text-center shadow-sm">
          <div className="text-6xl mb-4">🔬</div>
          <h1 className="text-3xl font-bold text-slate-800 mb-2">{t("onboarding.welcomeTitle")}</h1>
          <p className="text-slate-600">{t("onboarding.welcomeSubtitle")}</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-6 space-y-3">
          <h3 className="font-semibold text-slate-800">{t("onboarding.howItWorks")}</h3>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold shrink-0">1</div>
            <div>
              <p className="font-medium text-slate-800">{t("onboarding.step1Title")}</p>
              <p className="text-sm text-slate-500">{t("onboarding.step1Desc")}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold shrink-0">2</div>
            <div>
              <p className="font-medium text-slate-800">{t("onboarding.step2Title")}</p>
              <p className="text-sm text-slate-500">{t("onboarding.step2Desc")}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold shrink-0">3</div>
            <div>
              <p className="font-medium text-slate-800">{t("onboarding.step3Title")}</p>
              <p className="text-sm text-slate-500">{t("onboarding.step3Desc")}</p>
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={goHome}
            className="flex-1 bg-slate-100 text-slate-600 py-3 rounded-xl font-medium hover:bg-slate-200 transition"
          >
            {t("onboarding.skipForNow")}
          </button>
          <button
            onClick={start}
            className="flex-1 bg-emerald-600 text-white py-3 rounded-xl font-semibold hover:bg-emerald-700 transition"
          >
            {t("onboarding.startBtn")} →
          </button>
        </div>
      </div>
    );
  }

  if (step === 1) {
    return (
      <div className="max-w-2xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-800">{t("onboarding.quickTitle")}</h2>
          <span className="text-sm text-slate-500">{t("onboarding.stepLabel", { current: 1, total: 2 })}</span>
        </div>
        <p className="text-sm text-slate-500">{t("onboarding.quickSubtitle")}</p>

        {analyzing && (
          <div className="text-center py-6 space-y-2">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-emerald-200 border-t-emerald-600" />
            <p className="text-sm text-slate-500">{t("onboarding.analyzing")}</p>
          </div>
        )}

        <div className="space-y-4">
          {QUICK_QUESTIONS.map((q, qi) => (
            <div key={q.key} className="bg-white rounded-2xl shadow-sm p-5">
              <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
                <span>{q.icon}</span> {t(q.titleKey)}
                <span className="text-xs text-slate-400 font-normal">({qi + 1}/3)</span>
              </h3>
              <div className="space-y-2">
                {q.options.map((opt) => {
                  const active = answers[q.key]?.key === opt.key;
                  return (
                    <button
                      key={opt.key}
                      type="button"
                      disabled={analyzing}
                      onClick={() => pick(qi, opt)}
                      className={`w-full text-left px-4 py-3 rounded-xl border transition
                        ${active
                          ? "bg-emerald-50 border-emerald-500 text-emerald-800 font-medium"
                          : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"}`}
                    >
                      <span className="block text-lg leading-tight">{t(opt.labelKey)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => setStep(0)}
            disabled={analyzing}
            className="bg-slate-100 text-slate-600 px-4 py-3 rounded-xl font-medium hover:bg-slate-200 disabled:opacity-50 transition"
          >
            {t("onboarding.back")}
          </button>
          <button
            onClick={submitQuick}
            disabled={!readyForSubmit || analyzing}
            className="flex-1 bg-emerald-600 text-white py-3 rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50 transition"
          >
            {analyzing ? t("onboarding.analyzingBtn") : t("onboarding.getMyPreview")}
          </button>
        </div>
      </div>
    );
  }

  /* Step 2：3 轴已测的雷达 + 引导连设备/传化验单 */
  const scores = buildPartialScores();
  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-emerald-700">{t("onboarding.previewTitle")}</h2>
        <p className="text-slate-500 text-sm mt-1">{t("onboarding.previewSubtitle")}</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-6 flex flex-col items-center">
        <AxisRadar scores={scores} colors={partialColors} size={320} />
        <p className="text-sm text-slate-500 mt-2">
          <span className="font-semibold text-emerald-700">{t("onboarding.measuredCount", { n: 3 })}</span>
          ·
          <span className="ml-2 text-slate-400">{t("onboarding.lockedCount", { n: LOCKED_AXES.length })}</span>
        </p>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <p className="text-amber-800 font-medium">🔓 {t("onboarding.unlockHint")}</p>
        <p className="text-sm text-amber-700 mt-1">{t("onboarding.unlockDesc")}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          onClick={goUploadLab}
          className="bg-white rounded-xl p-4 shadow-sm border border-slate-200 hover:shadow-md hover:border-emerald-300 transition text-left"
        >
          <div className="text-2xl mb-1">📋</div>
          <p className="font-semibold text-slate-800">{t("onboarding.uploadLabTitle")}</p>
          <p className="text-xs text-slate-500 mt-0.5">{t("onboarding.uploadLabDesc")}</p>
        </button>
        <button
          onClick={goConnectDevice}
          className="bg-white rounded-xl p-4 shadow-sm border border-slate-200 hover:shadow-md hover:border-emerald-300 transition text-left"
        >
          <div className="text-2xl mb-1">⌚</div>
          <p className="font-semibold text-slate-800">{t("onboarding.connectDeviceTitle")}</p>
          <p className="text-xs text-slate-500 mt-0.5">{t("onboarding.connectDeviceDesc")}</p>
        </button>
      </div>

      <button
        onClick={goFullAssess}
        className="w-full bg-emerald-600 text-white py-3 rounded-xl font-semibold hover:bg-emerald-700 transition"
      >
        {t("onboarding.goFullAssess")} →
      </button>
      <button
        onClick={goHome}
        className="w-full bg-slate-100 text-slate-600 py-2 rounded-xl text-sm hover:bg-slate-200 transition"
      >
        {t("onboarding.skipForNow")}
      </button>
    </div>
  );
}
