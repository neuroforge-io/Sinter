import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {setImmediate as nextTurn} from 'node:timers/promises';
const source=readFileSync(new URL('../src/sinter/web/api.js',import.meta.url),'utf8');
let serial=0;
async function fixture(t){
  const api=await import('data:text/javascript;base64,'+Buffer.from(source+'\n// instance '+(++serial)).toString('base64'));
  let now=0,id=0,upstream,signal,calls=0;const timers=new Map();
  t.mock.method(globalThis,'setTimeout',(fn,ms)=>{const key=++id;timers.set(key,{at:now+ms,fn});return key;});
  t.mock.method(globalThis,'clearTimeout',key=>timers.delete(key));
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    calls++;if(path==='/api/session')return Response.json({token:'local-test-token'});
    assert.equal(path,'/api/chat');assert.equal(options.headers['X-Sinter-Token'],'local-test-token');signal=options.signal;
    return new Response(new ReadableStream({start(c){upstream=c;signal.addEventListener('abort',()=>c.error(new DOMException('Aborted','AbortError')),{once:true});}}));
  });
  const events=[],controller=new AbortController();
  const pending=api.stream('/api/chat',{},event=>events.push(event),controller.signal);
  await nextTurn();await nextTurn();
  return {pending,events,controller,get signal(){return signal;},get calls(){return calls;},
    tick(ms){now+=ms;for(const [key,timer] of [...timers])if(timer.at<=now){timers.delete(key);timer.fn();}},
    complete(){upstream.enqueue(new TextEncoder().encode('data: {"type":"delta","text":"Hello"}\n\ndata: [DONE]\n\n'));upstream.close();}};
}
test('browser survives the former 150-second timeout and completes once',async t=>{
  const f=await fixture(t);f.tick(150001);assert.equal(f.signal.aborted,false);f.complete();await f.pending;
  assert.deepEqual(f.events,[{type:'delta',text:'Hello'}]);assert.equal(f.calls,2);
});
test('browser retains an absolute 700-second ceiling',async t=>{
  const f=await fixture(t);f.tick(699999);assert.equal(f.signal.aborted,false);
  const rejected=assert.rejects(f.pending,{name:'AbortError'});f.tick(2);await rejected;assert.equal(f.signal.aborted,true);
});
test('human cancellation still aborts the stream without retrying it',async t=>{
  const f=await fixture(t);const rejected=assert.rejects(f.pending,{name:'AbortError'});f.controller.abort();await rejected;
  assert.equal(f.signal.aborted,true);assert.equal(f.calls,2);
});
