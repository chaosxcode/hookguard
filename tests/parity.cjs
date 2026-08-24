/* Parity harness: python scan.py vs browser JS port on identical inputs.
 * Run: node tests/parity.mjs   (exits 1 on divergence)
 * Requires: docs/assets/hg-scanner.js + fixture/corpus files present.
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
require(path.join(ROOT, 'docs', 'assets', 'hg-scanner.js'));
const HG = globalThis.HG_SCANNER;

// ---- inputs: fixtures + a spread of real corpus bundles ----
const INPUTS = [
  ['tests/fixtures/GuardedHook.sol'],
  ['tests/fixtures/RiskyHook.sol'],
];
const corpusRoot = path.join(ROOT, 'corpus');
for (const chain of ['unichain', 'base', 'ethereum']) {
  const dir = path.join(corpusRoot, chain);
  if (!fs.existsSync(dir)) continue;
  for (const addr of fs.readdirSync(dir).slice(0, 12)) {
    const d = path.join(dir, addr);
    if (!fs.statSync(d).isDirectory()) continue;
    INPUTS.push(fs.readdirSync(d).filter(f => f.endsWith('.sol'))
      .map(f => path.join(d, f)));
  }
}

function pyScan(files) {
  const tmp = fs.mkdtempSync('/tmp/hg-parity-');
  files.forEach((f, i) => fs.copyFileSync(f, path.join(tmp, `f${i}__${path.basename(f)}`)));
  const scriptPath = path.join(tmp, 'run.py');
  fs.writeFileSync(scriptPath, [
    'import sys, json, os',
    'sys.path.insert(0,' + JSON.stringify(path.join(ROOT, 'src')) + ')',
    'import scan',
    'rows = []',
    'd = ' + JSON.stringify(tmp),
    'for f in sorted(os.listdir(d)):',
    '    rows.extend(scan.analyze_file(os.path.join(d, f)))',
    'norm = [{"contract": r["contract"], "declared": sorted(r["declared"]),',
    '         "findings": sorted([[x[0], x[1], x[3]] for x in r["findings"]])} for r in rows]',
    'print(json.dumps(norm))',
  ].join('\n'));
  const out = execSync('python3 "' + scriptPath + '"', { encoding: 'utf8' });
  return JSON.parse(out);
}

function jsScan(files) {
  const bundle = {};
  files.forEach((f, i) => { bundle[`f${i}__${path.basename(f)}`] = fs.readFileSync(f, 'utf8'); });
  const rows = HG.scanBundle(bundle);
  return rows.map(r => ({ contract: r.contract,
    declared: [...r.declared].sort(),
    findings: r.findings.map(x => [x.sev, x.rule, x.line]).sort() }))
    .sort((a, b) => a.contract.localeCompare(b.contract));
}

let failures = 0, checked = 0;
const norm = rows => JSON.stringify(rows.map(r => [r.contract,
  [...r.declared].sort(), [...r.findings].sort()].sort()));
for (const files of INPUTS) {
  const existing = files.filter(f => fs.existsSync(f));
  if (!existing.length) continue;
  checked++;
  let py, js;
  try { py = pyScan(existing); js = jsScan(existing); }
  catch (e) { console.log(`FAIL ${existing[0]} — ${String(e.message).slice(0,120)}`); failures++; continue; }
  if (norm(py) !== norm(js)) {
    console.log(`DIVERGENCE in bundle (${existing.length} files):`);
    const pm = Object.fromEntries(py.map(r => [r.contract, r]));
    const jm = Object.fromEntries(js.map(r => [r.contract, r]));
    for (const n of new Set([...Object.keys(pm), ...Object.keys(jm)])) {
      const p = pm[n], j = jm[n];
      if (!p || !j) console.log(`  presence differs: ${n} py=${!!p} js=${!!j}`);
      else {
        if (JSON.stringify([...p.declared].sort()) !== JSON.stringify([...j.declared].sort()))
          console.log(`  ${n} declared: py=${JSON.stringify(p.declared)} js=${JSON.stringify(j.declared)}`);
        const pf = p.findings.map(x => x.slice(0,3).join(':')).sort();
        const jf = j.findings.map(x => x.slice(0,3).join(':')).sort();
        if (JSON.stringify(pf) !== JSON.stringify(jf))
          console.log(`  ${n} findings:\n    py=${pf}\n    js=${jf}`);
      }
    }
    failures++;
  } else console.log(`OK  ${existing.length}-file bundle (${py.length} hooks)`);
}
console.log(`\nchecked ${checked} bundles, failures: ${failures}`);
process.exit(failures ? 1 : 0);
