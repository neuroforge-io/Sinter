"""Packaged desktop entry point. Bundles Python; does not require a terminal.

The interface uses the user's browser. The authenticated Quit action stops the
local process. --self-test writes a receipt and performs no external requests.
"""
from __future__ import annotations

import argparse
import json
import logging
import platform
import struct
import sys
import tempfile
import threading
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__, workbench
from .server import make_server


def self_test(destination: str) -> int:
    receipt = {"schema": "sinter-native-test/v1", "version": __version__,
               "system": platform.system(), "machine": platform.machine(),
               "pointer_bits": struct.calcsize('P') * 8, "python": platform.python_version(),
               "frozen": bool(getattr(sys, 'frozen', False)), "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix='sinter-native-test-') as directory:
            server = make_server(port=0, directory=directory)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                base = f'http://127.0.0.1:{server.server_port}'
                with opener.open(base + '/api/session', timeout=10) as response:
                    assert json.load(response)['version'] == __version__
                for route in ('/', '/static/app.js', '/static/style.css'):
                    with opener.open(base + route, timeout=10) as response:
                        assert response.status == 200 and response.read()
                receipt['checks'].append('packaged static assets and loopback HTTP')
                for kind in ('brief', 'grants', 'meeting'):
                    result = workbench.run(workbench.example(kind))
                    assert result['workflow'] == kind
                receipt['checks'].append('three deterministic example workflows')
            finally:
                server.shutdown(); server.app.close(); server.server_close(); thread.join(timeout=5)
        receipt['passed'] = True
    except Exception as exc:
        receipt['passed'] = False
        receipt['error_type'] = type(exc).__name__
        receipt['error'] = str(exc)
    Path(destination).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return 0 if receipt['passed'] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='Sinter')
    parser.add_argument('--self-test', metavar='RECEIPT')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.self_test)
    server = make_server(port=0)
    server.app.desktop_shutdown = server.shutdown
    thread = threading.Thread(target=server.app.scheduler, daemon=True, name='sinter-watches')
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.app.close(); server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
