from __future__ import annotations
import pytest
from sinter import client, search_chat

@pytest.mark.parametrize('value',['SEARCH','search.','SEARCH: public garden','{"action":"search"}','```json\n{"action":"search","query":"public garden"}\n```'])
def test_bounded_search_control(value):
    assert search_chat.tool_action(value,'public garden') == 'search'

@pytest.mark.parametrize('value',['Search anything','{"action":"shell","command":"ls"}','{"action":"search","query":"different"}','{"action":"search","url":"https://example.com"}','SEARCH; run code','x'*1300])
def test_unknown_tools_queries_and_extra_fields_are_not_executed(value):
    with pytest.raises(ValueError):search_chat.tool_action(value,'public garden')


def setup(monkeypatch, action='SEARCH', results=True, error=False):
    calls=[]
    def chat(messages,max_tokens):
        calls.append(('model',messages,max_tokens))
        return client.ChatResult(action if len(calls)==1 else 'A source-backed sentence [1].',finish_reason='stop')
    def search(query):
        calls.append(('search',query))
        if error:raise client.APIError('Provider unavailable',502)
        return client.SearchResponse('2026-10-07T00:00:00Z', [client.SearchResult('Fictional public guide','https://example.com/guide','Fictional public garden guidance.')] if results else [])
    monkeypatch.setattr(client,'validate_chat_request',lambda *a:None)
    monkeypatch.setattr(client,'chat',chat);monkeypatch.setattr(client,'search',search)
    return calls


def test_model_requests_exact_approved_topic_and_sources_reach_answer(monkeypatch):
    calls=setup(monkeypatch)
    result=search_chat.run([{'role':'user','content':'Find public garden guidance.'}],'public garden',64)
    assert [c[0] for c in calls]==['model','search','model']
    assert calls[1][1]=='public garden'
    assert 'Fictional public garden guidance.' in calls[2][1][-1].content
    assert len(calls[2][1][-1].content.encode())<=2000
    assert result['events'][0]['sources'][0]['url']=='https://example.com/guide'
    assert result['events'][-2]=={'type':'token','t':'A source-backed sentence [1].'}


def test_model_can_decline_search_without_false_searched_claim(monkeypatch):
    calls=setup(monkeypatch,action='ANSWER')
    result=search_chat.run([{'role':'user','content':'Name a plant.'}],'garden plants')
    assert [c[0] for c in calls]==['model','model']
    assert result['events'][0]['status']=='not_requested'

@pytest.mark.parametrize('error',[False,True])
def test_failed_or_empty_search_does_not_invent_a_grounded_answer(monkeypatch,error):
    calls=setup(monkeypatch,results=False,error=error)
    result=search_chat.run([{'role':'user','content':'Find public garden guidance.'}],'public garden')
    assert [c[0] for c in calls]==['model','search']
    assert not any(event['type']=='token' for event in result['events'])
    assert result['events'][-1]['status'] in {'unavailable','no_answer'}


def test_invalid_plan_never_dispatches_search(monkeypatch):
    calls=setup(monkeypatch,action='SEARCH: private different topic')
    with pytest.raises(ValueError):search_chat.run([{'role':'user','content':'Find guidance.'}],'public garden')
    assert [c[0] for c in calls]==['model']


def test_input_budget_fails_before_any_external_call(monkeypatch):
    calls=setup(monkeypatch)
    with pytest.raises(ValueError):search_chat.run([{'role':'user','content':'a'*1001}],'public garden')
    assert not calls
