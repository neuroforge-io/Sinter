import {h,button,field,selectField,check,notice} from './ui.js';
import {request} from './api.js';
export async function browserSettingsPage(applyAppearance) {
  const current=await request('/api/settings');const s=current.settings;
  const fields=Object.fromEntries(['full_name','organisation','role','email','phone','website','location','organisation_type'].map(key=>[key,field(key.replaceAll('_',' '),'text',s[key]||'','Saved only in this browser.') ]));
  const theme=selectField('Colour theme',[['dark','Dark'],['light','Light']],s.theme);
  const size=selectField('Reading size',[['normal','Standard'],['large','Larger text']],s.text_size);
  const density=selectField('Layout',[['comfortable','Comfortable'],['compact','Compact']],s.density);
  const motion=check('Reduce movement and animation',s.reduce_motion);
  const feedback=h('div',{'aria-live':'polite'});
  const save=button('Save browser preferences',async()=>{save.disabled=true;try{const values=Object.fromEntries(Object.entries(fields).map(([key,entry])=>[key,entry.input.value]));const result=await request('/api/settings',{data:{settings:{...values,theme:theme.input.value,text_size:size.input.value,density:density.input.value,reduce_motion:motion.input.checked}}});applyAppearance(result.settings);feedback.replaceChildren(notice('Preferences saved in this browser.','success'));}catch(e){feedback.replaceChildren(notice(e.message,'error'));}finally{save.disabled=false;}},'primary');
  const test=button('Check public model connection',async()=>{test.disabled=true;try{const health=await request('/api/health');feedback.replaceChildren(notice(health.message,health.ok?'success':'warning'));}catch(e){feedback.replaceChildren(notice(e.message,'error'));}finally{test.disabled=false;}},'quiet');
  return h('div',{class:'stack'},h('h2',{},'Your browser workspace'),notice('Saved locally on this device. Export saved workspace to keep a separate backup. No account or API key is needed.'),
    h('div',{class:'card'},h('h3',{},'Your details'),h('div',{class:'form-grid'},...Object.values(fields).map(x=>x.wrap))),
    h('div',{class:'card'},h('h3',{},'Reading comfort'),theme.wrap,size.wrap,density.wrap,motion.wrap,save),
    h('div',{class:'card'},h('h3',{},'Optional public API'),h('p',{},'Search sends the query you enter. AI sends only context you explicitly approve. The current native preview supports short requests and is not qualified for general assistant quality. Longer workflows remain useful as local source-only reports.'),test,
      h('p',{},'Install Sinter for custom providers, API keys, ChatGPT sign-in, local speech and RKC executable/server access. Imported transcripts and atlases work here.')),feedback);
}
