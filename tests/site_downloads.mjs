import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const repository = 'https://github.com/neuroforge-io/Sinter';
const nodes = new Map();
function node(tag = 'div') {
  return {tag, children: [], textContent: '',
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.textContent = ''; this.children = children; },
    addEventListener() {},
  };
}
const system = node('select');
system.options = [{text: 'Windows'}, {text: 'macOS'}, {text: 'Linux'}];
Object.defineProperty(system, 'selectedIndex', {get() { return ['windows', 'darwin', 'linux'].indexOf(this.value); }});
nodes.set('system', system);
for (const id of ['release-status', 'downloads']) nodes.set(id, node());
const context = vm.createContext({document: {
  getElementById: id => nodes.get(id), createElement: node,
  createTextNode: text => ({textContent: text, children: []}),
}, navigator: {userAgent: 'Linux'}, AbortController,
fetch: () => new Promise(() => {}), setTimeout: () => 1, clearTimeout() {}});
vm.runInContext(readFileSync(new URL('../site/app.js', import.meta.url), 'utf8') + `
globalThis.siteFixture = {releaseVersion, newestRelease, installerAsset,
  renderDownloads(value, platform) { release = value; system.value = platform; render(); }};`, context);
const site = context.siteFixture;
const contents = value => value.textContent + value.children.map(contents).join('');
const links = value => [...(value.tag === 'a' ? [value] : []), ...value.children.flatMap(links)];
const asset = (tag, platform = 'linux', arch = 'x64') => {
  const suffix = platform === 'windows' ? '-setup.exe' : platform === 'darwin' ? '.pkg' : '.deb';
  const name = `Sinter-${tag.slice(1)}-${platform}-${arch}${suffix}`;
  return {name, size: 13034874, browser_download_url: `${repository}/releases/download/${tag}/${name}`};
};
const published = (tag, assets = [asset(tag)]) => ({tag_name: tag, draft: false,
  prerelease: true, assets});

test('release tags admit canonical stable and rc versions only', () => {
  for (const tag of ['v0.5.3', 'v0.5.4rc1', 'v0.5.4rc10', 'v1.0.0']) assert.ok(site.releaseVersion(tag));
  for (const tag of [null, 5, '', '0.5.4rc1', 'v0.05.4', 'v0.5.04', 'v0.5.4rc0',
    'v0.5.4rc01', 'v0.5.4-rc1', 'v0.5.4RC1', 'v0.5.4rc1.dev0', 'v0.5.4+private',
    'v0.5.4/../../other', 'v0.5.4\n', 'v' + '9'.repeat(65) + '.0.0']) {
    assert.equal(site.releaseVersion(tag), null, String(tag));
  }
});

test('current preview wins across metadata order without changing the input list', () => {
  const older = published('v0.5.3'), current = published('v0.5.4rc1');
  const input = [older, current], before = JSON.stringify(input);
  assert.equal(site.newestRelease(input), current);
  assert.equal(JSON.stringify(input), before);
  assert.equal(site.newestRelease([current, older]), current);
  assert.equal(site.newestRelease([current, published('v0.5.4rc2')]).tag_name, 'v0.5.4rc2');
  assert.equal(site.newestRelease([published('v0.5.4'), published('v0.5.4rc10')]).tag_name, 'v0.5.4');
  assert.equal(site.newestRelease([published('v0.9.9'), published('v0.10.0rc1')]).tag_name, 'v0.10.0rc1');
});

test('draft, malformed and incorrectly promoted rc records are excluded', () => {
  const valid = published('v0.5.3');
  assert.equal(site.newestRelease([null, {}, {...published('v9.0.0'), draft: true},
    {...published('v8.0.0'), draft: 'false'}, {...published('v7.0.0'), prerelease: 'true'},
    {...published('v6.0.0rc1'), prerelease: false}, published('v5.0.0rc01'), valid]), valid);
  for (const input of [null, {}, [], [{tag_name: 'v0.5.4rc1'}]]) assert.throws(() => site.newestRelease(input));
});

test('missing or unusable current installers never select an older platform package', () => {
  const older = published('v0.5.3', [asset('v0.5.3', 'windows')]);
  const current = published('v0.5.4rc1');
  assert.equal(site.newestRelease([older, current]), current);
  assert.equal(site.installerAsset(current, 'windows', 'x64'), null);
  assert.equal(site.installerAsset(current, 'darwin', 'arm64'), null);
  assert.equal(site.newestRelease([older, published('v0.5.4rc1', [])]).tag_name, 'v0.5.4rc1');
  assert.throws(() => site.newestRelease([older, {...current, assets: null}]));
});

test('installer names and URLs must match the exact selected release and target', () => {
  const current = published('v0.5.4rc1'), expected = current.assets[0];
  assert.equal(site.installerAsset(current, 'linux', 'x64'), expected);
  const wrong = [asset('v0.5.3'), {...expected, name: 'Other-0.5.4rc1-linux-x64.deb'},
    {...expected, browser_download_url: `${repository}/releases/download/v0.5.3/${expected.name}`},
    ...['http://github.com/neuroforge-io/Sinter', 'https://github.com/other/Sinter',
      'https://github.com.evil.invalid/neuroforge-io/Sinter', 'https://evil.invalid'].map(prefix =>
      ({...expected, browser_download_url: `${prefix}/releases/download/v0.5.4rc1/${expected.name}`})),
    ...['?redirect=evil', '#fragment', '/extra', '%2Fother'].map(suffix =>
      ({...expected, browser_download_url: expected.browser_download_url + suffix})),
    ...[0, -1, 1.5, NaN, '13034874'].map(size => ({...expected, size}))];
  for (const item of wrong) assert.equal(site.installerAsset({...current, assets: [null, {}, item]}, 'linux', 'x64'), null);
  assert.equal(site.installerAsset(current, 'other', 'x64'), null);
  assert.equal(site.installerAsset(current, 'linux', 'other'), null);
});

test('Linux-only preview renders one current installer and explicit absent targets', () => {
  const current = published('v0.5.4rc1');
  site.renderDownloads(current, 'linux');
  assert.equal(links(nodes.get('downloads')).length, 1);
  assert.equal(links(nodes.get('downloads'))[0].href, current.assets[0].browser_download_url);
  assert.match(contents(nodes.get('release-status')), /v0.5.4rc1 \/ Community preview/);
  assert.equal(links(nodes.get('release-status'))[0].href, `${repository}/releases/tag/v0.5.4rc1`);
  assert.match(contents(nodes.get('downloads')), /No Linux arm64 installer is available here for v0.5.4rc1/);
  for (const [platform, label] of [['windows', 'Windows'], ['darwin', 'macOS']]) {
    site.renderDownloads(current, platform);
    assert.equal(links(nodes.get('downloads')).length, 0);
    assert.match(contents(nodes.get('downloads')), new RegExp(`No ${label} .* installer is available here for v0.5.4rc1`));
    assert.match(contents(nodes.get('downloads')), /qualified targets; earlier previews/);
    assert.doesNotMatch(contents(nodes.get('downloads')), /tested under|build tested|M-series Macs/);
  }
});

test('the prior preview retains exact installer links when it is the selected version', () => {
  const legacy = published('v0.5.3', [asset('v0.5.3', 'windows'), asset('v0.5.3', 'darwin', 'arm64')]);
  site.renderDownloads(legacy, 'windows');
  assert.equal(links(nodes.get('downloads')).length, 1);
  assert.equal(links(nodes.get('downloads'))[0].href, legacy.assets[0].browser_download_url);
  site.renderDownloads(legacy, 'darwin');
  assert.equal(links(nodes.get('downloads')).length, 1);
  assert.equal(links(nodes.get('downloads'))[0].href, legacy.assets[1].browser_download_url);
});
