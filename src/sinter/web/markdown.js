/** Readable, bounded Markdown rendering without interpreting HTML from any source. */
import {h, safeLink} from './dom.js';

function literal(value) {
  return value.replace(/\\([\\`*_{}\[\]#!|>])/g, '$1')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

function inline(value, depth = 0) {
  if (depth > 6) return [literal(value)];
  const parts = [];
  // Underscores inside identifiers are literal. URL parentheses may be balanced;
  // unmatched or unsupported link syntax remains visible instead of losing text.
  const pattern = /\\[\\`*_{}\[\]#!|>]|\*\*([^\n]+?)\*\*|(?<![\p{L}\p{N}_])__([^\n]+?)__(?![\p{L}\p{N}_])|(?<!`)(`+)(?!`)([^\n]*?)(?<!`)\3(?!`)|(?<!!)\[([^\[\]\n]+)\]\((<[^<>\s]+>|(?:\\.|[^\s()\\]|\((?:\\.|[^\s()\\])*\))+)\)|\*([^*\n]+)\*|(?<![\p{L}\p{N}_])_([^_\n]+)_(?![\p{L}\p{N}_])/gu;
  let start = 0;
  for (const match of value.matchAll(pattern)) {
    if (match.index > start) parts.push(literal(value.slice(start, match.index)));
    if (match[1] !== undefined || match[2] !== undefined) parts.push(h('strong', {}, inline(match[1] ?? match[2], depth + 1)));
    else if (match[3] !== undefined) parts.push(h('code', {}, /^ .* $/.test(match[4]) && /\S/.test(match[4]) ? match[4].slice(1, -1) : match[4]));
    else if (match[5] !== undefined) {
      let target = literal(match[6].replace(/\\([()\\])/g, '$1'));
      if (target.startsWith('<') && target.endsWith('>')) target = target.slice(1, -1);
      const link = safeLink(target, literal(match[5]));
      parts.push(link.tagName === 'A' ? link : literal(match[0]));
    } else if (match[7] !== undefined || match[8] !== undefined) parts.push(h('em', {}, inline(match[7] ?? match[8], depth + 1)));
    else parts.push(literal(match[0]));
    start = match.index + match[0].length;
  }
  parts.push(literal(value.slice(start)));
  return parts;
}

function cells(line) {
  const values = []; let value = '', ticks = 0;
  // A pipe in inline code or escaped source text is content, not a column edge.
  const tokens = line.trim().match(/\\.|`+|[^\\`|]+|\||\\/g) || [];
  for (const token of tokens) {
    if (/^`+$/.test(token)) ticks = ticks === token.length ? 0 : ticks || token.length;
    if (token === '|' && !ticks) { values.push(value.trim()); value = ''; }
    else value += token;
  }
  values.push(value.trim());
  if (!values[0] && values.length > 1) values.shift();
  if (!values.at(-1) && values.length > 1) values.pop();
  return values;
}

function isTableRule(line) {
  const values = cells(line || '');
  return values.length > 0 && values.every(item => /^:?-{3,}:?$/.test(item));
}

function blocks(lines, root, depth = 0) {
  if (depth > 8) { root.append(h('p', {}, literal(lines.join('\n')))); return; }
  let i = 0;
  const listItem = line => /^( *)([-+*]|\d{1,9}[.)])( +)(.*)$/.exec(line);
  const startsBlock = line => /^(?: {0,3}#{1,6} | {0,3}>|\s*[-+*] |\s*\d{1,9}[.)] | {0,3}`{3,}| {0,3}~{3,}|---+$|\*\*\*+$|___+$)/.test(line);
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = /^\s*(`{3,}|~{3,})([^\s]*)\s*$/.exec(line);
    if (fence) {
      const content = []; i++;
      const close = new RegExp('^\\s*' + fence[1][0] + '{' + fence[1].length + ',}\\s*$');
      while (i < lines.length && !close.test(lines[i])) content.push(lines[i++]);
      if (i < lines.length) i++;
      root.append(h('pre', {}, h('code', {}, content.join('\n') + (content.length ? '\n' : '')))); continue;
    }
    const heading = /^ {0,3}(#{1,6}) (.+)$/.exec(line);
    if (heading) { root.append(h('h' + heading[1].length, {}, inline(heading[2]))); i++; continue; }
    if (/^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { root.append(h('hr')); i++; continue; }
    if (line.includes('|') && isTableRule(lines[i + 1]) && cells(line).length === cells(lines[i + 1]).length) {
      const headers = cells(line), rules = cells(lines[i + 1]);
      const rows = []; i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes('|') && !startsBlock(lines[i])) rows.push(cells(lines[i++]));
      // Preserve unexpected extra cells from a generated table; never discard a
      // user's text merely because its row has more columns than the header.
      const width = rows.reduce((maximum, row) => Math.max(maximum, row.length), headers.length);
      while (headers.length < width) headers.push('');
      const cell = (tag, text, at) => h(tag, {class: rules[at]?.startsWith(':') && rules[at]?.endsWith(':') ? 'align-center' : rules[at]?.endsWith(':') ? 'align-right' : ''}, inline(text));
      const table = h('table', {}, h('thead', {}, h('tr', {}, headers.map((value, at) => cell('th', value, at)))));
      const body = h('tbody'); table.append(body);
      for (const values of rows) body.append(h('tr', {}, headers.map((_, at) => cell('td', values[at] || '', at))));
      root.append(h('div', {class: 'table-scroll', tabIndex: 0, 'aria-label': 'Document table'}, table)); continue;
    }
    if (/^ {0,3}>/.test(line)) {
      const content = [];
      while (i < lines.length && /^ {0,3}>/.test(lines[i])) content.push(lines[i++].replace(/^ {0,3}> ?/, ''));
      const quote = h('blockquote'); blocks(content, quote, depth + 1); root.append(quote); continue;
    }
    const item = listItem(line);
    if (item) {
      const ordered = /^\d/.test(item[2]), indent = item[1].length;
      const list = h(ordered ? 'ol' : 'ul', ordered ? {start: parseInt(item[2], 10)} : {}); root.append(list);
      while (i < lines.length) {
        const next = listItem(lines[i]);
        if (!next || next[1].length !== indent || /^\d/.test(next[2]) !== ordered) break;
        const li = h('li'); list.append(li); i++;
        const continuation = [next[4]], contentIndent = indent + next[2].length + next[3].length;
        while (i < lines.length) {
          if (!lines[i].trim()) {
            let after = i + 1; while (after < lines.length && !lines[after].trim()) after++;
            const upcoming = listItem(lines[after] || '');
            if (upcoming && upcoming[1].length === indent && /^\d/.test(upcoming[2]) === ordered) { i = after; break; }
            if (after === lines.length || lines[after].search(/\S/) <= indent) break;
            continuation.push(''); i++; continue;
          }
          const spaces = lines[i].search(/\S/);
          if (spaces <= indent) break;
          continuation.push(lines[i++].slice(Math.min(contentIndent, spaces)));
        }
        blocks(continuation, li, depth + 1);
      }
      continue;
    }
    const paragraph = [line]; i++;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i]) && !(lines[i].includes('|') && isTableRule(lines[i + 1]))) paragraph.push(lines[i++]);
    const children = [];
    // Drafts include addresses, signatures and quoted source lines. Preserve
    // those deliberate newlines consistently on screen, in copy, and in export.
    paragraph.forEach((value, at) => {
      const hardBreak = at < paragraph.length - 1 && (value.match(/\\+$/)?.[0].length || 0) % 2;
      children.push(...inline(hardBreak ? value.slice(0, -1) : value.replace(/ {2,}$/, '')));
      if (at < paragraph.length - 1) children.push(h('br'));
    });
    root.append(h('p', {}, children));
  }
}

export function markdown(value) {
  const root = h('div', {class: 'document'});
  blocks(String(value ?? '').replace(/\r\n?/g, '\n').split('\n'), root);
  return root;
}
