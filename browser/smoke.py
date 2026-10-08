"""Real-browser contract for the built WebAssembly application (fictional data only)."""
from pathlib import Path
import argparse
import json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def phone_geometry(page):
    """Keep complete DOM geometry and ancestry without copying editor values."""
    return page.evaluate("""() => {
      const viewport = {width: innerWidth, height: innerHeight, scrollX, scrollY,
        rootClientWidth: document.documentElement.clientWidth,
        rootScrollWidth: document.documentElement.scrollWidth,
        bodyClientWidth: document.body.clientWidth, bodyScrollWidth: document.body.scrollWidth,
        devicePixelRatio};
      const nodes = [...document.querySelectorAll('*')];
      const indices = new Map(nodes.map((element, index) => [element, index]));
      const closedDetails = [...document.querySelectorAll('details:not([open])')];
      const describe = element => {
        const rect = element.getBoundingClientRect(), style = getComputedStyle(element);
        return {index: indices.get(element),
          parentIndex: indices.get(element.parentElement) ?? null,
          tag: element.tagName.toLowerCase(),
          id: element.id, classes: [...element.classList], role: element.getAttribute('role'),
          type: element.getAttribute('type'), hidden: element.hidden, inert: element.inert,
          rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height,
            top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left},
          scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
          offsetWidth: element.offsetWidth, scrollHeight: element.scrollHeight,
          clientHeight: element.clientHeight,
          style: {display: style.display, visibility: style.visibility,
            position: style.position, width: style.width, minWidth: style.minWidth,
            maxWidth: style.maxWidth, boxSizing: style.boxSizing,
            overflowX: style.overflowX, overflowY: style.overflowY,
            whiteSpace: style.whiteSpace, overflowWrap: style.overflowWrap,
            wordBreak: style.wordBreak, flexBasis: style.flexBasis,
            gridTemplateColumns: style.gridTemplateColumns},
          closedDetailAncestors: closedDetails
            .filter(parent => parent !== element && parent.contains(element))
            .map(parent => indices.get(parent))};
      };
      const geometry = nodes.map(describe);
      return {viewport, nodeCount: nodes.length, nodes: geometry,
        overflowing: geometry.filter(item => item.rect.right > innerWidth
          || item.rect.left < 0 || item.scrollWidth > item.clientWidth),
        controls: [...document.querySelectorAll('input, textarea, select, button')]
          .map(element => ({...describe(element),
            optionCount: element.tagName === 'SELECT' ? element.options.length : null})),
        details: [...document.querySelectorAll('details')].map(element => ({
          ...describe(element), open: element.open,
          summary: element.querySelector(':scope > summary')
            ? describe(element.querySelector(':scope > summary')) : null,
          directChildren: [...element.children].map(describe)}))};
    }""")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8877/sinter/')
    parser.add_argument('--browser', choices=['chromium','firefox','webkit'], default='chromium')
    parser.add_argument('--output', type=Path, default=Path('browser-evidence'))
    parser.add_argument('--chromium', type=Path, help='Existing Chromium executable for an offline local check.')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.chromium and (args.browser != 'chromium' or not args.chromium.is_file()):
        parser.error('--chromium requires the chromium browser and an existing executable.')
    with sync_playwright() as p:
        launch={'executable_path':str(args.chromium)} if args.chromium else {}
        browser=getattr(p,args.browser).launch(**launch)
        context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
        page=context.new_page(); errors=[]; forbidden=[]
        origin=urlparse(args.url).netloc
        def local_only(route):
            target=urlparse(route.request.url)
            if target.netloc != origin or target.path in {'/v1/models','/v1/chat/completions'}:
                forbidden.append(route.request.url)
                route.abort()
            else:
                route.continue_()
        context.route('**/*',local_only)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.url)
        page.get_by_role('heading',name='Your next piece of work starts here.').wait_for(timeout=90000)
        page.get_by_role('button',name='Switch to light theme',exact=True).click()
        page.wait_for_function("async () => (await sinterBrowser.request('/api/settings')).settings.theme === 'light'")
        page.reload()
        page.get_by_role('button',name='Switch to dark theme',exact=True).wait_for(timeout=90000)
        page.get_by_role('button',name='Open garden handover',exact=True).click()
        page.get_by_role('button',name='Save project',exact=True).click()
        page.locator('[data-casebook-save-success="true"]').wait_for(timeout=30000)
        page.reload()
        page.get_by_role('link',name='Community casebooks',exact=False).click()
        project_details=page.locator('.browser-project-details')
        project_summary=project_details.locator(':scope>summary')
        assert project_details.evaluate('(element)=>element.open')
        page.get_by_text('Fictional garden project - volunteer handover',exact=False).first.wait_for(timeout=30000)
        page.get_by_text('Optional AI drafting uses your configured connection',exact=False).wait_for()
        # Normal catalogue Open must reveal and focus the current editor itself.
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate('scrollTo(0,0)')
        page.get_by_role('button',name='Open project',exact=True).click()
        opened_project=page.get_by_label('Project name',exact=True)
        page.wait_for_function('(id)=>document.activeElement.id===id',arg=opened_project.get_attribute('id'))
        assert opened_project.input_value()=='Fictional garden project - volunteer handover'
        page.screenshot(path=str(args.output/'saved-project-open-390-viewport.png'))
        opened_box=opened_project.bounding_box()
        opened_question=page.get_by_label('What do you need to find out?',exact=True).bounding_box()
        opened_layout={'project_input':opened_box,'scroll_y':page.evaluate('scrollY'),
            'first_question_input':opened_question,
            'guidance_open':project_details.evaluate('(element)=>element.open'),
            'editor_precedes_guidance':project_details.evaluate('(element)=>element.previousElementSibling.matches(".casebook-editor")'),
            'input_focused':opened_project.evaluate('(element)=>document.activeElement===element')}
        (args.output/'saved-project-open-layout.json').write_text(json.dumps(opened_layout,indent=2)+'\n')
        (args.output/'saved-project-open-390-geometry.json').write_text(
            json.dumps(phone_geometry(page),indent=2)+'\n')
        assert opened_box and 0 <= opened_box['y'] < opened_box['y']+opened_box['height'] <= 844
        assert opened_layout['scroll_y']==0 and opened_layout['editor_precedes_guidance']
        assert opened_layout['input_focused'] and opened_project.is_enabled()
        assert opened_question and 0 <= opened_question['y'] < opened_question['y']+opened_question['height'] <= 844
        assert not project_details.evaluate('(element)=>element.open')
        page.set_viewport_size({'width':1440,'height':1000})
        saved=page.evaluate("async()=>await sinterBrowser.request('/api/browser/export')")
        assert len(saved['casebooks'])==1
        assert saved['casebooks'][0]['title']=='Fictional garden project - volunteer handover'
        backups=page.locator('#browser-controls>.browser-backups')
        summary=backups.locator('summary').first
        stop=page.get_by_role('button',name='Stop current operation',exact=True,include_hidden=True)
        assert not backups.evaluate('(element)=>element.open')
        assert stop.is_hidden() and stop.is_disabled()
        summary.focus();page.keyboard.press('Enter')
        assert backups.evaluate('(element)=>element.open')
        page.get_by_text('Backups are unencrypted.',exact=False).wait_for()
        assert summary.evaluate('(element)=>document.activeElement===element')
        about=backups.get_by_text('What runs here?',exact=True)
        about.focus();page.keyboard.press('Enter')
        page.get_by_text('Optional search uses the capacity-limited',exact=False).wait_for()
        page.get_by_text('Operating-system features require installed Sinter:',exact=False).wait_for()
        about.focus();page.keyboard.press('Space')
        with page.expect_download() as result:
            page.get_by_role('button',name='Export saved workspace',exact=True).click()
        download=result.value;download.save_as(args.output/'workspace.json')
        exported=json.loads((args.output/'workspace.json').read_text())
        assert exported['casebooks']==saved['casebooks']
        summary.focus();page.keyboard.press('Space')
        assert not backups.evaluate('(element)=>element.open')
        page.screenshot(path=str(args.output/'desktop.png'),full_page=True)
        page.screenshot(path=str(args.output/'desktop-viewport.png'))
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
        queries=[]
        def search_fixture(route):
            query=route.request.post_data_json['query']; queries.append(query)
            route.fulfill(status=200,content_type='application/json',body=json.dumps({
                'retrieved_at':'2026-10-07T00:00:00Z','source_status':'partial',
                'notice':'Fictional fixture: one source engine is unavailable.',
                'results':[{'title':'Fictional garden water guide','url':'https://example.com/garden',
                            'content':'Fictional example: check water access before opening the garden.'}]}))
        context.route('**/v1/search',search_fixture)
        page.get_by_role('link',name='Search the web',exact=True).click()
        page.get_by_label('Search query',exact=True).fill('fictional garden water')
        page.get_by_role('button',name='Search',exact=True).click()
        page.get_by_role('link',name='[1] Fictional garden water guide',exact=True).wait_for(timeout=30000)
        page.get_by_text('Fictional fixture: one source engine is unavailable.',exact=True).wait_for()
        page.get_by_role('button',name='Use these sources in a research brief',exact=True).click()
        page.get_by_label('Research topic',exact=True).wait_for()
        assert page.get_by_label('Research topic',exact=True).input_value() == 'fictional garden water'
        page.get_by_role('button',name='Prepare research brief',exact=True).click()
        page.get_by_role('button',name='Save to My workspace',exact=True).wait_for(timeout=30000)
        assert queries == ['fictional garden water']
        page.get_by_role('button',name='Save to My workspace',exact=True).click()
        assert page.locator('.document-word-save-options').is_hidden()
        page.set_viewport_size({'width':390,'height':844})
        page.goto(args.url+'#home')
        page.get_by_role('heading',name='Your next piece of work starts here.').wait_for(timeout=90000)
        page.screenshot(path=str(args.output/'mobile.png'),full_page=True)
        (args.output/'home-390-geometry.json').write_text(json.dumps(phone_geometry(page),indent=2)+'\n')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
        page.get_by_role('button',name='Open garden handover',exact=True).click()
        project=page.get_by_label('Project name',exact=True)
        project.wait_for(timeout=30000)
        assert project.input_value()=='Fictional garden project - volunteer handover'
        layouts=[]
        for theme in ['light','dark']:
            if page.locator('html').get_attribute('data-theme') != theme:
                page.get_by_role('button',name=f'Switch to {theme} theme',exact=True).click()
            page.wait_for_function('(theme)=>document.documentElement.dataset.theme===theme',arg=theme)
            stop.wait_for(state='hidden',timeout=30000)
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=str(args.output/f'garden-{theme}-390-viewport.png'))
            heading=page.get_by_role('heading',name='Prepare a report from your notes.',exact=True).bounding_box()
            field=project.bounding_box()
            first_question=page.get_by_label('What do you need to find out?',exact=True).bounding_box()
            layout={'theme':theme,'controls':page.locator('#browser-controls').bounding_box(),
                    'heading':heading,'project_input':field,'first_question_input':first_question,
                    'scroll_width':page.evaluate('document.documentElement.scrollWidth'),
                    'viewport_width':390,'viewport_height':844}
            layouts.append(layout)
            (args.output/'phone-layouts.json').write_text(json.dumps(layouts,indent=2)+'\n')
            (args.output/f'garden-{theme}-390-geometry.json').write_text(
                json.dumps(phone_geometry(page),indent=2)+'\n')
            assert heading and 0 <= heading['y'] < heading['y']+heading['height'] <= 844
            assert field and 0 <= field['y'] < field['y']+field['height'] <= 844
            assert layout['scroll_width'] <= 392
            assert first_question and 0 <= first_question['y'] < first_question['y']+first_question['height'] <= 844
            assert not backups.evaluate('(element)=>element.open')
            assert not page.locator('.browser-project-details').evaluate('(element)=>element.open')
        project_details=page.locator('.browser-project-details')
        project_summary=project_details.locator(':scope>summary')
        project_summary.focus();page.keyboard.press('Enter')
        page.get_by_text('Local by default. Sources are not fetched or uploaded automatically.',exact=False).wait_for()
        page.get_by_text('The insurance answer remains unknown.',exact=False).wait_for()
        page.get_by_role('button',name='Open garden campaign',exact=True).wait_for()
        project_summary.focus();page.keyboard.press('Space')
        assert not project_details.evaluate('(element)=>element.open')
        page.set_viewport_size({'width':1440,'height':1000})
        page.evaluate('scrollTo(0,0)')
        page.screenshot(path=str(args.output/'garden-dark-desktop-viewport.png'))
        page.get_by_role('button',name='Switch to light theme',exact=True).click()
        page.wait_for_function("document.documentElement.dataset.theme==='light'")
        stop.wait_for(state='hidden',timeout=30000)
        page.screenshot(path=str(args.output/'garden-light-desktop-viewport.png'))
        snapshot=page.evaluate("async()=>await sinterBrowser.request('/api/browser/export')")
        summary.focus();page.keyboard.press('Enter')
        confirmations=[]
        def answer_confirmation(dialog, expected, accept):
            assert dialog.type=='confirm' and dialog.message==expected
            confirmations.append({'message':dialog.message,'accepted':accept})
            dialog.accept() if accept else dialog.dismiss()
        counts=', '.join(f'{len(exported[key])} {key}' for key in ('casebooks','campaigns','reports','watches'))
        import_prompt=f'Restore {counts}? This replaces the saved browser workspace and discards unsaved editor inputs. Export your current saved workspace and unsaved project backups first. Imported search watches start paused.'
        page.once('dialog',lambda dialog:answer_confirmation(dialog,import_prompt,False))
        with page.expect_file_chooser() as chooser:
            page.get_by_role('button',name='Import workspace backup',exact=True).click()
        chooser.value.set_files(args.output/'workspace.json')
        page.get_by_text('Import cancelled. Your workspace is unchanged.',exact=True).wait_for(timeout=30000)
        recover_prompt='Restore the previous successful save? Newer saved changes and unsaved editor inputs will be discarded. Export them first if possible.'
        page.once('dialog',lambda dialog:answer_confirmation(dialog,recover_prompt,False))
        page.get_by_role('button',name='Recover previous save',exact=True).click()
        unchanged=page.evaluate("async()=>await sinterBrowser.request('/api/browser/export')")
        snapshot.pop('exported_at');unchanged.pop('exported_at')
        assert unchanged==snapshot
        before_rows=page.evaluate("async()=>await sinterBrowser.request('/api/casebooks')")
        def accept_recovery(dialog):
            if dialog.type=='beforeunload':
                confirmations.append({'type':'beforeunload','accepted':True})
                dialog.accept()
            else:
                answer_confirmation(dialog,recover_prompt,True)
        page.on('dialog',accept_recovery)
        page.get_by_role('button',name='Recover previous save',exact=True).click()
        page.get_by_role('button',name='Switch to light theme',exact=True).wait_for(timeout=90000)
        page.remove_listener('dialog',accept_recovery)
        recovered=page.evaluate("async()=>await sinterBrowser.request('/api/browser/export')")
        recovered.pop('exported_at')
        assert recovered['settings']['theme']=='dark'
        expected_recovery=json.loads(json.dumps(snapshot))
        expected_recovery['settings']['theme']='dark'
        assert recovered==expected_recovery
        assert page.evaluate("async()=>await sinterBrowser.request('/api/casebooks')")==before_rows
        backups=page.locator('#browser-controls>.browser-backups')
        stop=page.get_by_role('button',name='Stop current operation',exact=True,include_hidden=True)
        stopped_queries=[];held_routes=[]
        def hold_search(route):
            stopped_queries.append(route.request.post_data_json['query'])
            held_routes.append(route)
        context.route('**/v1/search',hold_search)
        with page.expect_request('**/v1/search'):
            page.evaluate("""()=>{window.stoppedOperation=sinterBrowser.request('/api/search',
              {data:{query:'fictional stopped request'}}).then(
                ()=>({unexpected:true}),error=>({error:error.message}));}""")
        stop.wait_for(state='visible',timeout=15000)
        assert stop.is_enabled() and stop.evaluate('(element)=>!element.closest("details")')
        assert not backups.evaluate('(element)=>element.open')
        page.screenshot(path=str(args.output/'active-stop-desktop-viewport.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate('scrollTo(0,0)')
        page.screenshot(path=str(args.output/'active-stop-390-viewport.png'))
        stop_box=stop.bounding_box()
        assert stop_box and 0 <= stop_box['y'] < stop_box['y']+stop_box['height'] <= 844
        stop_prompt='Stop the browser engine? Saved work is preserved. Unfinished results are discarded; you will need to reload.'
        page.once('dialog',lambda dialog:answer_confirmation(dialog,stop_prompt,False))
        stop.click()
        assert stop.is_visible() and stop.is_enabled()
        page.once('dialog',lambda dialog:answer_confirmation(dialog,stop_prompt,True))
        stop.click()
        stopped=page.evaluate('async()=>await window.stoppedOperation')
        # Release the fictional network fixture after the worker has stopped.
        for route in held_routes: route.abort()
        assert stopped_queries==['fictional stopped request']
        assert stopped['error']=='Stopped. Saved work is preserved. Reload to continue. No request was replayed.'
        assert page.locator('#browser-controls [role="status"]').inner_text()==stopped['error']
        assert stop.is_hidden() and stop.is_disabled()
        page.screenshot(path=str(args.output/'stopped-status-390-viewport.png'))
        assert page.locator('#browser-controls [role="status"]').evaluate(
            '(element)=>element.scrollHeight<=element.clientHeight')
        page.set_viewport_size({'width':1440,'height':1000})
        page.screenshot(path=str(args.output/'stopped-status-desktop-viewport.png'))
        page.reload()
        page.get_by_role('button',name='Switch to light theme',exact=True).wait_for(timeout=90000)
        after_stop=page.evaluate("async()=>await sinterBrowser.request('/api/browser/export')")
        after_stop.pop('exported_at')
        assert after_stop==recovered
        assert stopped_queries==['fictional stopped request']
        assert not forbidden,forbidden
        assert not errors,errors
        (args.output/'receipt.json').write_text(json.dumps({'browser':args.browser,'contract':contract,
            'errors':errors,'forbidden_requests':forbidden,'phone_layouts':layouts,
            'saved_project_open':opened_layout,
            'confirmations':confirmations,'recovery':'previous dark-theme save; complete saved documents and casebook identities unchanged',
            'stop':{'queries':stopped_queries,'result':stopped,'saved_workspace_unchanged':True},
            'passed':True},indent=2)+'\n')
        context.close()
        browser.close()

if __name__=='__main__': main()
