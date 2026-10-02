# RC4 owned relay cancellation

The hosted Windows 3.10 and 3.13 source run at
`3fe344a52cf06d3bb745f4002892b277ab853c2e` returned success from both socket
shutdown attempts while one real idle TCP request worker remained in `recv`.
Cleanup correctly refused with one worker and one owned socket still live. This
was an actual source qualification failure, not an installed-app crash.

Tracked RC4 relay request reads now poll for readability and an owned stop event.
The existing per-request timeout and five-second cleanup deadline stay unchanged.
The stop event is set before socket shutdown and listener closure. Idle and partial
requests stop without forwarding their incomplete bytes or creating a successful
response. Existing untracked relay reads retain their direct socket behavior.

Source controls use actual owned loopback sockets, including an explicitly
ineffective shutdown seam, literal Unicode/binary bytes, EOF, request timeouts,
stopped-before-read refusal and unchanged legacy transport. That seam demonstrates
cooperative cancellation independently of shutdown waking a reader; it does not
prove that the fix passes Windows. The exact hosted Windows regression must pass
before that claim. No physical application, customer data, model, installer or
release is used by these controls.

An independent source critic held the first proposal: one spurious readiness
return plus cancellation immediately before the actual read left the worker and
socket alive after 5.0202 seconds. The original proposal and full failed record
remain unchanged. The separate correction makes the admitted read nonblocking
and restores its original timeout after data, EOF, stale readiness or failure.
If restoration also fails after a genuine read failure, the original exception
object retains the later restoration error. This prevents a readiness/stop race
from starting another long blocking receive; it does not weaken the original
request timeout or establish an actual Windows pass.

The second independent review retained a further refusal: data and genuine
shutdown EOF could return after the stop event and start an upstream response
wait. Both original records retained one worker and one socket after the unchanged
five-second cleanup deadline. The original proposals, raw refusal streams and
explicit inert-sink cleanup records remain historical evidence.

The separate third proposal checks cancellation after each immediate operation
and timeout restoration, before admitting a result. It also applies cooperative
reads, partial writes and connection waits to both sides of tracked relays. Each
operation retains its original timeout budget; a partial send does not start a
new budget. Every syscall admitted after readiness is nonblocking, so stale
readiness cannot start another twenty-second wait. First exceptions retain later
timeout restoration or socket-close errors. Existing untracked relays keep the
same direct socket operations and fixed loopback targets.

Source controls cover actual late bytes/EOF, stalled upstream responses, client
backpressure, original timeout expiry and a complete tracked TCP/Unix/TCP raw-byte
exchange. They inspect closure of actual upstream descriptors as well as request
workers. A write already admitted when cancellation arrives can have sent some
bytes; its outcome remains uncertain and is never replayed automatically. These
controls use inert local sinks and do not establish an installed application,
hosted Windows, model, or release pass.

The third proposal was also held by independent review. An actual full Unix-domain
listen queue returned EAGAIN from the connect syscall. The proposed connection
helper then treated writability and SO_ERROR=0 as success even though the socket
was unconnected. Both that failure and the earlier proposals remain unchanged.

The fourth correction uses the immediate nonblocking connect syscall and keeps
its original exception object. A full Unix-domain queue retains its actual EAGAIN
refusal; it is not reinterpreted as a pending TCP connection. Pending connections
still wait cooperatively within the original timeout, and a zero socket error is
admitted only after the socket reports a connected peer. Later timeout restoration
errors remain attached to the first failure. Source controls retain the actual
Linux default-queue refusal and closed descriptors, with a separate genuine
restoration interruption. This is source evidence, not installed or Windows
qualification. The legacy untracked connection path remains unchanged.

Current-main composition preserves its ClosingRequest wrapper and original
framing policy: an idle preconnect closes without an error, while interrupted
partial headers or bodies remain failed requests. The wrapper delegates to the
cooperative tracked reader and maps cancellation to EOF for that same parser.
The inherited closing event is shared by the wrapper and tracked operations.
The direct standalone wrapper behavior, accepted native diagnostic publisher,
and five-second cleanup remain intact. Independent source review accepts this composition. Actual hosted and installed
qualification remain required.
