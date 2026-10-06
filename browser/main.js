import {h, button, notice, download} from './static/ui.js';
const controls=document.getElementById('browser-controls');
const status=h('p',{role:'status','aria-live':'polite'},'Opening your browser workspace…');
const actions=h('div',{class:'button-row'});
controls.append(h('div',{class:'browser-heading'},h('a',{href:'/sinter/'},'About Sinter & downloads'),h('strong',{},'Sinter · browser edition')),status,
  h('p',{class:'fine'},'Your projects stay in this browser on this device. Nothing is uploaded automatically. Use Save in the editor, then export a backup. Browser clearing, private browsing or device loss can erase local work. Backups are unencrypted.'),actions);
let worker, ready=false, counter=0, pending=new Map(), active=0;
let releaseLock, ownsLock=false;
function failed(error) {
  ready=false; status.textContent=error.message||String(error);status.className='notice error';
  for(const item of pending.values()) {clearTimeout(item.timer);item.reject(error);} pending.clear(); active=0;
}
function rpc(kind,payload,signal) {
  if(signal?.aborted)return Promise.reject(new Error('Cancelled before starting.'));
  const id=++counter;
  return new Promise((resolve,reject)=>{
    const abort=()=>{worker.terminate();failed(new Error('Operation stopped. Saved work is preserved; unfinished results were discarded. Reload to continue. No request was replayed.'));};
    const timer=setTimeout(abort,180000);
    signal?.addEventListener('abort',abort,{once:true});
    pending.set(id,{timer,reject,resolve:result=>{signal?.removeEventListener('abort',abort);resolve(result);}});
    worker.postMessage({id,kind,payload});
  });
}
async function request(path,options={}) {
  if(!ready)throw new Error('The workspace is not ready. Reload to continue.');
  active++;
  let errorStatus = null;
  status.textContent='Working locally… Search and AI send only the inputs you choose.';
  try {
    const response=await rpc('request',{path,data:options.data,method:options.method|| (options.data===undefined?'GET':'POST')},options.signal);
    if(response.status>=400) {const error=new Error(response.result.error||'The operation could not complete.');error.status=response.status;error.partialResult=response.result.partial_result;throw error;}
    if(options.responseType==='blob') {
      const r=response.result; return new Blob([r.content_base64?Uint8Array.from(atob(r.content_base64),c=>c.charCodeAt(0)):r.content],{type:r.content_type});
    }
    return response.result;
  } catch(error) {errorStatus=error.message;throw error;} finally {active--;if(errorStatus){status.className='notice error';status.textContent=errorStatus;}else if(ready){status.className='';status.textContent=active?'Working locally…':'Browser storage ready. Use Save for project changes; export a backup to keep a separate copy.';}}
}
async function start(recovery=false) {
  if(!ownsLock)throw new Error('Close the other Sinter tab and reload here before recovering data.');
  worker?.terminate(); worker=new Worker('./worker.js',{type:'module'});
  worker.onmessage=({data})=>{
    if(data.phase){status.textContent=data.phase;return;}
    const item=pending.get(data.id);if(!item)return;
    clearTimeout(item.timer);pending.delete(data.id);
    if(data.error){const error=new Error(data.error);error.recovery=data.recovery;item.reject(error);} else item.resolve(data.result);
  };
  worker.onerror=()=>failed(new Error('The local Python engine could not start. Your saved data was not changed. Reload or export recovery data.'));
  await rpc('init',{recovery}); ready=true;status.textContent='Browser storage ready. Nothing has been sent to a model.';
}
const exportButton=button('Export saved workspace',async()=>{
  exportButton.disabled=true;
  try {const data=await request('/api/browser/export');download('sinter-workspace-'+new Date().toISOString().slice(0,10)+'.json',JSON.stringify(data,null,2),'application/json');status.textContent='Backup download prepared. Check that the file saved. Unsaved editor inputs are not included.';}catch(e){status.textContent=e.message;}finally{exportButton.disabled=false;}
},'quiet');
const file=h('input',{type:'file',accept:'.json,application/json',hidden:true,'aria-label':'Import saved workspace backup'});
const importButton=button('Import workspace backup',()=>file.click(),'quiet');
file.addEventListener('change',async()=>{
  const selected=file.files?.[0];file.value='';if(!selected)return;
  if(selected.size>25*1024*1024){status.textContent='Choose a workspace JSON backup smaller than 25 MB.';return;}
  importButton.disabled=true;
  try {
    const document=JSON.parse(await selected.text());
    const counts=await request('/api/browser/import/preview',{data:{document}});
    const summary=Object.entries(counts).map(([key,value])=>`${value} ${key}`).join(', ');
    if(!confirm(`Restore ${summary}? This replaces the saved browser workspace and discards unsaved editor inputs. Export your current saved workspace and unsaved project backups first. Imported search watches start paused.`)){status.textContent='Import cancelled. Your workspace is unchanged.';return;}
    await request('/api/browser/import',{data:{document,confirm:true}});
    location.reload();
  }catch(e){status.textContent='Import rejected: '+e.message+' Your saved workspace is unchanged.';}finally{importButton.disabled=false;}
});
const recoverButton=button('Recover previous save',async()=>{
  if(!confirm('Restore the previous successful save? Newer saved changes and unsaved editor inputs will be discarded. Export them first if possible.'))return;
  try{await start(true);location.reload();}catch(e){failed(e);}
},'quiet');
const stopButton=button('Stop current operation',()=>{
  if(!active)return;
  if(confirm('Stop the browser engine? Saved work is preserved. Unfinished results are discarded; you will need to reload.')) {worker.terminate();failed(new Error('Stopped. Saved work is preserved. Reload to continue. No request was replayed.'));}
},'quiet');
actions.append(exportButton,importButton,file,recoverButton,stopButton);
const details=h('details',{},h('summary',{},'What runs here?'),
  h('p',{},'This is Sinter’s real Python workbench running locally with WebAssembly: casebooks, funding campaigns, research, source-only briefs, transcript minutes, document comparisons, action plans, reports and Word/JSON/CSV/calendar exports. Saved projects reload from IndexedDB. Project JSON formats match the installed app.'),
  h('p',{},'Optional search uses the capacity-limited NeuroForge public search API. Empty results are not a verified absence of information. Optional AI uses the currently available public model; it may reject longer contexts and is not qualified for general assistant quality.'),
  h('p',{},'Operating-system features require installed Sinter: local speech transcription, ChatGPT sign-in, custom provider keys, RKC executable/server connections and saving to an arbitrary filesystem path. Existing transcripts and RKC atlases can be imported. Use downloads to keep files.'),
  h('p',{},'Only one tab can edit a browser workspace at a time. Search watches run while this page is open and active; browser sleep can delay them. Local jobs run serially; Stop current operation discards unfinished work without replay.'));
controls.append(details);
globalThis.sinterBrowser={request};
async function boot() {
  if(!navigator.locks || !globalThis.indexedDB || !globalThis.Worker || !globalThis.WebAssembly)throw new Error('This browser needs WebAssembly, IndexedDB and Web Locks. Use a current Chrome, Edge, Firefox or Safari browser, or install Sinter.');
  await new Promise((resolve,reject)=>{
    navigator.locks.request('sinter-browser-workspace-v1',{ifAvailable:true},async lock=>{
      if(!lock){reject(new Error('Sinter is already open in another tab. Close that tab, then reload here to avoid overwriting its work.'));return;}
      ownsLock=true;resolve();await new Promise(r=>{releaseLock=r;});
    }).catch(reject);
  });
  await start(); await import('./static/app.js');
  setInterval(async()=>{if(ready&&!active&&document.visibilityState==='visible'){try{await request('/api/watches/check',{data:{}});}catch(e){status.textContent=e.message;}}},60000);
}
boot().catch(failed);
