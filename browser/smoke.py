"""Real-browser contract for the built WebAssembly application (fictional data only)."""
from pathlib import Path
import argparse
import json
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8877/sinter/')
    parser.add_argument('--browser', choices=['chromium','firefox','webkit'], default='chromium')
    parser.add_argument('--output', type=Path, default=Path('browser-evidence'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=getattr(p,args.browser).launch()
        context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
        page=context.new_page(); errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.url)
        page.get_by_role('heading',name='Your next piece of work starts here.').wait_for(timeout=90000)
        page.get_by_role('button',name='Open garden handover',exact=True).click()
        page.get_by_role('button',name='Save project',exact=True).click()
        page.locator('[data-casebook-save-success="true"]').wait_for(timeout=30000)
        page.reload()
        page.get_by_role('link',name='Community casebooks',exact=False).click()
        page.get_by_text('Fictional garden project - volunteer handover',exact=False).first.wait_for(timeout=30000)
        saved=page.evaluate("async()=>await sinterBrowser.request('/api/browser/export')")
        assert len(saved['casebooks'])==1
        assert saved['casebooks'][0]['title']=='Fictional garden project - volunteer handover'
        with page.expect_download() as result:
            page.get_by_role('button',name='Export saved workspace',exact=True).click()
        download=result.value;download.save_as(args.output/'workspace.json')
        exported=json.loads((args.output/'workspace.json').read_text())
        assert exported['casebooks']==saved['casebooks']
        page.screenshot(path=str(args.output/'desktop.png'),full_page=True)
        # Actual dispatcher in the browser, not a parallel JS implementation.
        contract=page.evaluate("""async()=>{
          const req=(path,data)=>sinterBrowser.request(path,{data});
          const bundle=await req('/api/practice/garden');
          const campaign=await req('/api/campaigns/save',{document:bundle.campaign});
          const book=(await req('/api/casebooks')).casebooks[0];
          const loaded=await req('/api/casebooks/'+book.id);
          const job=await req('/api/casebooks/build',{id:book.id,revision:loaded.revision});
          const result=await req('/api/jobs/'+job.id);
          if(result.status!=='done')throw Error(JSON.stringify(result));
          await req('/api/reports',{report:result.result});
          const invalid=await req('/api/browser/export'); invalid.casebooks[0].schema='unknown';
          let rejected=false;try{await req('/api/browser/import',{document:invalid,confirm:true});}catch{rejected=true;}
          return {campaign:!!campaign.id,rejected,reports:(await req('/api/reports')).reports.length};
        }""")
        assert contract=={'campaign':True,'rejected':True,'reports':1},contract
        second=context.new_page();second.goto(args.url)
        second.get_by_text('Sinter is already open in another tab.',exact=False).wait_for(timeout=15000)
        second.close()
        page.set_viewport_size({'width':390,'height':844})
        page.goto(args.url+'#home')
        page.get_by_role('heading',name='Your next piece of work starts here.').wait_for(timeout=90000)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
        page.screenshot(path=str(args.output/'mobile.png'),full_page=True)
        assert not errors,errors
        (args.output/'receipt.json').write_text(json.dumps({'browser':args.browser,'contract':contract,'errors':errors,'passed':True},indent=2)+'\n')
        browser.close()

if __name__=='__main__': main()
