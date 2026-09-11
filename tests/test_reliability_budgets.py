"""Clock-controlled regressions: queue time is not socket idle time."""
import io
from unittest.mock import patch
import pytest
from sinter import client

def test_operation_budgets_are_distinct_and_bounded():
    assert client._request_timeout('/models', None) == 10
    assert client._request_timeout('/search', {'query':'hello'}) == 30
    assert client._request_timeout('/chat/completions', {}) == 120
    assert client._request_timeout('/chat/completions', {'stream':True}) == 30
    assert client.STREAM_DEADLINE == 660

def test_slow_stream_beyond_old_cutoff_finishes_without_retry():
    now=[0.0]
    class Slow(io.BytesIO):
        def readline(self, limit=-1):
            now[0] += 45
            return super().readline(limit)
    raw=b': keep-alive\n\ndata: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    with patch.object(client.time,'monotonic',side_effect=lambda:now[0]), patch.object(client,'_post_raw',return_value=Slow(raw)) as send:
        assert ''.join(client.chat_stream([client.Message('user','hello')]))=='Hello'
        assert now[0] > 120
        send.assert_called_once()

def test_keepalive_never_resets_absolute_deadline():
    now=[0.0]
    class Heartbeats(io.BytesIO):
        def readline(self, limit=-1):
            now[0] += 100
            return b': keep-alive\n'
    with patch.object(client.time,'monotonic',side_effect=lambda:now[0]), pytest.raises(client.APIError,match='overall time budget'):
        list(client._events(Heartbeats()))

def test_late_eof_cannot_turn_expired_pending_data_into_success():
    now=[0.0]
    class LateEOF(io.BytesIO):
        def readline(self, limit=-1):
            now[0]=661
            return b''
    with patch.object(client.time,'monotonic',side_effect=lambda:now[0]), pytest.raises(client.APIError,match='overall time budget'):
        list(client._events(LateEOF(),deadline=660))

def test_buffered_generation_uses_larger_network_timeout_without_retries():
    with patch.object(client.urllib.request,'build_opener') as opener:
        client._open('/chat/completions',{'messages':[]})
        opener.return_value.open.assert_called_once()
        assert opener.return_value.open.call_args.kwargs['timeout']==120

def test_stream_negotiates_sse_and_retains_short_idle_timeout():
    with patch.object(client.urllib.request,'build_opener') as opener:
        client._open('/chat/completions',{'stream':True})
        args=opener.return_value.open.call_args
        assert args.args[0].get_header('Accept')=='text/event-stream'
        assert args.kwargs['timeout']==30
