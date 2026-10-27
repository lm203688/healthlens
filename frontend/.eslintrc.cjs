/* P0-QA-01（2026-10-27）：此前 package.json 声明了 `lint: eslint src/ --fix`
 * 但从未声明 eslint 依赖、也无任何 ESLint 配置文件——`npm run lint` 在 CI
 * 上实际从未真正跑过（eslint 未安装即报 "eslint: not found"，或装后报
 * "No ESLint configuration found"）。本配置补齐，并把 `--fix` 从 CI 唯一
 * lint 行为中移除（报告要求：lint 应检出不修复，修复走显式 `--fix` 步骤）。
 *
 * 用 .cjs（而非 .eslintrc.js）是因为 package.json 为 `type: module`，
 * .eslintrc.js 会被当作 ESM 导致 ESLint 加载失败；ESLint 8 默认 legacy
 * config 格式，.eslintrc.cjs 与其兼容性最稳。
 */
module.exports = {
  root: true,
  env: { browser: true, es2021: true, node: true },
  extends: [
    "eslint:recommended",
    "plugin:react-hooks/recommended",
  ],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  plugins: ["react-refresh"],
  rules: {
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    // 项目现有代码风格：未使用的变量/导入在若干页面存在，属历史债务，
    // 不在此轮一并强开，避免 lint 门禁把 P0-QA-01 之外的大量无关文件标红。
    "no-unused-vars": "off",
  },
  ignorePatterns: ["dist", "node_modules", "*.config.js", "*.config.mjs"],
};
