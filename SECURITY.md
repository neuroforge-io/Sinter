# Security and privacy

Sinter is a local, single-user workbench, not an internet-facing multi-user service.
Do not expose its HTTP listener publicly. Keep session tokens private. Saved work,
exports and checkpoints are unencrypted and may contain sensitive source material.

Review admitted content before authorising an API transfer. Filename/content checks
are heuristic and cannot certify that data is secret-free. Optional providers have
their own retention, access, availability and charging policies. An uncertain remote
result must not be automatically replayed; explicit retries may duplicate processing.

For a sensitive vulnerability, use GitHub's private vulnerability reporting option
when available. Otherwise contact the repository maintainer privately through a
verified contact route before sharing details. Do not post secrets, personal data
or a live exploit against the public service in a public issue. Rotate exposed
credentials through their provider; deleting a report does not revoke a credential.

Include the Sinter version, affected component and a minimal fictional reproduction.
This community project does not promise a response-time SLA or independent security
audit. Public-boundary checks, secret heuristics and passing CI are limited checks,
not security certification.
