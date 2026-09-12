import {h} from './dom.js';
export {h, safeLink} from './dom.js';
export {markdown} from './markdown.js';

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
