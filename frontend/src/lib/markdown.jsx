/* 轻量 Markdown 渲染器（无外部依赖）
 *
 * 背景：AgentChat 的 process card 内容包含 **加粗**、`代码`、- 列表、空行分段。
 * 直接用 {content} 输出会让 Markdown 语法以字面量形式暴露给用户（如 "**计划**"），
 * 体验差。此模块在客户端把常见 Markdown 子集渲染成 React 元素，避免新增
 * react-markdown 依赖（会拉大 bundle 200KB+）。
 *
 * 支持的语法（覆盖 AgentChat / MyChanges / Dashboard 实际用到的全部）：
 *   **bold**         → <strong>
 *   *italic*         → <em>
 *   `code`           → <code>
 *   ```block```      → <pre><code>
 *   - item           → <ul><li>
 *   1. item          → <ol><li>
 *   > quote          → <blockquote>
 *   空行             → 分段
 *
 * 不支持：图片 / 链接 / 表格 / HTML 原样输出（安全考虑）。
 */

import React from 'react';

// 逐行分类器：list item / quote / blank / paragraph / fence
function parseLines(lines) {
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') { i++; continue; }
    // 代码块 ```...```
    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3);
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        buf.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing fence
      blocks.push({ type: 'code', lang, text: buf.join('\n') });
      continue;
    }
    // 无序列表
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ''));
        i++;
      }
      blocks.push({ type: 'ul', items });
      continue;
    }
    // 有序列表
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      blocks.push({ type: 'ol', items });
      continue;
    }
    // 引用
    if (line.trimStart().startsWith('>')) {
      const items = [];
      while (i < lines.length && lines[i].trimStart().startsWith('>')) {
        items.push(lines[i].replace(/^\s*>\s?/, ''));
        i++;
      }
      blocks.push({ type: 'quote', items });
      continue;
    }
    // 普通段落（可能多行合并，直到遇到空行 / 新块）
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() !== '' &&
           !/^\s*[-*+]\s+/.test(lines[i]) &&
           !/^\s*\d+\.\s+/.test(lines[i]) &&
           !lines[i].trim().startsWith('```') &&
           !lines[i].trimStart().startsWith('>')
    ) {
      buf.push(lines[i]);
      i++;
    }
    blocks.push({ type: 'p', text: buf.join('\n') });
  }
  return blocks;
}

// 行内元素解析：bold / italic / code
function parseInline(text, keyPrefix = '') {
  const out = [];
  let idx = 0;
  let k = 0;
  while (idx < text.length) {
    // `code`（最先匹配，避免 **code** 冲突）
    const codeMatch = text.slice(idx).match(/^`([^`]+)`/);
    if (codeMatch) {
      out.push(<code key={keyPrefix + k++} style={{
        background: '#f3f4f6',
        padding: '1px 6px',
        borderRadius: '4px',
        fontFamily: 'ui-monospace, SFMono-Regular, monospace',
        fontSize: '12px',
      }}>{codeMatch[1]}</code>);
      idx += codeMatch[0].length;
      continue;
    }
    // **bold**
    const boldMatch = text.slice(idx).match(/^\*\*([^*]+)\*\*/);
    if (boldMatch) {
      out.push(<strong key={keyPrefix + k++} style={{ fontWeight: 600, color: '#111827' }}>{boldMatch[1]}</strong>);
      idx += boldMatch[0].length;
      continue;
    }
    // *italic*（单独一个 *，不是 **）
    const italicMatch = text.slice(idx).match(/^\*([^*]+)\*(?!\*)/);
    if (italicMatch) {
      out.push(<em key={keyPrefix + k++} style={{ fontStyle: 'italic' }}>{italicMatch[1]}</em>);
      idx += italicMatch[0].length;
      continue;
    }
    // 累积普通文本直到下一个特殊语法
    let next = idx + 1;
    while (next < text.length) {
      const rest = text.slice(next);
      if (rest.startsWith('`') || rest.startsWith('**') || /^\*[^*]/.test(rest)) break;
      next++;
    }
    if (next > idx) {
      out.push(text.slice(idx, next));
    }
    idx = next;
  }
  return out;
}

/**
 * 渲染一段 Markdown 文本为 React 元素数组。
 * @param {string} text 输入的 Markdown
 * @returns {React.ReactNode}
 */
export function renderMarkdown(text) {
  if (!text || typeof text !== 'string') return null;
  const lines = text.split(/\r?\n/);
  const blocks = parseLines(lines);
  return blocks.map((b, i) => {
    if (b.type === 'code') {
      return (
        <pre key={i} style={{
          background: '#1f2937',
          color: '#f9fafb',
          padding: '10px 12px',
          borderRadius: '6px',
          overflowX: 'auto',
          fontSize: '12px',
          margin: '6px 0',
        }}>
          <code>{b.text}</code>
        </pre>
      );
    }
    if (b.type === 'ul') {
      return (
        <ul key={i} style={{ margin: '4px 0 8px 18px', paddingLeft: 0 }}>
          {b.items.map((it, j) => <li key={j} style={{ marginBottom: 2 }}>{parseInline(it, `ul-${i}-${j}-`)}</li>)}
        </ul>
      );
    }
    if (b.type === 'ol') {
      return (
        <ol key={i} style={{ margin: '4px 0 8px 18px', paddingLeft: 0 }}>
          {b.items.map((it, j) => <li key={j} style={{ marginBottom: 2 }}>{parseInline(it, `ol-${i}-${j}-`)}</li>)}
        </ol>
      );
    }
    if (b.type === 'quote') {
      return (
        <blockquote key={i} style={{
          borderLeft: '3px solid #d1d5db',
          padding: '4px 10px',
          color: '#4b5563',
          margin: '6px 0',
          background: '#f9fafb',
        }}>
          {b.items.map((it, j) => <div key={j}>{parseInline(it, `q-${i}-${j}-`)}</div>)}
        </blockquote>
      );
    }
    // paragraph
    return (
      <div key={i} style={{ margin: '2px 0' }}>
        {b.text.split('\n').map((l, j) => (
          <div key={j}>{l === '' ? '\u00A0' : parseInline(l, `p-${i}-${j}-`)}</div>
        ))}
      </div>
    );
  });
}

/** 消息气泡容器组件：Markdown 内容 + 紧凑排版 */
export function MessageContent({ content }) {
  return <div style={{ fontSize: 13, lineHeight: 1.55 }}>{renderMarkdown(content)}</div>;
}
