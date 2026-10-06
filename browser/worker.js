/* Sinter runs its real Python/domain code in this isolated browser worker. */
import {loadPyodide} from './vendor/pyodide.mjs';
const MAX_BYTES = 25 * 1024 * 1024;
let py, api, db, current, previous, sequence = Promise.resolve();
function database() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('sinter-browser-v1', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('workspace');
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(new Error('Browser storage is unavailable. Your existing data was not changed.'));
    req.onblocked = () => reject(new Error('Another tab is blocking storage. Close other Sinter tabs and reload.'));
  });
}
function read(key) { return new Promise((resolve, reject) => { const tx = db.transaction('workspace'); const req=tx.objectStore('workspace').get(key); req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error); }); }
async function checksum(files) {
  const text = Object.keys(files).sort().map(name=>name+':'+files[name]).join('\n');
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
}
function capture() {
  const files = {};
  for (const name of ['workspace.sqlite3','campaigns.sqlite3','preferences.json']) {
    const path='/sinter-workspace/'+name;
    if (py.FS.analyzePath(path).exists) {
      const bytes=py.FS.readFile(path); let parts=[];
      for(let offset=0;offset<bytes.length;offset+=8192) parts.push(String.fromCharCode(...bytes.subarray(offset,offset+8192)));
      files[name]=btoa(parts.join(''));
    }
  }
  if(JSON.stringify(files).length > MAX_BYTES*1.5) throw new Error('This workspace exceeds the browser storage limit. Export individual projects before saving more.');
  return files;
}
function restore(files) {
  for(const name of ['workspace.sqlite3','campaigns.sqlite3','preferences.json']) {
    const path='/sinter-workspace/'+name;
    if(py.FS.analyzePath(path).exists) py.FS.unlink(path);
    if(files[name]) py.FS.writeFile(path,Uint8Array.from(atob(files[name]),c=>c.charCodeAt(0)));
  }
  api.initialize().destroy();
}
async function validated(record) {
  if(!record || record.schema !== 1 || typeof record.files !== 'object' || !record.files || Array.isArray(record.files)) throw new Error('Saved browser storage needs recovery.');
  if(Object.keys(record.files).some(k=>!['workspace.sqlite3','campaigns.sqlite3','preferences.json'].includes(k)) || Object.values(record.files).some(v=>typeof v!=='string') || JSON.stringify(record.files).length > MAX_BYTES*1.5 || await checksum(record.files)!==record.sha256) throw new Error('Saved browser storage failed its integrity check.');
  return record;
}
async function persist(files) {
  const record={schema:1, files, sha256:await checksum(files), savedAt:Date.now()};
  if(current?.sha256===record.sha256) return;
  await new Promise((resolve,reject)=>{
    const tx=db.transaction('workspace','readwrite'); const store=tx.objectStore('workspace');
    if(current) store.put(current,'previous'); store.put(record,'current');
    tx.oncomplete=resolve;
    tx.onabort=()=>reject(new Error('Save failed: browser storage is full or unavailable. Your last saved workspace is unchanged. Export your editor backup before closing.'));
    tx.onerror=()=>{};
  });
  previous=current; current=record;
}
function transport(path, raw, timeoutMs=30000) {
  // Synchronous XHR is worker-only: Python stays synchronous, UI stays responsive.
  // Fixed paths, no credentials, redirects cannot cross origin under connect-src.
  if(!['/search','/models','/chat/completions'].includes(path)) throw new Error('Unsupported API path');
  const xhr=new XMLHttpRequest(); xhr.open(raw==='null'?'GET':'POST','/v1'+path,false);
  xhr.timeout=Math.max(1,Math.min(Number(timeoutMs)||30000,path==='/chat/completions'?120000:30000));
  self.postMessage({phase:path==='/search'?'Searching the approved public topic…':path==='/chat/completions'?'Waiting for the public model… No request will be automatically replayed.':'Checking the public model catalogue…'}); xhr.setRequestHeader('Accept','application/json');
  if(raw!=='null') xhr.setRequestHeader('Content-Type','application/json');
  try {
    xhr.send(raw==='null'?null:raw);
    if(new URL(xhr.responseURL).origin!==self.location.origin || !/^application\/json(?:;|$)/i.test(xhr.getResponseHeader('Content-Type')||'') || xhr.responseText.length>2097152) throw new Error('Invalid response');
    const data=JSON.parse(xhr.responseText);
    return JSON.stringify({status:xhr.status,data,code:data?.error?.code||''});
  } catch { return JSON.stringify({status:504,data:{},code:'network_unavailable'}); }
}
async function initialize(recovery=false) {
  if(!py) {
    self.postMessage({phase:'Loading the local Python engine… The first visit downloads about 15 MB; your documents stay on this device.'});
    py=await loadPyodide({indexURL:new URL('./vendor/',self.location.href).href});
    await py.loadPackage(['sqlite3','ssl']);
    const response=await fetch('./python-files.json'); if(!response.ok) throw new Error('Sinter source files could not load. Reload when your connection returns.');
    const files=await response.json();
    for(const [name, content] of Object.entries(files)) { if(!/^sinter\/[\w/.-]+$/.test(name)||name.includes('..'))throw new Error('Invalid source package'); const path='/app/'+name; py.FS.mkdirTree(path.slice(0,path.lastIndexOf('/')));py.FS.writeFile(path,content); }
    py.runPython("import sys; sys.path.insert(0, '/app')\nfrom sinter import browser_runtime as browser_api");
    api=py.globals.get('browser_api'); api.configure_network(transport);
    py.FS.mkdirTree('/sinter-workspace');
  }
  db=db||await database();
  current=await read('current'); previous=await read('previous');
  if(recovery) {
    const candidate=await validated(previous);
    restore(candidate.files);
    // Preserve the corrupt/current record until the user explicitly recovers.
    current=undefined; await persist(candidate.files);
  } else if(current) { await validated(current); restore(current.files); }
  else api.initialize().destroy();
  return {ready:true, savedAt:current?.savedAt||null};
}
async function handle(message) {
  const {id,kind,payload}=message;
  try {
    if(kind==='init') { self.postMessage({id,result:await initialize(payload?.recovery)}); return; }
    if(!api)throw new Error('The browser runtime is not ready.');
    const before=capture();
    const result=JSON.parse(api.request(JSON.stringify(payload)));
    const writes=new Set(['/api/settings','/api/casebooks/save','/api/casebooks/delete','/api/campaigns/save','/api/campaigns/delete','/api/reports','/api/reports/delete','/api/watches','/api/watches/update','/api/watches/delete','/api/watches/check','/api/browser/import']);
    if(result.status<400 && payload.data !== undefined && writes.has(payload.path)) {
      try { await persist(capture()); }
      catch(error) { restore(before); throw error; }
    }
    self.postMessage({id,result,savedAt:current?.savedAt});
  } catch(error) { self.postMessage({id,error:String(error.message||error),recovery:!!previous}); }
}
self.onmessage=event=>{ sequence=sequence.then(()=>handle(event.data)); };
