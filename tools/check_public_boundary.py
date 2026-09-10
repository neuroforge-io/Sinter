"""Narrow release guard: no bundled weights/private-key material or inline UI scripts.

Not a forensic history audit, a comprehensive secret scanner or legal advice.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    failures = []
    for path in (ROOT / 'src').rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        if path.suffix.lower() in {'.safetensors', '.gguf', '.pt', '.pth', '.onnx', '.ckpt'}:
            failures.append(f'Unexpected model artifact: {path.relative_to(ROOT)}')
        if path.suffix in {'.py', '.js', '.html', '.css'}:
            text = path.read_text(encoding='utf-8')
            if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text):
                failures.append(f'Private key material: {path.relative_to(ROOT)}')
            if path.suffix == '.js' and re.search(r'\.innerHTML\s*=', text):
                failures.append(f'Unsafe HTML assignment: {path.relative_to(ROOT)}')
    index = (ROOT / 'src/sinter/web/index.html').read_text(encoding='utf-8')
    if re.search(r'\son\w+\s*=', index) or re.search(r'<script(?![^>]*\bsrc=)[^>]*>', index):
        failures.append('Inline script or event handler in the UI entry point')
    if 'Apache License' not in (ROOT / 'LICENSE').read_text(encoding='utf-8'):
        failures.append('Missing Apache license')
    if 'license = "Apache-2.0"' not in (ROOT / 'pyproject.toml').read_text(encoding='utf-8'):
        failures.append('Package license metadata does not match Apache-2.0')
    if failures:
        raise SystemExit('\n'.join(failures))
    print('PASS: narrow public-boundary and safe-UI release checks')


if __name__ == '__main__':
    main()
