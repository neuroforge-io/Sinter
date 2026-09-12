"""Offline dogfood audit, with a separate opt-in model review via the CLI.

This tests collection admission, retrieval provenance, coverage and module inputs;
it does not establish the absence of source bugs or independently review code.
"""
from pathlib import Path
import hashlib
import json
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sinter import casebooks, review, workbench
from sinter.evidence import validate_excerpt, Excerpt, Source

root = Path(__file__).resolve().parents[1]
started = time.monotonic()
collection, admission = review.load_collection(root / 'src')
collection['title'] = 'Sinter source and community workflow self-audit'
collection['questions'] = 'How are timeouts and cancellation handled?\nWhere are original sources and corrections retained?\nWhat grant eligibility remains unknown?\nHow are API keys protected?'
result = casebooks.build(collection)
for excerpt in result['excerpts']:
    assert validate_excerpt(Excerpt(**excerpt), [Source(**source) for source in result['sources']])
ledger = review.run(collection, offline=True)
for kind in workbench.WORKFLOWS:
    assert workbench.run(workbench.example(kind))['workflow'] == kind
receipt = {'schema': 'sinter-self-audit/v1', 'passed': True, 'network_requests': 0,
           'scope': 'Deterministic collection/provenance and fictional workflow integration; not an independent code audit.',
           'admission': admission, 'coverage': result['coverage'], 'review_coverage': ledger['coverage'],
           'source_fingerprint': result['casebook_fingerprint'], 'seconds': round(time.monotonic() - started, 4)}
output = root / 'self-audit-artifacts'; output.mkdir(exist_ok=True)
(output / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
(output / 'report.md').write_text(result['markdown'], encoding='utf-8')
print(json.dumps(receipt, indent=2))
