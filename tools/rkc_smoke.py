"""Actual pinned RKC compilation and HTTP context interoperability; no AI calls."""
from __future__ import annotations
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from sinter import atlas


def main():
    binary = Path(sys.argv[1]).resolve()
    files = [{'name':'garden.py', 'content':'def garden_budget():\n    """Garden budget is proposed; spending has not been approved."""\n    return 0\n'},
             {'name':'notes.md','content':'# Garden planning\nNo spending was approved. Request quotes before a decision.\n'}]
    generated = atlas.compile_collection(files, str(binary), True)
    assert generated['summary']['item_count'] > 0
    result = atlas.context(generated['document'], 'garden')
    assert result['items']
    with tempfile.TemporaryDirectory(prefix='sinter-rkc-real-') as folder:
        root=Path(folder)
        for row in files: (root/row['name']).write_text(row['content'], encoding='utf-8')
        subprocess.run([str(binary),'quickstart', str(root)], check=True, timeout=180)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        with (root/'server.log').open('w') as log:
            process = subprocess.Popen([str(binary), 'serve', '--dir', str(root/'.rkc'), '--addr', f'127.0.0.1:{port}'],
                                       stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            try:
                error=None; document=None
                for _ in range(30):
                    try:
                        document=atlas.retrieve(port, 'garden'); break
                    except ValueError as exc:
                        error=exc; time.sleep(.25)
                if document is None: raise RuntimeError('Actual RKC context failed: '+str(error))
                assert document['schema_version']=='rkc-context/v1'
                assert atlas.context(document, 'garden')['items']
                receipt={'schema':'sinter-rkc-test/v1','passed':True,'rkc_commit':'37a908e9f99cc246d8185bdc202981c0b55e9ef5',
                         'snapshot_id':document['snapshot_id'],'items':len(document['items']),
                         'checks':['selected-file compilation','bundle import','real RKC HTTP context','snapshot header and citation binding','bounded excerpt selection'],
                         'model_calls':0,'qualification_claim':False}
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    output=ROOT/'rkc-artifacts'; output.mkdir(exist_ok=True)
    (output/'compatibility.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__': main()
