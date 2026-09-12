/** Safe DOM primitives shared by controls and document rendering. */
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

export function safeLink(url, label = url) {
  try {
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url) || /[\\\s\p{Cc}\p{Cf}]/u.test(url)) throw new Error('Invalid link');
    const parsed = new URL(url);
    if (!['https:', 'http:'].includes(parsed.protocol) || !parsed.hostname || parsed.port === '0' || parsed.username || parsed.password) throw new Error('Invalid link');
    return h('a', {href: parsed.href, target: '_blank', rel: 'noopener noreferrer'}, label);
  } catch { return h('span', {}, 'No valid external link supplied'); }
}
