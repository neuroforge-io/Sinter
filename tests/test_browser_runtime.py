"""Use the same test cases on CPython and the shipped Pyodide interpreter."""
import copy
import json
from pathlib import Path

from sinter import browser_runtime as b


def call(path, data=None, expect=200):
    value = {"path": path}
    if data is not None:
        value["data"] = data
    result = json.loads(b.request(json.dumps(value)))
    assert result["status"] == expect, result
    return result["result"]


def exercise(directory):
    b.ROOT = Path(directory)
    b.app = b.BrowserApplication(directory)
    garden = call('/api/practice/garden')
    saved = call('/api/casebooks/save', {'document': garden['casebook']})
    assert saved['revision'] == 1
    loaded = call('/api/casebooks/' + saved['id'])
    assert loaded['document'] == saved['document']
    job = call('/api/casebooks/build', {'id': saved['id'], 'revision': 1}, expect=202)
    report = call('/api/jobs/' + job['id'])
    assert report['status'] == 'done', report
    assert 'insurance' in report['result']['markdown'].lower()
    report_id = call('/api/reports', {'report': report['result']}, expect=201)['id']
    assert call('/api/reports/' + report_id)['title']
    campaign = call('/api/campaigns/save', {'document': garden['campaign']})
    assert call('/api/campaigns/' + campaign['id'])['document'] == campaign['document']
    prepared = call('/api/campaigns/prepare', {'document': campaign['document']})
    assert prepared
    for workflow in ['brief', 'grants', 'meeting', 'research']:
        example = call('/api/example?workflow=' + workflow)
        example.update(use_search=False, use_model=False)
        job = call('/api/workbench', example, expect=202)
        result = call('/api/jobs/' + job['id'])
        assert result['status'] == 'done', (workflow, result)
        assert result['result']['markdown']
    comparison = call('/api/community/compare', {'before':'First wording\n', 'after':'Changed wording\n'})
    assert comparison
    call('/api/transcript/inspect', {'text':'Alex: We need the quote.\nSam: It has not arrived.'})
    watch = call('/api/watches', {'title':'Fictional watch','query':'community grants','interval':86400,'consent':True}, expect=201)
    snapshot = call('/api/browser/export')
    assert len(snapshot['casebooks']) == len(snapshot['campaigns']) == len(snapshot['reports']) == 1
    assert 'api_key' not in json.dumps(snapshot)
    original = copy.deepcopy(snapshot)
    invalid = copy.deepcopy(snapshot); invalid['casebooks'][0]['schema'] = 'unknown/future'
    call('/api/browser/import/preview', {'document':invalid}, expect=400)
    call('/api/browser/import', {'document':invalid,'confirm':True}, expect=400)
    after = call('/api/browser/export');after.pop('exported_at');original.pop('exported_at');assert after == original
    counts = call('/api/browser/import/preview', {'document':snapshot})
    assert counts['casebooks'] == 1
    call('/api/browser/import', {'document':snapshot}, expect=400)
    call('/api/browser/import', {'document':snapshot,'confirm':True})
    assert call('/api/watches')['watches'][0]['enabled'] == 0
    call('/api/settings', {'settings':{'api_url':'https://example.invalid/v1'}}, expect=400)
    call('/api/settings', {'settings':{'theme':'light'}})
    assert call('/api/settings')['settings']['theme'] == 'light'
    for route in ['/api/atlas/compile','/api/atlas/retrieve','/api/transcribe','/api/account/connect','/api/documents/docx/save','/api/desktop/quit']:
        call(route, {}, expect=400)
    assert not call('/api/speech')['available']
    print('BROWSER DOMAIN CONTRACT PASSED: casebooks, campaigns, 4 report workflows, local saves, import rollback, watch pause, settings, OS capability guards')


def test_browser_domain_contract(tmp_path):
    exercise(tmp_path)
