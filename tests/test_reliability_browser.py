"""Execute the browser module rather than only comparing timeout literals."""
import shutil
import subprocess
from pathlib import Path
import pytest

def test_browser_reliability_contract():
    node=shutil.which('node')
    if node is None:
        pytest.skip('Node is required to execute the browser module')
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([node,'--test','tests/reliability_browser.mjs'],cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
