/* HookGuard browser scanner — JS port of src/scan.py rules.
 * Global: HG_SCANNER.scanBundle(files) / .scoreResults(results)
 *   files = { "Name.sol": sourceText, ... }
 * Findings format mirrors python: {sev, rule, msg, line}
 * Parity with python is enforced by tests/parity.mjs on shared inputs.
 */
(function () {
  const CALLBACKS = ['beforeInitialize','afterInitialize','beforeAddLiquidity',
    'afterAddLiquidity','beforeRemoveLiquidity','afterRemoveLiquidity',
    'beforeSwap','afterSwap','beforeDonate','afterDonate'];
  const RETDELTA = ['beforeSwapReturnsDelta','afterSwapReturnsDelta',
    'afterAddLiquidityReturnsDelta','afterRemoveLiquidityReturnsDelta'];
  const VENDORED = ['test','mock','lib/','node_modules','script','out/','audit'];

  function stripComments(s) {
    s = s.replace(/\/\*[\s\S]*?\*\//g, m => '\n'.repeat((m.match(/\n/g) || []).length));
    return s.replace(/\/\/[^\n]*/g, '');
  }
  function lineOf(src, pos) { return src.slice(0, pos).split('\n').length; }

  function bodyOf(src, bracePos) {
    let depth = 0;
    for (let i = bracePos; i < src.length; i++) {
      if (src[i] === '{') depth++;
      else if (src[i] === '}') { if (--depth === 0) return src.slice(bracePos, i + 1); }
    }
    return src.slice(bracePos);
  }

  function validatesPool(view) {
    return new RegExp('key_?\\.(currency0|currency1|fee|tickSpacing|hooks)\\b[^;]{0,300}?(!=|==)[^;]{0,300}?(revert|require)', 'is').test(view)
        || new RegExp('(revert|require)[^;]{0,300}?key_?\\.(currency0|currency1|fee|tickSpacing)', 'is').test(view)
        || new RegExp('(revert|require)[^;]{0,160}?(NotInitialized|NotRegistered|NotSupported|NotAllowed|UnknownPool|InvalidPool|PoolNotFound)', 'is').test(view)
        || /!\s*\w+\.\s*(isInitialized|initialized|registered|enabled|active)\b[^;]{0,80}revert/is.test(view)
        || /sqrtPriceX96\s*==\s*0(?=[\s\S]{0,900}?revert\s+\w*Invalid)/is.test(view);
  }

  function isInert(sig, body) {
    const inner = body.slice(1, -1);
    if (/\brevert\b/.test(inner) && !(/\bif\b/.test(inner) || /\brequire\b/.test(inner))) return true;
    if (/\b(view|pure)\b/.test(sig)) return true;
    const safe = new Set();
    const rc = /returns\s*\(([^)]*)\)/s.exec(sig);
    if (rc) rc[1].split(',').forEach(p => { const w = p.trim().split(/\s+/); if (w.length >= 2) safe.add(w[w.length - 1]); });
    let m;
    const rd = /\b(?:uint\d*|int\d*|bool|address|bytes\d*|string|[A-Z]\w*)\s+(?:memory\s+|calldata\s+|storage\s+)?\s*(\w+)\s*=/g;
    while ((m = rd.exec(inner))) safe.add(m[1]);
    const ra = /(?:^|[;{}\n])\s*([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:\.\w+)?\s*=[^=]/g;
    while ((m = ra.exec(inner))) if (!safe.has(m[1])) return false;
    if (/\.call|\.transfer|safeTransfer|\bdelete\s|\+\+|--/.test(inner)) return false;
    return true;
  }

  /** Analyze one virtual bundle. Returns array of result rows:
   *  {file, contract, declared[], returnsDelta[], findings:[{sev,rule,msg,line}]} */
  function scanBundle(files) {
    const names = Object.keys(files).filter(n => /\.(sol)$/i.test(n));
    if (!names.length) return [];
    const stripped = {};                       // per-file stripped sources
    names.forEach(n => { stripped[n] = stripComments(files[n]); });

    // combined view for validation lookups (python: src + sibling files)
    const othersOf = (self) => names.filter(n => n !== self).map(n => stripped[n]).join('\n');

    const rows = [];
    const othersByName = {};
    names.forEach(n => { if (n !== '__self__') {} });
    for (const fname of names) {
      const src = stripped[fname];
      // narrow chased-sibling view (mirrors python): starts as own source;
      // delegation-target siblings get appended during guard/R2 setup below.
      let view = src;
      const addSiblingView = (tname) => {
        for (const n of names) {
          if (n === fname) continue;
          if (new RegExp('\\b(contract|library|abstract contract)\\s+' + tname + '\\b').test(stripped[n])) {
            view += '\n' + stripped[n];
            return true;
          }
        }
        return false;
      };

      // concrete declarations in this file
      const decls = [];
      const dr = /(abstract\s+)?contract\s+(\w+)/g;
      let dm;
      while ((dm = dr.exec(src))) if (!dm[1]) decls.push({ pos: dm.index, name: dm[2] });
      if (!decls.length) continue;

      for (let idx = 0; idx < decls.length; idx++) {
        const d = decls[idx];
        const name = d.name;

        // template filters
        if (/\/(mocks?|tests?)\//i.test('/' + fname) ||
            /(Mock|Test|Harness)$/.test(name) ||
            /^(Example|Test|Mock|Sample|Demo|Vulnerable)/.test(name) ||
            /vulnerable/i.test(name) ||
            (name === 'Counter' && /(^|\/)Counter\.sol$/i.test(fname))) continue;

        const icm = new RegExp('contract\\s+' + name + '\\s+is\\s+([^;{]+)\\{').exec(src);
        const inherits = icm ? icm[1] : '';
        const hasPermsStructural =
          /function\s+getHookPermissions\s*\([^)]*\)([^;{]*)\{/s.test(src);
        if (!(hasPermsStructural || /\b(BaseHook|IHooks)\b/.test(inherits))) continue;

        // structural permissions body — first match at or after this decl
        let pblock = '';
        const pr = /function\s+getHookPermissions\s*\([^)]*\)([^;{]*)\{(.*?)\n\s*\}/gs;
        let pm;
        while ((pm = pr.exec(src))) {
          if (pm.index >= d.pos - name.length - 20) { pblock = pm[2]; break; }
        }
        const declared = {};
        CALLBACKS.forEach(c => declared[c] = new RegExp('\\b' + c + '\\s*:\\s*true').test(pblock));
        const retDelta = {};
        RETDELTA.forEach(k => retDelta[k] = new RegExp('\\b' + k + '\\s*:\\s*true').test(pblock));

        const F = [];
        const declLine = lineOf(src, d.pos);

        // maps needed by guard rule AND by the sibling chase below
        const modBodies0 = {}, internalBodies0 = {};
        let mm0;
        const modRe0 = /modifier\s+(\w+)\s*(?:\([^)]*\))?\s*\{/g;
        while ((mm0 = modRe0.exec(src))) modBodies0[mm0[1]] = bodyOf(src, mm0.index + mm0[0].length - 1);
        const fnRe0 = /function\s+(_?\w+)\s*\([^)]*\)([^;{]*)\{/g;
        while ((mm0 = fnRe0.exec(src))) internalBodies0[mm0[1]] = bodyOf(src, mm0.index + mm0[0].length - 1);

        function chaseSiblings() {
          const targets = new Set();
          for (const c of CALLBACKS) {
            const m2 = new RegExp('function\\s+_?' + c + '\\s*\\([^)]*\\)([^;{]*)\\{').exec(src);
            if (!m2) continue;
            const cb = bodyOf(src, m2.index + m2[0].length - 1);
            const cRe = new RegExp('\\b([A-Z]\\w+)\\.\\s*_?' + c + '\\s*\\(', 'g');
            let tm;
            while ((tm = cRe.exec(cb))) targets.add(tm[1]);
            for (const fnm of (cb.match(/\b(_?\w+)\s*\(/g) || []).map(x => x.replace(/[\s(]/g, ''))) {
              const fb = internalBodies0[fnm];
              if (!fb || fnm === c) continue;
              for (const t of (fb.match(/\b[A-Z]\w+\.\s*\w+\s*\(/g) || []))
                targets.add(t.split('.')[0]);
            }
          }
          targets.delete(name); targets.delete('BaseHook'); targets.delete('IHooks'); targets.delete('Hooks');
          for (const t of targets) addSiblingView(t);
        }
        chaseSiblings();

        // ---- R1 ----
        const allowlisted = /(allowlist|allowList|whitelist|authorizedPool|validPool|onlyValidPool|poolId\s*==|PoolIdLibrary\.toId)/i.test(view);
        if (!declared['beforeInitialize'] && !allowlisted && !validatesPool(view)) {
          const holdsFunds = /(safeTransfer|transferFrom|\.transfer\(|take\(|settle\(|mint\(|burn\()/.test(src);
          const poolState = /mapping\s*\(\s*PoolId/.test(src);
          if (holdsFunds || poolState)
            F.push({ sev: 'MEDIUM', rule: 'PERMISSIONLESS_ATTACHMENT', line: declLine,
              msg: 'No beforeInitialize gate and no pool validation found, and the hook holds funds or keeps per-PoolId state.' });
          else
            F.push({ sev: 'INFO', rule: 'PERMISSIONLESS_BY_DESIGN', line: declLine,
              msg: 'Any pool may attach this hook (no beforeInitialize gate). No funds or per-pool state detected.' });
        }

        // ---- R2 guard detection ----
        const usesBasehook = /\bis\b[^{]*BaseHook/.test(view);
        const modBodies = {}, authHelpers = new Set(), internalBodies = {};
        let mm;
        const modRe = /modifier\s+(\w+)\s*(?:\([^)]*\))?\s*\{/g;
        while ((mm = modRe.exec(src))) modBodies[mm[1]] = bodyOf(src, mm.index + mm[0].length - 1);
        const fnRe = /function\s+(_?\w+)\s*\([^)]*\)([^;{]*)\{/g;
        while ((mm = fnRe.exec(src))) {
          const nm = mm[1];
          const fb = bodyOf(src, mm.index + mm[0].length - 1);
          internalBodies[nm] = fb;
          if (!(nm in modBodies) && !CALLBACKS.includes(nm) && nm !== 'constructor') {
            if (fb.length <= 600 && /msg\.sender\s*(==|!=)/.test(fb)) authHelpers.add(nm);
          }
        }
        const KEYWORDS = new Set(['external','public','internal','private','pure','view',
          'payable','virtual','override','returns']);

        function guarded(sigtail, body) {
          const applied = new Set((sigtail.match(/[A-Za-z_]\w*/g) || []).filter(x => !KEYWORDS.has(x)));
          for (const t of applied) {
            if (t in modBodies && /msg\.sender\s*(==|!=)/.test(modBodies[t])) return true;
            if (t.toLowerCase().replace(/_/g, '').includes('poolmanager')) return true;
          }
          if (/msg\.sender\s*(==|!=)\s*[^\s;]/.test(body)) return true;
          for (const h of authHelpers)
            if (new RegExp('\\b' + h + '\\s*\\(').test(body)) return true;
          return false;
        }

        if (!usesBasehook) {
          for (const c of CALLBACKS) {
            const m2 = new RegExp('function\\s+' + c + '\\s*\\([^)]*\\)([^;{]*)\\{').exec(src);
            if (!m2) continue;
            const body = bodyOf(src, m2.index + m2[0].length - 1);
            if (guarded(m2[1], body)) continue;
            if (isInert(m2[0], body)) continue;
            F.push({ sev: 'HIGH', rule: 'MISSING_POOLMANAGER_GUARD', line: lineOf(src, m2.index),
              msg: c + '() has no onlyPoolManager-style guard and the contract does not inherit BaseHook.' });
          }
        }

        // ---- R3 ----
        if (retDelta['beforeSwapReturnsDelta']) {
          const b = /function\s+_?beforeSwap\s*\(.*?\n\s*\}/s.exec(src);
          if (b && !/toBeforeSwapDelta|BeforeSwapDelta\s*\(/.test(b[0]))
            F.push({ sev: 'MEDIUM', rule: 'DELTA_FLAG_MISMATCH', line: lineOf(src, b.index),
              msg: 'beforeSwapReturnsDelta declared but beforeSwap does not construct a BeforeSwapDelta.' });
        }
        if (retDelta['afterSwapReturnsDelta']) {
          const b = /function\s+_?afterSwap\s*\(.*?\n\s*\}/s.exec(src);
          if (b && !/return\s*\([^)]*,\s*(?!0\b)/.test(b[0]))
            F.push({ sev: 'LOW', rule: 'DELTA_FLAG_UNUSED', line: lineOf(src, b.index),
              msg: 'afterSwapReturnsDelta declared but afterSwap appears to always return zero delta.' });
        }

        // ---- R4 ----
        for (const c of ['beforeSwap', 'afterSwap']) {
          if (!declared[c]) continue;
          const b = new RegExp('function\\s+_?' + c + '\\s*\\(.*?\\n\\s*\\}', 's').exec(src);
          if (!b) continue;
          const ext = /\b(latestRoundData|getPrice|oracle\.|\.call\(|staticcall|IERC20\([^)]*\)\.(transfer|transferFrom))/.exec(b[0]);
          if (ext && !/try /.test(b[0]))
            F.push({ sev: 'MEDIUM', rule: 'REVERT_DOS_RISK', line: lineOf(src, b.index + ext.index),
              msg: c + ' makes an external call with no try/catch — failing dependency bricks every swap.' });
        }

        // ---- R5 ----
        if (/DYNAMIC_FEE_FLAG|updateDynamicLPFee/.test(src) &&
            !/(MAX_FEE|maxFee|require\s*\([^)]*fee\s*<|fee\s*=\s*fee\s*>\s*\w+\s*\?)/.test(src))
          F.push({ sev: 'MEDIUM', rule: 'UNBOUNDED_DYNAMIC_FEE', line: declLine,
            msg: 'Dynamic fee is set with no visible upper bound.' });

        // ---- R6 ----
        if (/\b(UUPSUpgradeable|Initializable|TransparentUpgradeableProxy|_authorizeUpgrade|delegatecall)\b/.test(src))
          F.push({ sev: 'HIGH', rule: 'UPGRADEABLE_HOOK', line: declLine,
            msg: 'Upgradeable/delegatecall pattern — implementation can be swapped.' });

        // ---- R7 ----
        if (!/ReentrancyGuard|nonReentrant|_locked|transient/.test(src)) {
          for (const c of CALLBACKS) {
            if (!declared[c]) continue;
            const b = new RegExp('function\\s+_?' + c + '\\s*\\(.*?\\n\\s*\\}', 's').exec(src);
            if (b && /\.call\{|\.call\(|safeTransfer|transferFrom|\.send\(/.test(b[0])) {
              F.push({ sev: 'MEDIUM', rule: 'REENTRANCY_SURFACE', line: lineOf(src, b.index),
                msg: c + ' performs a token/native transfer with no reentrancy guard.' });
              break;
            }
          }
        }

        rows.push({ file: fname, contract: name,
          declared: Object.keys(declared).filter(k => declared[k]),
          returnsDelta: Object.keys(retDelta).filter(k => retDelta[k]),
          findings: F.sort((a, b) => a.line - b.line) });
      }
    }
    return rows;
  }

  /* ---- scoring: same weights as src/score.py (source layer only) ---- */
  const W = { high: 15, medium: 7, low: 3, info: 1 };
  function scoreResults(rows) {
    let score = 0; const factors = [];
    const count = { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
    rows.forEach(r => r.findings.forEach(f => count[f.sev]++));
    const add = (label, delta) => { score += delta; factors.push({ label, delta }); };
    if (count.HIGH) add(count.HIGH + '× HIGH finding(s)', W.high * count.HIGH);
    if (count.MEDIUM) add(count.MEDIUM + '× MEDIUM finding(s)', W.medium * count.MEDIUM);
    if (count.LOW) add(count.LOW + '× LOW finding(s)', W.low * count.LOW);
    if (count.INFO) add(count.INFO + '× informational', W.info * count.INFO);
    score = Math.max(0, Math.min(100, score));
    const band = score <= 24 ? 'LOW' : score <= 49 ? 'MODERATE' : score <= 74 ? 'ELEVATED' : 'HIGH';
    return { value: score, band, confidence: 'medium', factors };
  }

  globalThis.HG_SCANNER = { scanBundle, scoreResults, CALLBACKS };
})();
