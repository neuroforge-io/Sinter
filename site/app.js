/* Public metadata only. No accounts, analytics, private context or automatic downloads. */
const repository = 'https://github.com/neuroforge-io/Sinter';
const system = document.getElementById('system');
const status = document.getElementById('release-status');
const downloads = document.getElementById('downloads');
const platforms = {
  windows: [['x64', 'Most PCs / Intel & AMD 64-bit', 'For a 64-bit Windows installation.'], ['arm64', 'ARM64 PCs', 'For an ARM64 Windows installation.'], ['x86', 'Older PCs / 32-bit', 'For a 32-bit Windows installation.']],
  darwin: [['arm64', 'Apple Silicon', 'For M-series Macs.'], ['x64', 'Intel Mac', 'For 64-bit Intel macOS.']],
  linux: [['x64', 'Intel & AMD 64-bit', 'Debian/Ubuntu package.'], ['arm64', 'ARM64', 'For a 64-bit ARM Debian/Ubuntu installation.'], ['x86', 'Intel & AMD 32-bit', 'For a 32-bit Debian/Ubuntu installation.'], ['armv7', 'ARMv7 / 32-bit', 'For an ARMv7 Debian/Ubuntu installation.']]
};
let release = null;
function element(tag, text) { const node = document.createElement(tag); if (text) node.textContent = text; return node; }

function releaseVersion(tag) {
  if (typeof tag !== 'string' || tag.length > 64) return null;
  const match = /^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:rc([1-9]\d*))?$/.exec(tag);
  return match ? {parts: match.slice(1, 4).map(BigInt), rc: match[4] ? BigInt(match[4]) : null} : null;
}

function newestRelease(releases) {
  if (!Array.isArray(releases)) throw new Error('Invalid release metadata');
  const published = releases.filter(item => {
    const version = releaseVersion(item?.tag_name);
    return version && item.draft === false && typeof item.prerelease === 'boolean'
      && (version.rc === null || item.prerelease === true);
  });
  published.sort((left, right) => {
    const a = releaseVersion(left.tag_name), b = releaseVersion(right.tag_name);
    for (let index = 0; index < a.parts.length; index++) {
      if (a.parts[index] !== b.parts[index]) return a.parts[index] > b.parts[index] ? -1 : 1;
    }
    if (a.rc === b.rc) return 0;
    if (a.rc === null) return -1;
    if (b.rc === null) return 1;
    return a.rc > b.rc ? -1 : 1;
  });
  const selected = published[0];
  if (!selected || !Array.isArray(selected.assets)) throw new Error('Installer metadata unavailable');
  return selected;
}

function installerAsset(selected, platform, arch) {
  if (!releaseVersion(selected?.tag_name) || !Array.isArray(selected.assets)
      || !platforms[platform]?.some(([value]) => value === arch)) return null;
  const suffix = platform === 'windows' ? '-setup.exe' : platform === 'darwin' ? '.pkg' : '.deb';
  const name = `Sinter-${selected.tag_name.slice(1)}-${platform}-${arch}${suffix}`;
  const url = `${repository}/releases/download/${selected.tag_name}/${encodeURIComponent(name)}`;
  return selected.assets.find(item => item?.name === name && item.browser_download_url === url
    && Number.isSafeInteger(item.size) && item.size > 0) || null;
}

function render() {
  downloads.replaceChildren();
  if (!release) return;
  const notes = element('a', 'Release notes, checksums and qualification');
  notes.href = `${repository}/releases/tag/${release.tag_name}`;
  status.replaceChildren(document.createTextNode(`${release.tag_name} / ${release.prerelease ? 'Community preview' : 'Published release'}. `), notes);
  for (const [arch, name, detail] of platforms[system.value] || []) {
    const asset = installerAsset(release, system.value, arch);
    const card = element('article'); card.className = 'package';
    card.append(element('strong', name));
    if (asset) {
      card.append(element('p', `${detail} Check this version’s release notes for tested systems and installation requirements.`));
      const link = element('a', `Download ${release.tag_name} installer / ${(asset.size/1048576).toFixed(1)} MB`);
      link.href = asset.browser_download_url; card.append(link);
    } else card.append(element('p', `No ${system.options[system.selectedIndex]?.text || system.value} ${arch} installer is available here for ${release.tag_name}. Check this version’s release notes for qualified targets; earlier previews remain on the all-releases page.`));
    downloads.append(card);
  }
}
system.addEventListener('change', render);
const agent = navigator.userAgent.toLowerCase();
system.value = agent.includes('mac') ? 'darwin' : agent.includes('linux') ? 'linux' : 'windows';
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 10000);
fetch('https://api.github.com/repos/neuroforge-io/Sinter/releases?per_page=10', {credentials:'omit', referrerPolicy:'no-referrer', signal:controller.signal})
  .then(response => { if (!response.ok) throw new Error('Release service unavailable'); return response.json(); })
  .then(releases => {
    release = newestRelease(releases);
    render();
    clearTimeout(timeout);
  }).catch(() => { clearTimeout(timeout); release = null; downloads.replaceChildren(); status.textContent = 'Download metadata could not be checked. Use the releases page below to review available versions, checksums and build qualification.'; });
