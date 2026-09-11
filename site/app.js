/* Public metadata only. No accounts, analytics, private context or automatic downloads. */
const repository = 'https://github.com/neuroforge-io/Sinter';
const system = document.getElementById('system');
const status = document.getElementById('release-status');
const downloads = document.getElementById('downloads');
const platforms = {
  windows: [['x64', 'Most PCs / Intel & AMD 64-bit', 'Windows 10 or newer.'], ['arm64', 'ARM64 PCs', 'For an ARM64 Windows installation.'], ['x86', 'Older PCs / 32-bit', '32-bit build tested under Windows compatibility mode.']],
  darwin: [['arm64', 'Apple Silicon', 'M-series Macs. Ad-hoc signed app; installer is not notarised.'], ['x64', 'Intel Mac', 'Modern 64-bit Intel macOS. No 32-bit macOS build.']],
  linux: [['x64', 'Intel & AMD 64-bit', 'Debian/Ubuntu package. Check the release notes for the glibc baseline.'], ['arm64', 'ARM64', 'For a 64-bit ARM Debian/Ubuntu installation.'], ['x86', 'Intel & AMD 32-bit', '32-bit userspace tested in compatibility mode.'], ['armv7', 'ARMv7 / 32-bit', 'armhf build tested under emulation, not on physical ARMv7 hardware.']]
};
let release = null;
function element(tag, text) { const node = document.createElement(tag); if (text) node.textContent = text; return node; }
function render() {
  downloads.replaceChildren();
  if (!release) return;
  status.textContent = `${release.tag_name} / ${release.prerelease ? 'Community preview' : 'Published release'}`;
  for (const [arch, name, detail] of platforms[system.value]) {
    const suffix = system.value === 'windows' ? '-setup.exe' : system.value === 'darwin' ? '.pkg' : '.deb';
    const asset = release.assets.find(item => typeof item.name === 'string' && item.name.endsWith(`-${system.value}-${arch}${suffix}`));
    const card = element('article'); card.className = 'package';
    card.append(element('strong', name), element('p', detail));
    if (asset && typeof asset.browser_download_url === 'string' && asset.browser_download_url.startsWith(repository+'/releases/download/')) {
      const link = element('a', `Download installer / ${((Number.isFinite(asset.size) ? asset.size : 0)/1048576).toFixed(1)} MB`);
      link.href = asset.browser_download_url; card.append(link);
    } else card.append(element('p', 'No installer for this target in this release. Use the release page for alternatives.'));
    downloads.append(card);
  }
}
system.addEventListener('change', render);
const agent = navigator.userAgent.toLowerCase();
system.value = agent.includes('mac') ? 'darwin' : agent.includes('linux') ? 'linux' : 'windows';
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 10000);
fetch('https://api.github.com/repos/neuroforge-io/Sinter/releases?per_page=10', {credentials:'omit', referrerPolicy:'no-referrer', signal:controller.signal})
  .then(response => { clearTimeout(timeout); if (!response.ok) throw new Error('Release service unavailable'); return response.json(); })
  .then(releases => {
    if (!Array.isArray(releases)) throw new Error('Invalid release metadata');
    release = releases.find(item => !item.draft && typeof item.tag_name === 'string' && /^v\d+\.\d+\.\d+$/.test(item.tag_name) && Array.isArray(item.assets) && item.assets.some(asset => /\.(exe|pkg|deb)$/.test(asset.name)));
    if (!release) throw new Error('No published installer release yet');
    render();
  }).catch(() => { clearTimeout(timeout); status.textContent = 'Downloads are available from the releases page below. Published build availability is checked there.'; });
