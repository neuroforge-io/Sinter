/** DOM construction only: remote content is never assigned to innerHTML. */
export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === 'class') element.className = value;
    else if (key === 'text') element.textContent = value;
    else if (key.startsWith('on')) element.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key in element && !key.startsWith('aria-')) element[key] = value;
    else if (value !== false && value != null) element.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child != null && child !== false) element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

export function button(label, action, style = '') {
  return h('button', {type: 'button', class: `button ${style}`, onclick: action}, label);
}

let sequence = 0;
export function field(label, type = 'text', value = '', help = '', props = {}) {
  const id = `field-${++sequence}`;
  const input = type === 'textarea' ? h('textarea', {id, value, ...props})
    : type === 'select' ? h('select', {id, ...props})
      : h('input', {id, type, ...(type === 'file' ? {} : {value}), ...props});
  if (help) input.setAttribute('aria-describedby', `${id}-help`);
  return {input, wrap: h('div', {class: 'field'}, h('label', {htmlFor: id}, label), input,
    help ? h('small', {id: `${id}-help`}, help) : null)};
}

export function selectField(label, options, value = '', help = '') {
  const result = field(label, 'select', '', help);
  for (const [key, name] of options) result.input.append(h('option', {value: key}, name));
  result.input.value = value || options[0]?.[0] || '';
  return result;
}

export function check(label, checked = false) {
  const input = h('input', {type: 'checkbox', checked});
  return {input, wrap: h('label', {class: 'checkbox'}, input, h('span', {}, label))};
}

export function notice(message, kind = '') {
  return h('div', {class: `notice ${kind}`, role: kind === 'error' ? 'alert' : 'note'}, message);
}

export function announce(message) {
  document.getElementById('announcements').textContent = message;
}

export function safeLink(url, label = url) {
  try {
    if (typeof url !== 'string' || /[\\\x00-\x20\x7f]/.test(url)) throw new Error('Invalid link');
    const parsed = new URL(url);
    if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error('Invalid link');
    return h('a', {href: parsed.href, target: '_blank', rel: 'noopener noreferrer'}, label);
  } catch { return h('span', {}, 'No valid external link supplied'); }
}

function unescapeLiteral(value) {
  return value.replace(/\\([\\`*_{}\[\]#!|])/g, '$1')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

/** Deliberately non-HTML Markdown. Source links use safeLink separately. */
export function markdown(value) {
  const root = h('div', {class: 'document'});
  let list = null, code = null;
  for (const line of String(value).split('\n')) {
    if (line.startsWith('```')) {
      if (code) code = null;
      else { code = h('pre'); root.append(code); }
      list = null;
      continue;
    }
    if (code) { code.append(document.createTextNode(line + '\n')); continue; }
    if (!line.trim()) { list = null; continue; }
    const heading = /^(#{1,3}) (.+)$/.exec(line);
    if (heading) { root.append(h(`h${heading[1].length}`, {}, unescapeLiteral(heading[2]))); list = null; }
    else if (line.startsWith('> ')) { root.append(h('blockquote', {}, h('p', {}, unescapeLiteral(line.slice(2))))); list = null; }
    else if (line.startsWith('- ')) {
      if (!list) { list = h('ul'); root.append(list); }
      list.append(h('li', {}, unescapeLiteral(line.slice(2))));
    } else { root.append(h('p', {}, unescapeLiteral(line))); list = null; }
  }
  return root;
}

export function download(name, content, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = h('a', {href: url, download: name});
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function reportName(title) {
  return 'sinter-' + title.normalize('NFKC').replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').slice(0, 80).replace(/[. ]+$/, '') + '-DRAFT';
}

export function dateTime(seconds) {
  return seconds ? new Date(seconds * 1000).toLocaleString() : 'Not checked yet';
}
