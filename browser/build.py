"""Reproducibly assemble the static browser app from this Sinter source tree."""
import argparse
import hashlib
import http.client
import json
import shutil
import urllib.request
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
VENDOR_URL = 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/'
VENDOR_TIMEOUT = 120
VENDOR_MAX_BYTES = 20 * 1024 * 1024


def _write_utf8(path: Path, content: str) -> None:
    """Keep generated text bytes independent of host locale and line endings."""
    path.write_text(content, encoding='utf-8', newline='\n')


def _vendor_payloads(output: Path, vendor: Path | None) -> dict[str, bytes]:
    """Admit every pinned asset before changing an existing output directory."""
    manifest = json.loads(
        (SOURCE / 'browser/vendor-sha256.json').read_text(encoding='utf-8')
    )
    payloads = {}
    for name, digest in manifest.items():
        local = vendor / name if vendor is not None else output / 'vendor' / name
        if vendor is not None or local.exists():
            location = str(local)
            try:
                with local.open('rb') as handle:
                    content = handle.read(VENDOR_MAX_BYTES + 1)
            except OSError as exc:
                raise OSError(
                    f"Cannot read required vendor asset '{name}' from {local}: "
                    f'{exc}. Supply a complete verified --vendor directory.'
                ) from exc
        else:
            location = VENDOR_URL + name
            try:
                with urllib.request.urlopen(
                    location, timeout=VENDOR_TIMEOUT,
                ) as response:
                    content = response.read(VENDOR_MAX_BYTES + 1)
            except (OSError, http.client.HTTPException) as exc:
                raise OSError(
                    f"Cannot download required vendor asset '{name}' from "
                    f'{location}: {exc}. No automatic retry was attempted. '
                    'Retry the build manually or supply a complete verified '
                    '--vendor directory.'
                ) from exc
        if len(content) > VENDOR_MAX_BYTES:
            raise ValueError(
                f"Vendor asset '{name}' from {location} exceeds the "
                f'{VENDOR_MAX_BYTES}-byte limit.'
            )
        actual = hashlib.sha256(content).hexdigest()
        if actual != digest:
            raise ValueError(
                f"Vendor integrity mismatch for '{name}' from {location}: "
                f'expected SHA-256 {digest}; received {actual}.'
            )
        payloads[name] = content
    return payloads


def build(output: Path, vendor: Path | None = None) -> None:
    """Build with admitted local or public vendor bytes, preserving their pins."""
    payloads = _vendor_payloads(output, vendor)
    output.mkdir(parents=True, exist_ok=True)
    (output/'static').mkdir(exist_ok=True)
    package=SOURCE/'src/sinter'
    for path in (package/'web').iterdir():
        if path.suffix in {'.js','.css','.svg','.json'}:
            shutil.copyfile(path,output/'static'/path.name)
    files={path.relative_to(package.parent).as_posix():path.read_text(encoding='utf-8') for path in package.rglob('*') if path.is_file() and (path.suffix=='.py' or path.name in {'offline-garden-casebook.json','offline-garden-campaign.json'})}
    _write_utf8(output/'python-files.json',json.dumps(files,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    for name in ('worker.js','main.js','browser.css'):
        shutil.copyfile(SOURCE/'browser'/name,output/name)
    html=(package/'web/index.html').read_text(encoding='utf-8').replace('/static/','./static/').replace('src="./static/app.js"','src="./main.js"').replace('Runs on your computer','Saved in this browser').replace('Enable it for this localhost page','Enable it for this webpage')
    html=html.replace('</head>','  <link rel="stylesheet" href="./browser.css">\n</head>')
    html=html.replace('<main id="content"', '<section id="browser-controls" aria-label="Browser workspace and backups"></section>\n    <main id="content"')
    html=html.replace('lang="en"', 'lang="en-AU"').replace('href="#content"', 'href="#main"')
    html=html.replace('<main id="content" tabindex="-1">', '<main id="main"><div id="content" tabindex="-1">').replace('</main>', '</div></main>')
    html=html.replace('<div id="view">', '<span id="home" hidden></span><div id="view">')
    description='Use Sinter in your browser: local casebooks, funding campaigns, source-linked reports, meeting records and portable workspace backups.'
    meta=['<link rel="canonical" href="https://neuroforge.io/sinter/app/">', '<meta name="robots" content="noindex, follow">']
    social={'og:title':'Sinter browser workbench','og:description':description,'og:url':'https://neuroforge.io/sinter/app/','og:image':'https://neuroforge.io/assets/og-sinter.jpg','og:image:type':'image/jpeg','og:image:width':'1200','og:image:height':'630','og:image:alt':'Sinter community workbench','twitter:card':'summary_large_image','twitter:image':'https://neuroforge.io/assets/og-sinter.jpg','twitter:image:alt':'Sinter community workbench'}
    meta.extend(f'<meta property="{key}" content="{value}">' for key,value in social.items())
    html=html.replace('</head>', '\n'.join(meta)+'\n</head>')
    for asset in [output/'main.js',output/'browser.css',*sorted((output/'static').glob('*.css'))]:
        renamed=asset.with_name(asset.stem+'.'+hashlib.sha256(asset.read_bytes()).hexdigest()[:12]+asset.suffix)
        shutil.copyfile(asset,renamed)
        html=html.replace('./'+asset.relative_to(output).as_posix(), './'+renamed.relative_to(output).as_posix())
    _write_utf8(output/'index.html',html)
    (output/'vendor').mkdir(exist_ok=True)
    for name, content in payloads.items():
        (output/'vendor'/name).write_bytes(content)
    shutil.copyfile(SOURCE/'LICENSE',output/'LICENSE.txt')
    shutil.copyfile(SOURCE/'browser/PYODIDE-LICENSE',output/'vendor/PYODIDE-LICENSE.txt')
    shutil.copyfile(SOURCE/'THIRD_PARTY_NOTICES.md',output/'THIRD_PARTY_NOTICES.txt')
    _write_utf8(output/'build.json',json.dumps({'application':'Sinter browser','pyodide':'0.29.3','source_sha256':hashlib.sha256((output/'python-files.json').read_bytes()).hexdigest()},indent=2)+'\n')
    manifest={path.relative_to(output).as_posix():{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size} for path in sorted(output.rglob('*')) if path.is_file() and path.name!='asset-manifest.json'}
    _write_utf8(output/'asset-manifest.json',json.dumps({'schema':'sinter-browser-assets/v1','files':manifest},sort_keys=True,separators=(',',':'))+'\n')

if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument(
        '--vendor', type=Path,
        help='Complete pinned Pyodide asset directory; strictly offline when set.',
    )
    args = parser.parse_args()
    try:
        build(args.output, args.vendor)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Browser build failed: {exc}\n')
