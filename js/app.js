/**
 * app.js — Grader page logic
 * Talks to the local companion server at http://localhost:5001
 */

const SERVER = 'http://localhost:5001';

/* ── State ───────────────────────────────────────────────── */
let connected = false;
let running   = false;
let csvData   = { headers: [], rows: [] };

/* ── DOM refs ────────────────────────────────────────────── */
const banner      = document.getElementById('server-banner');
const dot         = document.getElementById('server-dot');
const statusText  = document.getElementById('server-status-text');
const btnRun      = document.getElementById('btn-run');
const runMeta     = document.getElementById('run-meta');
const logBox      = document.getElementById('log-box');
const progressWrap= document.getElementById('progress-wrap');
const progressFill= document.getElementById('progress-fill');
const progressLbl = document.getElementById('progress-label-text');
const progressPct = document.getElementById('progress-pct');
const resultsSection = document.getElementById('results-section');
const emptyResults   = document.getElementById('empty-results');

/* ── Server connection check ─────────────────────────────── */

async function checkServer() {
  try {
    const res = await fetch(`${SERVER}/api/ping`, { signal: AbortSignal.timeout(2500) });
    if (res.ok) {
      setConnected(true);
      loadConfig();
      tryLoadResults();
      return;
    }
  } catch (_) {}
  setConnected(false);
}

function setConnected(ok) {
  connected = ok;
  banner.className = 'server-banner ' + (ok ? 'connected' : 'error');
  statusText.textContent = ok
    ? 'Local grader server is running — ready to grade.'
    : 'Local grader server not found. Run: python3 server.py';
  btnRun.disabled = !ok || running;
  runMeta.textContent = ok
    ? 'Submissions folder and rubric are loaded from config.json.'
    : 'Connect the local server to enable grading.';
}

document.getElementById('btn-retry-connect').addEventListener('click', checkServer);

/* ── Config ──────────────────────────────────────────────── */

async function loadConfig() {
  try {
    const res = await fetch(`${SERVER}/api/config`);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.submissions_dir) document.getElementById('cfg-submissions').value = cfg.submissions_dir;
    if (cfg.rubric_file)     document.getElementById('cfg-rubric').value      = cfg.rubric_file;
    if (cfg.output_csv)      document.getElementById('cfg-output').value      = cfg.output_csv;
    const strat = cfg.id_extraction?.strategy || 'before_first_underscore';
    document.getElementById('cfg-id-strategy').value = strat;
    if (cfg.id_extraction?.regex) document.getElementById('cfg-regex').value = cfg.id_extraction.regex;
    toggleRegexField(strat);
    // LLM settings
    if (cfg.llm_provider) document.getElementById('cfg-llm-provider').value = cfg.llm_provider;
    if (cfg.llm_model)    document.getElementById('cfg-llm-model').value    = cfg.llm_model;
    if (cfg.llm_api_key)  document.getElementById('cfg-llm-key').value      = cfg.llm_api_key;
  } catch (_) {}
}

async function saveConfig() {
  const strategy = document.getElementById('cfg-id-strategy').value;
  const cfg = {
    submissions_dir: document.getElementById('cfg-submissions').value || './submissions',
    rubric_file:     document.getElementById('cfg-rubric').value      || './rubric.json',
    output_csv:      document.getElementById('cfg-output').value      || './results.csv',
    id_extraction: {
      strategy,
      regex: document.getElementById('cfg-regex').value || '^([^_]+)',
    },
    compile_timeout_seconds: 10,
    run_timeout_seconds: 2,
    llm_provider: document.getElementById('cfg-llm-provider').value || 'anthropic',
    llm_model:    document.getElementById('cfg-llm-model').value    || 'claude-3-haiku-20240307',
    llm_api_key:  document.getElementById('cfg-llm-key').value      || '',
  };
  try {
    await fetch(`${SERVER}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg),
    });
  } catch (_) {}
}

document.getElementById('cfg-id-strategy').addEventListener('change', e => {
  toggleRegexField(e.target.value);
});

function toggleRegexField(strategy) {
  document.getElementById('regex-group').style.display =
    strategy === 'regex' ? 'flex' : 'none';
}

/* ── Run grader ──────────────────────────────────────────── */

btnRun.addEventListener('click', async () => {
  if (!connected || running) return;
  await saveConfig();
  startGrader();
});

async function startGrader() {
  running = true;
  btnRun.disabled = true;
  btnRun.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="margin-right:4px;animation:spin 1s linear infinite">
      <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2" stroke-dasharray="28" stroke-dashoffset="10"/>
    </svg>Running…`;

  clearLog();
  showProgress(true);
  setProgress(0, 'Starting grader…');

  // POST to start the run
  try {
    const res = await fetch(`${SERVER}/api/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json();
      appendLog(err.error || 'Failed to start grader.', 'err');
      finishRun(false);
      return;
    }
  } catch (e) {
    appendLog('Could not reach server: ' + e.message, 'err');
    finishRun(false);
    return;
  }

  // Open SSE stream to receive live log
  const es = new EventSource(`${SERVER}/api/stream`);

  let total = 0;
  let done  = 0;

  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.done) {
      es.close();
      if (msg.error) {
        appendLog('ERROR: ' + msg.error, 'err');
      }
      if (msg.summary?.text) {
        appendLog(msg.summary.text, 'bold');
      }
      setProgress(100, 'Done.');
      finishRun(true);
      setTimeout(() => tryLoadResults(), 600);
      return;
    }

    const line = msg.line || '';

    // Detect total from "Found N submission(s)"
    const foundMatch = line.match(/Found\s+(\d+)\s+submission/);
    if (foundMatch) total = parseInt(foundMatch[1], 10);

    // Detect per-file graded lines
    if (line.match(/✓ Compiles|✗ Compile/)) {
      done++;
      if (total > 0) setProgress(Math.round((done / total) * 95), `Grading ${done} / ${total}…`);
    }

    // Style lines
    let cls = 'info';
    if (line.includes('✓')) cls = 'ok';
    else if (line.includes('✗') || line.toLowerCase().includes('error')) cls = 'err';
    else if (line.startsWith('Found') || line.startsWith('Rubric') || line.startsWith('ID') || line.startsWith('Summary')) cls = 'bold';

    appendLog(line, cls);
  };

  es.onerror = () => {
    es.close();
    finishRun(false);
  };
}

function finishRun(success) {
  running = false;
  btnRun.disabled = !connected;
  btnRun.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="margin-right:4px">
      <path d="M4 3l10 5-10 5V3z" fill="currentColor"/>
    </svg>Run Grader`;
  runMeta.textContent = success
    ? 'Grading complete — results loaded below.'
    : 'Grading stopped. Check the log for details.';
}

/* ── Log helpers ─────────────────────────────────────────── */

function clearLog() {
  logBox.innerHTML = '';
  logBox.classList.add('visible');
}

function appendLog(text, cls = '') {
  const line = document.createElement('div');
  line.className = 'log-line ' + cls;
  line.textContent = text;
  logBox.appendChild(line);
  logBox.scrollTop = logBox.scrollHeight;
}

/* ── Progress bar ────────────────────────────────────────── */

function showProgress(visible) {
  progressWrap.classList.toggle('visible', visible);
}

function setProgress(pct, label) {
  progressFill.style.width = pct + '%';
  progressLbl.textContent  = label;
  progressPct.textContent  = pct + '%';
}

/* ── Results table ───────────────────────────────────────── */

async function tryLoadResults() {
  try {
    const res = await fetch(`${SERVER}/api/results`);
    if (!res.ok) {
      showEmptyResults();
      return;
    }
    const data = await res.json();
    if (data.rows && data.rows.length > 0) {
      csvData = data;
      renderTable(data.headers, data.rows);
    } else {
      showEmptyResults();
    }
  } catch (_) {
    showEmptyResults();
  }
}

function renderTable(headers, rows) {
  const thead = document.getElementById('results-thead');
  const tbody = document.getElementById('results-tbody');
  const title = document.getElementById('results-title');

  title.textContent = `Results — ${rows.length} student${rows.length !== 1 ? 's' : ''}`;

  // Fixed columns that are never rubric-score columns
  const fixedCols    = new Set(['Student_ID','File','Compiles','Compile_Error','Total_Score','Max_Score','Feedback']);
  const compilesIdx  = headers.indexOf('Compiles');
  const totalIdx     = headers.indexOf('Total_Score');
  const maxIdx       = headers.indexOf('Max_Score');

  // Determine per-rubric-item max marks from the first row (stored in Max_Score split isn't available,
  // so we colour by ratio: 0=red, full=green, partial=orange)
  const rubricCols = headers.filter(h => !fixedCols.has(h));

  // Per-column max (from all rows)
  const colMax = {};
  rubricCols.forEach(h => {
    colMax[h] = Math.max(...rows.map(r => Number(r[h]) || 0));
  });

  // Header
  thead.innerHTML = '<tr>' + headers.map(h => `<th>${esc(h.replace(/_/g,' '))}</th>`).join('') + '</tr>';

  // Body
  tbody.innerHTML = rows.map(row => {
    const cells = headers.map((h, i) => {
      let val = row[h] ?? '';
      let cls = '';
      let display = esc(val);

      if (i === compilesIdx) {
        cls = val === 'Y' ? 'compile-y' : val === 'N' ? 'compile-n' : '';
      } else if (rubricCols.includes(h) && val !== '') {
        const n = Number(val);
        const max = colMax[h] || 1;
        const ratio = n / max;
        cls = ratio >= 1 ? 'score-full' : ratio > 0 ? 'score-partial' : 'score-zero';
        display = `${n}<span class="score-max">/${max}</span>`;
      } else if (i === totalIdx && maxIdx !== -1) {
        const total = Number(val) || 0;
        const max   = Number(row['Max_Score']) || 1;
        const pct   = Math.round(total / max * 100);
        display = `${total} <span class="score-max">(${pct}%)</span>`;
      } else if (h === 'Compile_Error' || h === 'Feedback') {
        display = val ? `<span title="${esc(val)}" style="cursor:help">⚠ hover</span>` : '';
      }

      return `<td class="${cls}" title="${esc(String(val))}">${display}</td>`;
    });
    return '<tr>' + cells.join('') + '</tr>';
  }).join('');

  resultsSection.style.display = 'block';
  emptyResults.style.display   = 'none';
}

function showEmptyResults() {
  resultsSection.style.display = 'none';
  emptyResults.style.display   = 'block';
}

/* ── Refresh results ─────────────────────────────────────── */
document.getElementById('btn-refresh-results').addEventListener('click', tryLoadResults);

/* ── Download CSV ────────────────────────────────────────── */
document.getElementById('btn-download-csv').addEventListener('click', () => {
  if (!csvData.headers.length) return;

  const lines = [
    csvData.headers.map(csvCell).join(','),
    ...csvData.rows.map(row => csvData.headers.map(h => csvCell(row[h] ?? '')).join(','))
  ];
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = 'results.csv';
  a.click();
  URL.revokeObjectURL(url);
});

function csvCell(val) {
  const s = String(val);
  return (s.includes(',') || s.includes('"') || s.includes('\n'))
    ? '"' + s.replace(/"/g, '""') + '"'
    : s;
}

/* ── Toast ───────────────────────────────────────────────── */
let toastTimer;
function toast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show ' + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 2400);
}

/* ── Spin keyframe ───────────────────────────────────────── */
const style = document.createElement('style');
style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(style);

/* ── Utility ─────────────────────────────────────────────── */
function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Boot ────────────────────────────────────────────────── */
checkServer();
// Re-check every 5 seconds in case server starts up later
setInterval(() => { if (!connected) checkServer(); }, 5000);
