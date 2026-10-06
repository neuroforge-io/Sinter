"""Reproducibly assemble the static browser app from this Sinter source tree."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
VENDOR_URL = 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/'

def build(output, vendor=None):
    output.mkdir(parents=True, exist_ok=True)
    (output/'static').mkdir(exist_ok=True)
    package=SOURCE/'src/sinter'
    for path in (package/'web').iterdir():
        if path.suffix in {'.js','.css','.svg','.json'}:
            shutil.copyfile(path,output/'static'/path.name)
    files={str(path.relative_to(package.parent)):path.read_text() for path in package.rglob('*') if path.is_file() and (path.suffix=='.py' or path.name in {'offline-garden-casebook.json','offline-garden-campaign.json'})}
    (output/'python-files.json').write_text(json.dumps(files,ensure_ascii=False,separators=(',',':')))
    for name in ('worker.js','main.js','browser.css'):
        shutil.copyfile(SOURCE/'browser'/name,output/name)
    html=(package/'web/index.html').read_text().replace('/static/','./static/').replace('src="./static/app.js"','src="./main.js"').replace('Runs on your computer','Saved in this browser').replace('Enable it for this localhost page','Enable it for this webpage')
    html=html.replace('</head>','  <link rel="stylesheet" href="./browser.css">\n</head>')
    html=html.replace('<main id="content"', '<section id="browser-controls" aria-label="Browser workspace and backups"></section>\n    <main id="content"')
    html=html.replace('lang="en"', 'lang="en-AU"').replace('href="#content"', 'href="#main"')
    html=html.replace('<main id="content" tabindex="-1">', '<main id="main"><div id="content" tabindex="-1">').replace('</main>', '</div></main>')
    html=html.replace('<div id="view">', '<span id="home" hidden></span><div id="view">')
    description='Use Sinter in your browser: local casebooks, funding campaigns, source-linked reports, meeting records and portable workspace backups.'
    meta=['<link rel="canonical" href="https://neuroforge.io/sinter/app/">']
    social={'og:title':'Sinter browser workbench','og:description':description,'og:url':'https://neuroforge.io/sinter/app/','og:image':'https://neuroforge.io/assets/og-sinter.jpg','og:image:type':'image/jpeg','og:image:width':'1200','og:image:height':'630','og:image:alt':'Sinter community workbench','twitter:card':'summary_large_image','twitter:image':'https://neuroforge.io/assets/og-sinter.jpg','twitter:image:alt':'Sinter community workbench'}
    meta.extend(f'<meta property="{key}" content="{value}">' for key,value in social.items())
    html=html.replace('</head>', '\n'.join(meta)+'\n</head>')
    for asset in [output/'main.js',output/'browser.css',*sorted((output/'static').glob('*.css'))]:
        renamed=asset.with_name(asset.stem+'.'+hashlib.sha256(asset.read_bytes()).hexdigest()[:12]+asset.suffix)
        shutil.copyfile(asset,renamed)
        html=html.replace('./'+asset.relative_to(output).as_posix(), './'+renamed.relative_to(output).as_posix())
    (output/'index.html').write_text(html)
    (output/'vendor').mkdir(exist_ok=True)
    manifest=json.loads((SOURCE/'browser/vendor-sha256.json').read_text())
    for name,digest in manifest.items():
        local=vendor/name if vendor else output/'vendor'/name
        if not local.exists():
            with urllib.request.urlopen(VENDOR_URL+name,timeout=120) as response: content=response.read(20*1024*1024)
        else: content=local.read_bytes()
        if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Vendor integrity mismatch: '+name)
        (output/'vendor'/name).write_bytes(content)
    shutil.copyfile(SOURCE/'LICENSE',output/'LICENSE.txt')
    shutil.copyfile(SOURCE/'browser/PYODIDE-LICENSE',output/'vendor/PYODIDE-LICENSE.txt')
    shutil.copyfile(SOURCE/'THIRD_PARTY_NOTICES.md',output/'THIRD_PARTY_NOTICES.txt')
    (output/'build.json').write_text(json.dumps({'application':'Sinter browser','pyodide':'0.29.3','source_sha256':hashlib.sha256((output/'python-files.json').read_bytes()).hexdigest()},indent=2)+'\n')
    manifest={str(path.relative_to(output)):{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size} for path in sorted(output.rglob('*')) if path.is_file() and path.name!='asset-manifest.json'}
    (output/'asset-manifest.json').write_text(json.dumps({'schema':'sinter-browser-assets/v1','files':manifest},sort_keys=True,separators=(',',':'))+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('--vendor',type=Path)
    args=parser.parse_args();build(args.output,args.vendor)
