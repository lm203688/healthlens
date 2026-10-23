/* P0-3（2026-10-23）：全局 ErrorBoundary。
 *
 * 背景：产品评估定位到全站无 ErrorBoundary——任一页面渲染异常会导致整站白屏。
 * 此组件在应用最外层包裹，捕获子树内的 React 错误，展示友好提示 + 重新加载按钮，
 * 不再让整站白屏。
 *
 * 用法：
 *   <ErrorBoundary>
 *     <App />
 *   </ErrorBoundary>
 */
import { Component } from "react";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    // 生产环境可在 console.error 基础上接错误上报（Sentry/Bugsnag）
    try {
      console.error("[ErrorBoundary] render error:", error, info);
    } catch {}
  }

  handleReload = () => {
    // 清本地状态 → 整页刷新（保留 URL hash 支持回到出错页）
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f9fafb",
          padding: "24px",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <div
          style={{
            background: "#fff",
            border: "1px solid #e5e7eb",
            borderRadius: 12,
            padding: "32px",
            maxWidth: 480,
            width: "100%",
            boxShadow: "0 4px 12px rgba(0,0,0,0.05)",
          }}
        >
          <div style={{ fontSize: 40, marginBottom: 12 }}>😵</div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: "#1f2937", marginBottom: 8 }}>
            页面渲染出了点问题
          </h2>
          <p style={{ color: "#6b7280", fontSize: 14, lineHeight: 1.6, marginBottom: 16 }}>
            别担心，你的数据是安全的。请刷新页面重试；如果问题持续，请联系支持。
          </p>
          <details style={{ marginBottom: 16 }}>
            <summary style={{ color: "#3b82f6", cursor: "pointer", fontSize: 13 }}>
              查看错误详情（仅开发调试用）
            </summary>
            <pre
              style={{
                background: "#fef2f2",
                border: "1px solid #fecaca",
                borderRadius: 6,
                padding: 8,
                fontSize: 11,
                color: "#991b1b",
                whiteSpace: "pre-wrap",
                marginTop: 8,
                maxHeight: 200,
                overflow: "auto",
              }}
            >
              {String(this.state.error?.message || this.state.error) +
                (this.state.info?.componentStack
                  ? "\n\n" + this.state.info.componentStack
                  : "")}
            </pre>
          </details>
          <button
            onClick={this.handleReload}
            style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "10px 20px",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              width: "100%",
            }}
          >
            刷新页面
          </button>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
