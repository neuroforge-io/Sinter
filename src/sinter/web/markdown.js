/** Readable, bounded Markdown rendering without interpreting HTML from any source. */
import {h, safeLink} from './dom.js';
import {isDocumentPageBreak} from './document-page-break.js';

function literal(value) {
  return value.replace(/\\([\\`*_{}\[\]#!|>+.~)\-])/g, '$1')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

function inline(value, depth = 0) {
  if (depth > 6) return [literal(value)];
  const parts = [];
  // Underscores inside identifiers are literal. URL parentheses may be balanced;
  // unmatched or unsupported link syntax remains visible instead of losing text.
  const pattern = /\\[\\`*_{}\[\]#!|>+.~)\-]|\*\*([^\n]+?)\*\*|(?<![\p{L}\p{N}_])__([^\n]+?)__(?![\p{L}\p{N}_])|(?<!`)(`+)(?!`)([^\n]*?)(?<!`)\3(?!`)|(?<!!)\[([^\[\]\n]+)\]\((<[^<>\s]+>|(?:\\.|[^\s()\\]|\((?:\\.|[^\s()\\])*\))+)\)|\*([^*\n]+)\*|(?<![\p{L}\p{N}_])_([^_\n]+)_(?![\p{L}\p{N}_])/gu;
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


function sourceLines(source) {
  const lines = [];
  let start = 0, index = 0;
  while (index < source.length) {
    if (source[index] !== '\n' && source[index] !== '\r') { index++; continue; }
    const end = index;
    if (source[index] === '\r' && source[index + 1] === '\n') index++;
    index++;
    lines.push({text: source.slice(start, end), start, end: index});
    start = index;
  }
  lines.push({text: source.slice(start), start, end: source.length});
  return lines;
}

function lexMarkdownBlocks(source, depth = 0, pageBreaks = null, compact = false) {
  return lexMarkdownLines(sourceLines(source), depth, pageBreaks, compact);
}

function lexMarkdownLines(lines, depth = 0, pageBreaks = null, compact = false) {
  if (depth > 8) return lines.length ? [{
    kind: 'deep-literal', start: lines[0].start, end: lines.at(-1).end,
    lines: lines.map(line => line.text), complete: true,
  }] : [];
  const textLines = lines.map(line => line.text), tokens = [];
  const listItem = line => /^( *)([-+*]|\d{1,9}[.)])( +)(.*)$/.exec(line);
  const startsBlock = line => /^(?: {0,3}#{1,6} | {0,3}>|\s*[-+*] |\s*\d{1,9}[.)] | {0,3}\x60{3,}| {0,3}~{3,}|---+$|\*\*\*+$|___+$)/.test(line);
  const push = (kind, first, after, values = {}) => {
    if (compact) {
      tokens.push({kind, start: lines[first].start, end: lines[after - 1].end,
        complete: values.complete ?? true});
      return;
    }
    const selected = lines.slice(first, after);
    tokens.push({kind, start: selected[0].start, end: selected.at(-1).end,
      lines: selected.map(line => line.text), complete: true, ...values});
  };
  let i = 0;
  while (i < lines.length) {
    const line = textLines[i];
    if (!line.trim()) {
      const first = i++;
      while (i < lines.length && !textLines[i].trim()) i++;
      push('blank', first, i);
      continue;
    }
    if (isDocumentPageBreak(textLines, i, depth)
        && (pageBreaks === null || pageBreaks.has(lines[i].start))) { push('page-break', i, ++i); continue; }
    const fence = /^\s*(\x60{3,}|~{3,})([^\s]*)\s*$/.exec(line);
    if (fence) {
      const first = i, contentStart = ++i;
      const close = new RegExp('^\\s*' + fence[1][0] + '{' + fence[1].length + ',}\\s*$');
      while (i < lines.length && !close.test(textLines[i])) i++;
      const closed = i < lines.length, content = compact ? null : textLines.slice(contentStart, i);
      if (closed) i++;
      push('fence', first, i, {content, complete: closed});
      continue;
    }
    const heading = /^ {0,3}(#{1,6}) (.+)$/.exec(line);
    if (heading) { push('heading', i, ++i, {level: heading[1].length, content: heading[2]}); continue; }
    if (/^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { push('rule', i, ++i); continue; }
    if (line.includes('|') && isTableRule(textLines[i + 1]) && cells(line).length === cells(textLines[i + 1]).length) {
      const first = i, headers = cells(line), rules = cells(textLines[i + 1]);
      i += 2;
      while (i < lines.length && textLines[i].trim() && textLines[i].includes('|') && !startsBlock(textLines[i])) i++;
      push('table', first, i, {headers, rules, rows: textLines.slice(first + 2, i).map(cells)});
      continue;
    }
    if (/^ {0,3}>/.test(line)) {
      const first = i;
      while (i < lines.length && /^ {0,3}>/.test(textLines[i])) i++;
      push('quote', first, i);
      continue;
    }
    const item = listItem(line);
    if (item) {
      const first = i, ordered = /^\d/.test(item[2]), indent = item[1].length, items = [];
      while (i < lines.length) {
        const next = listItem(textLines[i]);
        if (!next || next[1].length !== indent || /^\d/.test(next[2]) !== ordered) break;
        i++;
        const continuation = [next[4]], contentIndent = indent + next[2].length + next[3].length;
        while (i < lines.length) {
          if (!textLines[i].trim()) {
            let after = i + 1;
            while (after < lines.length && !textLines[after].trim()) after++;
            const upcoming = listItem(textLines[after] || '');
            if (upcoming && upcoming[1].length === indent && /^\d/.test(upcoming[2]) === ordered) { i = after; break; }
            if (after === lines.length || textLines[after].search(/\S/) <= indent) break;
            continuation.push('');
            i++;
            continue;
          }
          const spaces = textLines[i].search(/\S/);
          if (spaces <= indent) break;
          continuation.push(textLines[i++].slice(Math.min(contentIndent, spaces)));
        }
        items.push(continuation);
      }
      push('list', first, i, {ordered, ordinalStart: parseInt(item[2], 10), items});
      continue;
    }
    const first = i++;
    while (i < lines.length && textLines[i].trim() && !startsBlock(textLines[i])
        && !(textLines[i].includes('|') && isTableRule(textLines[i + 1]))) i++;
    push('paragraph', first, i);
  }
  return tokens;
}

function renderParagraph(lines, root) {
  const children = [];
  // Preserve deliberate line breaks in addresses, signatures and quoted wording.
  lines.forEach((value, at) => {
    const hardBreak = at < lines.length - 1 && (value.match(/\\+$/)?.[0].length || 0) % 2;
    children.push(...inline(hardBreak ? value.slice(0, -1) : value.replace(/ {2,}$/, '')));
    if (at < lines.length - 1) children.push(h('br'));
  });
  root.append(h('p', {}, children));
}

function renderMarkdownBlocks(source, root, depth = 0, pageBreaks = null) {
  for (const token of lexMarkdownBlocks(source, depth, pageBreaks)) {
    if (token.kind === 'blank') continue;
    if (token.kind === 'deep-literal') {
      root.append(h('p', {}, literal(token.lines.join('\n'))));
    } else if (token.kind === 'page-break') {
      root.append(h('div', {class: 'document-page-break', role: 'separator', 'aria-label': 'Page break'}, 'Page break'));
    } else if (token.kind === 'fence') {
      root.append(h('pre', {}, h('code', {}, token.content.join('\n') + (token.content.length ? '\n' : ''))));
    } else if (token.kind === 'heading') {
      root.append(h('h' + token.level, {}, inline(token.content)));
    } else if (token.kind === 'rule') {
      root.append(h('hr'));
    } else if (token.kind === 'table') {
      const headers = [...token.headers], rules = token.rules, rows = token.rows;
      const width = rows.reduce((maximum, row) => Math.max(maximum, row.length), headers.length);
      while (headers.length < width) headers.push('');
      const cell = (tag, text, at) => h(tag, {class: rules[at]?.startsWith(':') && rules[at]?.endsWith(':') ? 'align-center' : rules[at]?.endsWith(':') ? 'align-right' : ''}, inline(text));
      const table = h('table', {}, h('thead', {}, h('tr', {}, headers.map((value, at) => cell('th', value, at)))));
      const body = h('tbody'); table.append(body);
      for (const values of rows) body.append(h('tr', {}, headers.map((_, at) => cell('td', values[at] || '', at))));
      root.append(h('div', {class: 'table-scroll', tabIndex: 0, 'aria-label': 'Document table'}, table));
    } else if (token.kind === 'quote') {
      const quote = h('blockquote');
      renderMarkdownBlocks(token.lines.map(line => line.replace(/^ {0,3}> ?/, '')).join('\n'), quote, depth + 1);
      root.append(quote);
    } else if (token.kind === 'list') {
      const list = h(token.ordered ? 'ol' : 'ul', token.ordered ? {start: token.ordinalStart} : {});
      root.append(list);
      for (const continuation of token.items) {
        const li = h('li'); list.append(li);
        renderMarkdownBlocks(continuation.join('\n'), li, depth + 1);
      }
    } else renderParagraph(token.lines, root);
  }
}

function compactMarkdownBlocks(source) {
  return lexMarkdownBlocks(source, 0, null, true);
}

export function createMarkdownIndex(value) {
  const source = String(value ?? '');
  return {source, blocks: compactMarkdownBlocks(source)};
}

function advanceCodePoints(source, start, limit) {
  let end = start, count = 0;
  while (end < source.length && count < limit) { end += source.codePointAt(end) > 0xffff ? 2 : 1; count++; }
  return {end, count};
}

function isCodePointBoundary(source, offset) {
  if (offset <= 0 || offset >= source.length) return true;
  const before = source.charCodeAt(offset - 1), after = source.charCodeAt(offset);
  return !(before >= 0xd800 && before <= 0xdbff && after >= 0xdc00 && after <= 0xdfff);
}

/** Select a bounded source window using the same complete-block lexer as rendering. */
export function markdownWindow(value, start = 0, limit = 2400, index = null) {
  const source = String(value ?? '');
  if (!Number.isInteger(limit) || limit < 1 || limit > 2400) throw new RangeError('A Markdown preview section must contain 1 to 2,400 characters.');
  if (!Number.isInteger(start) || start < 0 || start > source.length || !isCodePointBoundary(source, start)) {
    throw new RangeError('A Markdown preview offset must be a Unicode character boundary.');
  }
  const blocks = index?.source === source && Array.isArray(index.blocks) ? index.blocks : compactMarkdownBlocks(source);
  if (start === source.length) return {markdown: '', start, end: start, characters: 0, truncated: false, literal: false, literalReason: null, segments: [], pageBreaks: []};
  let low = 0, high = blocks.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (blocks[middle].end <= start) low = middle + 1;
    else high = middle;
  }
  const position = low;
  if (position >= blocks.length || blocks[position].start > start) {
    throw new Error('The saved wording preview could not find this source section.');
  }
  const budget = advanceCodePoints(source, start, limit), segments = [], pageBreaks = [];
  let end = start;
  const addSegment = (from, after, literalSource, reason = null) => {
    if (after <= from) return;
    const segment = {start: from - start, end: after - start, literal: literalSource, reason};
    const previous = segments.at(-1);
    if (previous && previous.literal === segment.literal && previous.end === segment.start) {
      previous.end = segment.end;
      previous.reason ||= segment.reason;
    } else segments.push(segment);
  };
  for (let at = position; at < blocks.length && end < budget.end; at++) {
    const block = blocks[at];
    if (block.start < end) {
      const after = Math.min(budget.end, block.end);
      addSegment(end, after, true, block.complete ? 'continuation' : 'unfinished-block');
      end = after;
      if (end < block.end) break;
      continue;
    }
    if (block.start !== end) throw new Error('The saved wording Markdown sections are not contiguous.');
    if (!block.complete) {
      const after = Math.min(budget.end, block.end);
      addSegment(end, after, true, 'unfinished-block');
      end = after;
      if (end < block.end) break;
      continue;
    }
    if (block.end <= budget.end) {
      if (block.kind === 'page-break') pageBreaks.push(block.start - start);
      addSegment(end, block.end, false);
      end = block.end;
      continue;
    }
    // An oversized block cannot be kept whole on any section: use the remaining
    // space after a fitting prefix rather than creating a tiny extra section.
    if (end === start || advanceCodePoints(source, block.start, limit).end < block.end) {
      addSegment(end, budget.end, true, 'oversized-block');
      end = budget.end;
    }
    break;
  }
  if (end === start) throw new Error('The saved wording preview could not advance within its character limit.');
  const section = source.slice(start, end), characters = [...section].length;
  if (characters > limit || !isCodePointBoundary(source, end)
      || segments.at(-1)?.end !== section.length) {
    throw new Error('The saved wording preview exceeded its safe section boundary.');
  }
  return {markdown: section, start, end, characters, truncated: end < source.length,
    literal: segments.some(segment => segment.literal), literalReason: segments.find(segment => segment.literal)?.reason ?? null,
    segments, pageBreaks};
}

/** Optional original-source page-break offsets keep bounded slices from inventing dividers. */
export function markdown(value, {pageBreaks = null} = {}) {
  const root = h('div', {class: 'document'});
  renderMarkdownBlocks(String(value ?? ''), root, 0, pageBreaks === null ? null : new Set(pageBreaks));
  return root;
}
