/** Same-origin client. Tokens stay in memory, never URLs or browser storage. */
let sessionPromise;
export function session() {
  if (!sessionPromise) sessionPromise = request('/api/session').catch(error => { sessionPromise = null; throw error; });
  return sessionPromise;
}

export async function request(path, {data, signal, method = data === undefined ? 'GET' : 'POST', responseType = 'json'} = {}) {
  if (!path.startsWith('/api/')) throw new Error('Only local API paths are allowed.');
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, {once: true});
  const timer = setTimeout(abort, 35000);
  try {
    const headers = {};
    if (method === 'POST') {
      headers['Content-Type'] = 'application/json';
      headers['X-Sinter-Token'] = (await session()).token;
    }
    const response = await fetch(path, {method, headers, cache: 'no-store',
      body: data === undefined ? undefined : JSON.stringify(data), signal: controller.signal});
    const result = response.ok && responseType === 'blob' ? await response.blob() : await response.json();
    if (!response.ok) { const error = new Error(result.error || result.message || `The request failed (${response.status}).`); error.status = response.status; error.partialResult = result.partial_result; throw error; }
    return result;
  } catch (error) {
    if (error.name === 'TypeError') throw new Error('Cannot reach the local Sinter app. Keep the launcher window open, then retry.');
    if (error.name === 'AbortError') throw new Error('The request stopped or timed out. Check the app connection before retrying.');
    throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}

/** SSE framing accepts split CRLF and multiline data; bounds unfinished frames. */
export function sseParser(onData) {
  let buffer = '', data = [], frameSize = 0;
  function line(value) {
    value = value.replace(/\r$/, '');
    if (!value) {
      if (data.length) { onData(data.join('\n')); data = []; frameSize = 0; }
    } else if (value.startsWith('data:')) {
      frameSize += value.length;
      if (frameSize > 2097152) throw new Error('The stream exceeded the display limit.');
      data.push(value.slice(5).replace(/^ /, ''));
    }
  }
  return {
    feed(text, final = false) {
      buffer += text;
      if (buffer.length > 2097152) throw new Error('The stream exceeded the display limit.');
      let position;
      while ((position = buffer.indexOf('\n')) >= 0) {
        const value = buffer.slice(0, position);
        buffer = buffer.slice(position + 1);
        line(value);
      }
      if (final) { if (buffer) line(buffer); buffer = ''; line(''); }
    }
  };
}

export async function stream(path, data, onEvent, signal) {
  if (!path.startsWith('/api/')) throw new Error('Only local API paths are allowed.');
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, {once: true});
  // Allow the 660-second Python stream budget plus one idle-read and delivery margin.
  const timer = setTimeout(abort, 700000);
  let reader, completed = false, size = 0;
  try {
    const response = await fetch(path, {method: 'POST', cache: 'no-store', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-Sinter-Token': (await session()).token}, body: JSON.stringify(data)});
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'The request could not be started.');
    }
    if (!response.body) throw new Error('This browser could not open a response stream.');
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    const parser = sseParser(payload => {
      if (payload === '[DONE]') { completed = true; return; }
      const event = JSON.parse(payload);
      if (event.type === 'error') throw new Error(event.error || 'The stream failed.');
      onEvent(event);
    });
    while (!completed) {
      const {value, done} = await reader.read();
      if (done) { parser.feed(decoder.decode(), true); break; }
      size += value.length;
      if (size > 2097152) throw new Error('The response exceeded the display limit.');
      parser.feed(decoder.decode(value, {stream: true}));
    }
    if (!completed) throw new Error('The response ended early. Partial output is not complete.');
  } finally {
    clearTimeout(timer); signal?.removeEventListener('abort', abort);
    if (reader) await reader.cancel().catch(() => {});
  }
}

export async function waitForJob(id, onStatus = () => {}) {
  let failures = 0, delay = 500;
  for (;;) {
    let job;
    try { job = await request(`/api/jobs/${id}`); failures = 0; }
    catch (error) {
      if ([400, 403, 404].includes(error.status) || ++failures > 5) {
        const failure = new Error(`${error.message} Open Recent activity to check task ${id} before starting another copy.`);
        failure.jobId = id; throw failure;
      }
      onStatus({id, status: 'reconnecting', message: 'Connection interrupted. Rechecking the existing task, not starting it again...'});
      await new Promise(resolve => setTimeout(resolve, Math.min(500 * 2 ** failures, 8000)));
      continue;
    }
    onStatus(job);
    if (job.status === 'done') return job.result;
    if (job.status === 'failed') { const error = new Error(job.error); error.partialResult = job.result; error.jobId = id; throw error; }
    if (job.status === 'cancelled') throw new Error('Cancelled. No report was saved.');
    await new Promise(resolve => setTimeout(resolve, delay));
    delay = Math.min(delay + 100, 2000);
  }
}
