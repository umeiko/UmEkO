import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js/lib/common';

const parser = new MarkdownIt({ html: false, linkify: true, breaks: true });
const escape = parser.utils.escapeHtml;
const MAX_HIGHLIGHT = 120 * 1024;
const copyIcon =
  '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M9 9h12v12H9Z M15 5V3H3v12h2"/></svg>';

export function codeHtml(text, language, highlight = true) {
  if (highlight && text.length <= MAX_HIGHLIGHT && hljs.getLanguage(language)) {
    try {
      return hljs.highlight(text, { language, ignoreIllegals: true }).value;
    } catch {}
  }
  return escape(text);
}

function codeBlock(text, info, env) {
  const language = parser.utils.unescapeAll(info).trim().split(/\s+/)[0] || 'text';
  const label = escape(language.slice(0, 64));
  const copy = escape(env.translate('code.copy'));
  return `<section class="markdown-code"><div class="code-toolbar"><span class="code-language">${label}</span><button type="button" class="code-copy" data-code-copy>${copyIcon}<span class="copy-label" data-i18n="code.copy">${copy}</span></button></div><pre tabindex="0"><code class="hljs">${codeHtml(text, language, env.highlight !== false)}</code></pre></section>\n`;
}
parser.renderer.rules.fence = (tokens, index, options, env) =>
  codeBlock(tokens[index].content, tokens[index].info, env);
parser.renderer.rules.code_block = (tokens, index, options, env) =>
  codeBlock(tokens[index].content, '', env);
parser.renderer.rules.table_open = () => '<div class="markdown-table-wrap"><table>\n';
parser.renderer.rules.table_close = () => '</table></div>\n';

// Paths are relative to the Markdown file, and stay inside the session workspace.
function workspacePath(href, sourcePath) {
  if (!href || href.startsWith('#') || href.startsWith('//')) return null;
  let relative;
  let parts;
  if (/^workspace-file:/i.test(href)) {
    try {
      relative = decodeURIComponent(href.slice('workspace-file:'.length));
    } catch {
      return null;
    }
    parts = [];
  } else {
    if (/^[a-z][a-z\d+.-]*:/i.test(href) || href.startsWith('/')) return null;
    parts = sourcePath ? sourcePath.split('/').slice(0, -1) : [];
    try {
      relative = decodeURIComponent(href.split(/[?#]/)[0]);
    } catch {
      return null;
    }
  }
  for (const part of relative.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') {
      if (!parts.length) return null;
      parts.pop();
    } else parts.push(part);
  }
  const path = parts.join('/');
  return /^(workspace|attachments|generate)\//.test(path) && !/[\\\0]/.test(path) ? path : null;
}
parser.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const token = tokens[index];
  const href = token.attrGet('href');
  const path = workspacePath(href, env.path);
  if (path) {
    token.attrSet('href', '#workspace-file');
    token.attrSet('class', 'message-file-link');
    token.attrSet('data-workspace-path', encodeURIComponent(path));
  } else if (/^https?:\/\//i.test(href)) {
    token.attrSet('target', '_blank');
    token.attrSet('rel', 'noopener noreferrer');
  } else if (href && !href.startsWith('#') && !/^[a-z][a-z\d+.-]*:/i.test(href)) {
    token.attrSet('href', '#');
  } else if (/^workspace-file:/i.test(href)) {
    token.attrSet('href', '#');
  }
  return self.renderToken(tokens, index, options);
};
const imageRule = parser.renderer.rules.image;
parser.renderer.rules.image = (tokens, index, options, env, self) => {
  const token = tokens[index];
  const src = token.attrGet('src');
  const path = workspacePath(src, env.path);
  if (path && env.workspaceUrl) token.attrSet('src', env.workspaceUrl(path));
  else if (src && !/^https?:\/\//i.test(src)) return escape(token.content);
  token.attrSet('loading', 'lazy');
  return imageRule(tokens, index, options, env, self);
};

export function renderMarkdown(source, env = {}) {
  return parser.render(String(source ?? ''), { translate: (key) => key, ...env });
}

export function renderSkillMarkdown(source, env = {}) {
  const text = String(source ?? '');
  const frontmatter = text.match(/^\uFEFF?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);
  if (!frontmatter) return renderMarkdown(text, env);
  const title = escape(env.translate?.('skill.metadata') || '技能信息');
  return (
    `<details class="skill-metadata"><summary>${title}</summary><pre tabindex="0"><code class="hljs">${codeHtml(frontmatter[1], 'yaml')}</code></pre></details>\n` +
    renderMarkdown(text.slice(frontmatter[0].length), env)
  );
}
