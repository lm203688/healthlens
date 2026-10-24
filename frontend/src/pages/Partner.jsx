/* P1-4（2026-10-24）：合作开发者中心（Partner Console MVP）。
 *
 * 定位：外部开发者 30 分钟内能完成首次调用。
 * 公开页（无需登录）——开发者通常没登录账号。
 *
 * 内容：
 *   1) Hero + 三步快速开始
 *   2) 端点速览表（6 个 partner-api 端点）
 *   3) curl 示例（带复制按钮）
 *   4) SDK 入口 + 认证说明 + 配额
 *   5) 合规声明（claims_guard 5 法域）
 *   6) 申请 Key 表单（mailto 兜底）
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { track } from "../lib/track";

const API_BASE = "https://api.healthlens.cc/api/v1/partner-api";
const OPENAPI_URL = "https://api.healthlens.cc/api/v1/openapi.json";
const DOCS_URL = "https://api.healthlens.cc/api/v1/docs";

const ENDPOINTS = [
  {
    method: "GET",
    path: "/health",
    key: "endpointHealth",
    desc: "endpointHealthDesc",
    needsKey: false,
  },
  {
    method: "GET",
    path: "/config",
    key: "endpointConfig",
    desc: "endpointConfigDesc",
    needsKey: true,
  },
  {
    method: "POST",
    path: "/health-score",
    key: "endpointScore",
    desc: "endpointScoreDesc",
    needsKey: true,
    body: { user_id: "u_123", date: "2026-10-24" },
  },
  {
    method: "POST",
    path: "/axis-assessment",
    key: "endpointAxis",
    desc: "endpointAxisDesc",
    needsKey: true,
    body: { user_id: "u_123" },
  },
  {
    method: "POST",
    path: "/tcm-recommendations",
    key: "endpointTcm",
    desc: "endpointTcmDesc",
    needsKey: true,
    body: { user_id: "u_123" },
  },
  {
    method: "POST",
    path: "/wellness-report",
    key: "endpointReport",
    desc: "endpointReportDesc",
    needsKey: true,
    body: { user_id: "u_123" },
  },
];

const CURL_EXAMPLE = `curl -X POST "${API_BASE}/health-score" \\
  -H "X-API-Key: sk_live_XXXXXX" \\
  -H "Content-Type: application/json" \\
  -d '{"user_id": "u_123", "date": "2026-10-24"}'`;

function buildCurl(ep) {
  if (!ep.body) return `curl "${API_BASE}${ep.path}" -H "X-API-Key: sk_live_XXXXXX"`;
  return `curl -X POST "${API_BASE}${ep.path}" \\
  -H "X-API-Key: sk_live_XXXXXX" \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(ep.body)}'`;
}

export default function Partner() {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(null); // endpoint path or "default"
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [useCase, setUseCase] = useState("");

  function copy(text, key) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => {
        setCopied(key);
        setTimeout(() => setCopied(null), 1500);
      });
    }
  }

  function submitApply(e) {
    e.preventDefault();
    track("partner_apply_submitted", { company });
    // 无后端表单端点——直接打开 mailto，让用户填完发出去
    const subject = encodeURIComponent(`HealthLens API Key 申请 — ${company || "个人开发者"}`);
    const body = encodeURIComponent(
      `邮箱：${email}\n公司：${company}\n应用场景：${useCase}\n`
    );
    window.location.href = `mailto:partners@healthlens.cc?subject=${subject}&body=${body}`;
  }

  return (
    <div className="bg-slate-50 min-h-screen">
      {/* Hero */}
      <section className="bg-gradient-to-br from-emerald-600 to-teal-700 text-white">
        <div className="max-w-6xl mx-auto px-4 py-14">
          <div className="text-sm font-medium opacity-80 mb-2">🔬 {t("partner.title")}</div>
          <h1 className="text-4xl font-bold mb-3">{t("partner.heroTitle")}</h1>
          <p className="text-lg opacity-90 mb-6 max-w-2xl">{t("partner.subtitle")}</p>
          <p className="text-sm opacity-75 mb-8">{t("partner.heroDesc")}</p>
          <div className="flex flex-wrap gap-3">
            <a href={DOCS_URL} target="_blank" rel="noopener noreferrer"
              onClick={() => track("partner_docs_opened")}
              className="px-5 py-2.5 bg-white text-emerald-700 rounded-lg font-medium hover:bg-emerald-50 transition">
              📖 {t("partner.ctaOpenAPI")}
            </a>
            <a href={OPENAPI_URL} target="_blank" rel="noopener noreferrer"
              onClick={() => track("partner_openapi_opened")}
              className="px-5 py-2.5 bg-emerald-500/40 border border-white/30 rounded-lg font-medium hover:bg-emerald-500/60 transition">
              📄 {t("partner.ctaSdkDocs")}
            </a>
            <button onClick={() => track("partner_apply_clicked")}
              className="px-5 py-2.5 bg-emerald-400/30 border border-white/30 rounded-lg font-medium hover:bg-emerald-400/50 transition">
              🔑 {t("partner.ctaGetKey")}
            </button>
          </div>
        </div>
      </section>

      <div className="max-w-6xl mx-auto px-4 py-10 space-y-12">
        {/* Quick Start */}
        <section>
          <h2 className="text-2xl font-bold text-slate-800 mb-1">{t("partner.quickstartTitle")}</h2>
          <p className="text-slate-500 mb-5">{t("partner.quickstartDesc")}</p>
          <div className="grid gap-4 md:grid-cols-3">
            {[1, 2, 3].map((n) => (
              <div key={n} className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
                <div className="text-emerald-600 font-bold text-lg mb-2">{t(`partner.quickstartStep${n}`).split(" ")[0]}</div>
                <p className="text-slate-600 text-sm">{t(`partner.quickstartStep${n}`).replace(/^\d+\.\s*/, "")}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Endpoints */}
        <section>
          <h2 className="text-2xl font-bold text-slate-800 mb-5">{t("partner.endpointsTitle")}</h2>
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold w-20">Method</th>
                  <th className="px-4 py-3 text-left font-semibold">Path</th>
                  <th className="px-4 py-3 text-left font-semibold hidden md:table-cell">说明</th>
                  <th className="px-4 py-3 text-right font-semibold w-24">Key</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ENDPOINTS.map((ep) => (
                  <tr key={ep.path} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono font-semibold ${
                        ep.method === "GET" ? "bg-blue-100 text-blue-700" : "bg-emerald-100 text-emerald-700"
                      }`}>{ep.method}</span>
                    </td>
                    <td className="px-4 py-3">
                      <code className="font-mono text-slate-800">{ep.path}</code>
                    </td>
                    <td className="px-4 py-3 text-slate-600 hidden md:table-cell">
                      <div className="font-medium text-slate-700">{t(`partner.${ep.key}`)}</div>
                      <div className="text-xs text-slate-500">{t(`partner.${ep.desc}`)}</div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {ep.needsKey ? (
                        <span className="text-xs text-amber-600">必需</span>
                      ) : (
                        <span className="text-xs text-slate-400">公开</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Curl Example */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-2xl font-bold text-slate-800">{t("partner.codeExampleTitle")}</h2>
            <button onClick={() => copy(CURL_EXAMPLE, "default")}
              className="px-3 py-1.5 bg-slate-800 text-white text-xs rounded-lg hover:bg-slate-700 transition">
              {copied === "default" ? t("partner.copiedBtn") : t("partner.copyBtn")}
            </button>
          </div>
          <pre className="bg-slate-900 text-slate-100 rounded-xl p-5 overflow-x-auto text-sm leading-relaxed">
            <code>{CURL_EXAMPLE}</code>
          </pre>

          <p className="text-sm text-slate-500 mt-3">
            每个端点都可点击方法标签复制对应 curl：
          </p>
          <div className="grid gap-2 md:grid-cols-2 mt-3">
            {ENDPOINTS.filter((ep) => ep.body).map((ep) => (
              <div key={ep.path} className="bg-slate-900 rounded-lg p-3 flex items-start gap-2">
                <code className="flex-1 text-xs text-slate-100 overflow-x-auto whitespace-pre">{buildCurl(ep)}</code>
                <button onClick={() => copy(buildCurl(ep), ep.path)}
                  className="shrink-0 px-2 py-1 bg-slate-700 text-white text-xs rounded hover:bg-slate-600">
                  {copied === ep.path ? "✓" : "⧉"}
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* Auth + SDK + Quota */}
        <section className="grid gap-6 md:grid-cols-3">
          <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
            <h3 className="font-bold text-slate-800 mb-2">🔐 {t("partner.authTitle")}</h3>
            <p className="text-sm text-slate-600">{t("partner.authDesc")}</p>
            <p className="text-xs text-slate-500 mt-3 font-mono">X-API-Key: sk_live_XXXXXX</p>
          </div>
          <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
            <h3 className="font-bold text-slate-800 mb-2">📦 {t("partner.sdkTitle")}</h3>
            <p className="text-sm text-slate-600 mb-3">{t("partner.sdkDesc")}</p>
            <div className="flex flex-wrap gap-2">
              <span className="px-2.5 py-1 bg-emerald-50 text-emerald-700 text-xs rounded-full font-medium">{t("partner.sdkPython")}</span>
              <span className="px-2.5 py-1 bg-blue-50 text-blue-700 text-xs rounded-full font-medium">{t("partner.sdkTs")}</span>
              <span className="px-2.5 py-1 bg-purple-50 text-purple-700 text-xs rounded-full font-medium">{t("partner.sdkSwift")}</span>
            </div>
            <p className="text-xs text-slate-500 mt-3">{t("partner.sdkInstallHint")}</p>
          </div>
          <div className="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
            <h3 className="font-bold text-slate-800 mb-2">📊 {t("partner.quotaTitle")}</h3>
            <ul className="text-sm text-slate-600 space-y-1">
              <li>{t("partner.quotaRow1")}</li>
              <li>{t("partner.quotaRow2")}</li>
              <li>{t("partner.quotaRow3")}</li>
            </ul>
          </div>
        </section>

        {/* Compliance */}
        <section className="bg-amber-50 border border-amber-200 rounded-xl p-5">
          <h3 className="font-bold text-amber-900 mb-2">⚖️ {t("partner.complianceTitle")}</h3>
          <p className="text-sm text-amber-900/80 mb-2">{t("partner.complianceDesc")}</p>
          <p className="text-xs text-amber-800 italic">{t("partner.wellnessNote")}</p>
        </section>

        {/* Apply Form */}
        <section className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
          <h2 className="text-2xl font-bold text-slate-800 mb-1">{t("partner.applyTitle")}</h2>
          <p className="text-slate-500 mb-5">{t("partner.applyDesc")}</p>
          <form onSubmit={submitApply} className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">{t("partner.applyEmail")}</label>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">{t("partner.applyCompany")}</label>
              <input type="text" required value={company} onChange={(e) => setCompany(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400" />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">{t("partner.applyUseCase")}</label>
              <textarea rows="3" value={useCase} onChange={(e) => setUseCase(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400" />
            </div>
            <div className="md:col-span-2">
              <button type="submit"
                className="px-6 py-2.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition">
                📩 {t("partner.applyBtn")}
              </button>
            </div>
          </form>
        </section>

        {/* Footer */}
        <footer className="text-center text-xs text-slate-400 pb-4">
          {t("partner.footerNote")}
        </footer>
      </div>
    </div>
  );
}
