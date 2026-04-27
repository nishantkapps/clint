/**
 * app.js — Grader page (compile, execution, rubric as separate phases)
 */

const SERVER_KEY = 'clint_server_url';
let SERVER = localStorage.getItem(SERVER_KEY) || 'http://localhost:5001';

let connected = false;
let running = false;
let runningMode = null; // 'compile' | 'execution' | 'rubric'

let csvCompile = { headers: [], rows: [] };
let csvExecution = { headers: [], rows: [] };
let csvRubric = { headers: [], rows: [] };
let rubricItems = [];

const banner = document.getElementById('server-banner');
const btnCompile = document.getElementById('btn-run-compile');
const btnExecution = document.getElementById('btn-run-execution');
const btnRubric = document.getElementById('btn-run-rubric');
const runMeta = document.getElementById('run-meta');
const logBox = document.getElementById('log-box');
const progressWrap = document.getElementById('progress-wrap');
const progressFill = document.getElementById('progress-fill');
const progressLbl = document.getElementById('progress-label-text');
const progressPct = document.getElementById('progress-pct');

/* ── Server ──────────────────────────────────────────────── */

async function checkServer() {
  try {
    const res = await fetch(`${SERVER}/api/ping`, { signal: AbortSignal.timeout(2500) });
    if (res.ok) {
      setConnected(true);
      loadConfig();
      loadRubric();
      tryLoadCompileResults();
      tryLoadExecutionResults();
      tryLoadRubricResults();
      return;
    }
  } catch (_) {}
  setConnected(false);
}

function setConnected(ok) {
  connected = ok;
  banner.className = 'server-banner ' + (ok ? 'connected' : 'error');
  document.getElementById('server-status-text').textContent = ok
    ? 'Grader server is running — ready to grade.'
    : 'Grader server not found. Check the URL or run: python3 server.py';
  document.getElementById('server-url-display').textContent = SERVER;
  btnCompile.disabled = !ok || running;
  btnExecution.disabled = !ok || running;
  btnRubric.disabled = !ok || running;
  runMeta.textContent = ok
    ? 'Compile first, then run execution (test cases), then rubric — or any step alone.'
    : 'Connect to the grader server.';
}

document.getElementById('btn-retry-connect').addEventListener('click', checkServer);

/* Server URL editor */
const urlEditor = document.getElementById('server-url-editor');
const urlInput = document.getElementById('server-url-input');

document.getElementById('btn-change-url').addEventListener('click', () => {
  urlInput.value = SERVER;
  urlEditor.style.display = urlEditor.style.display === 'none' ? 'block' : 'none';
  if (urlEditor.style.display !== 'none') urlInput.focus();
});
document.getElementById('btn-cancel-url').addEventListener('click', () => { urlEditor.style.display = 'none'; });
document.getElementById('btn-save-url').addEventListener('click', () => {
  const val = urlInput.value.trim().replace(/\/$/, '');
  if (!val) return;
  SERVER = val;
  localStorage.setItem(SERVER_KEY, SERVER);
  urlEditor.style.display = 'none';
  setConnected(false);
  checkServer();
});
urlInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('btn-save-url').click();
  if (e.key === 'Escape') document.getElementById('btn-cancel-url').click();
});

/* ── Config ──────────────────────────────────────────────── */

async function loadConfig() {
  try {
    const res = await fetch(`${SERVER}/api/config`);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.submissions_dir) document.getElementById('cfg-submissions').value = cfg.submissions_dir;
    if (cfg.build_output_dir != null) document.getElementById('cfg-build-output').value = cfg.build_output_dir;
    if (cfg.rubric_file) document.getElementById('cfg-rubric').value = cfg.rubric_file;
    if (cfg.output_compile_csv) document.getElementById('cfg-output-compile').value = cfg.output_compile_csv;
    if (cfg.output_execution_csv) document.getElementById('cfg-output-execution').value = cfg.output_execution_csv;
    if (cfg.output_rubric_csv) document.getElementById('cfg-output-rubric').value = cfg.output_rubric_csv;
    const strat = cfg.id_extraction?.strategy || 'before_first_underscore';
    document.getElementById('cfg-id-strategy').value = strat;
    if (cfg.id_extraction?.regex) document.getElementById('cfg-regex').value = cfg.id_extraction.regex;
    toggleRegexField(strat);
    if (cfg.llm_provider) document.getElementById('cfg-llm-provider').value = cfg.llm_provider;
    if (cfg.llm_model) document.getElementById('cfg-llm-model').value = cfg.llm_model;
    if (cfg.llm_api_key) document.getElementById('cfg-llm-key').value = cfg.llm_api_key;
    if (cfg.stdin_for_run != null) document.getElementById('cfg-stdin').value = cfg.stdin_for_run;
    if (cfg.expected_output != null) document.getElementById('cfg-expected').value = cfg.expected_output;
    if (cfg.compilation_max_marks != null) {
      document.getElementById('cfg-compile-max').value = String(cfg.compilation_max_marks);
    }
    if (cfg.execution_max_marks != null) document.getElementById('cfg-exec-max').value = String(cfg.execution_max_marks);
    const useSuites = Boolean(cfg.use_test_suites);
    document.getElementById('cfg-use-test-suites').checked = useSuites;
    document.getElementById('cfg-test-suite-strategy').value =
      cfg.test_suite_strategy === 'mod3_id_numeric' ? 'mod3_id_numeric' : 'mod3_id_charsum';
    toggleSuiteStrategyVisibility(useSuites);
  } catch (_) {}
}

async function saveConfig() {
  const strategy = document.getElementById('cfg-id-strategy').value;
  const cfg = {
    submissions_dir: document.getElementById('cfg-submissions').value || './submissions',
    build_output_dir: document.getElementById('cfg-build-output').value || './output',
    rubric_file: document.getElementById('cfg-rubric').value || './rubric.json',
    output_compile_csv: document.getElementById('cfg-output-compile').value || './results_compile.csv',
    output_execution_csv: document.getElementById('cfg-output-execution').value || './results_execution.csv',
    output_rubric_csv: document.getElementById('cfg-output-rubric').value || './results_rubric.csv',
    id_extraction: {
      strategy,
      regex: document.getElementById('cfg-regex').value || '^([^_]+)',
    },
    compile_timeout_seconds: 10,
    run_timeout_seconds: 2,
    llm_provider: document.getElementById('cfg-llm-provider').value || 'anthropic',
    llm_model: document.getElementById('cfg-llm-model').value || 'claude-3-haiku-20240307',
    llm_api_key: document.getElementById('cfg-llm-key').value || '',
    stdin_for_run: document.getElementById('cfg-stdin').value,
    expected_output: document.getElementById('cfg-expected').value,
    compilation_max_marks: Number(document.getElementById('cfg-compile-max').value) || 5,
    execution_max_marks: Number(document.getElementById('cfg-exec-max').value) || 10,
    use_test_suites: document.getElementById('cfg-use-test-suites').checked,
    test_suite_strategy: document.getElementById('cfg-test-suite-strategy').value,
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
document.getElementById('cfg-use-test-suites').addEventListener('change', e => {
  toggleSuiteStrategyVisibility(e.target.checked);
});
function toggleSuiteStrategyVisibility(on) {
  document.getElementById('cfg-suite-strategy-wrap').style.display = on ? 'flex' : 'none';
}
function toggleRegexField(strategy) {
  document.getElementById('regex-group').style.display =
    strategy === 'regex' ? 'flex' : 'none';
}

/* ── Rubric legend ───────────────────────────────────────── */

async function loadRubric() {
  try {
    const res = await fetch(`${SERVER}/api/rubric`);
    if (!res.ok) return;
    const data = await res.json();
    rubricItems = data.items || [];
    renderRubricLegend(rubricItems);
  } catch (_) {}
}

function renderRubricLegend(items) {
  const legend = document.getElementById('rubric-legend');
  const container = document.getElementById('rubric-legend-items');
  if (!items.length) { legend.style.display = 'none'; return; }
  container.innerHTML = items.map((item, i) => {
    const typeClass = `badge-type-${item.type || 'static'}`;
    return `
      <div class="rubric-chip">
        <span class="chip-label">Rubric ${i + 1}</span>
        <span class="chip-name">${esc(item.name)}</span>
        <span class="chip-cond">${esc(item.condition)}</span>
        <span class="chip-meta">
          <span class="${typeClass}">${item.type}</span>
          &nbsp;·&nbsp; max ${item.max_marks} pts
        </span>
      </div>`;
  }).join('');
  legend.style.display = 'block';
}

/* ── Run phases ───────────────────────────────────────────── */

const PHASE_ENDPOINT = {
  compile: '/api/run-compile',
  execution: '/api/run-execution',
  rubric: '/api/run-rubric',
};

function phaseButton(mode) {
  if (mode === 'compile') return btnCompile;
  if (mode === 'execution') return btnExecution;
  return btnRubric;
}

const PHASE_PROGRESS = {
  compile: 'Compiling…',
  execution: 'Running tests…',
  rubric: 'Scoring rubric…',
};

btnCompile.addEventListener('click', () => startPhase('compile'));
btnExecution.addEventListener('click', () => startPhase('execution'));
btnRubric.addEventListener('click', () => startPhase('rubric'));

async function startPhase(mode) {
  if (!connected || running) return;
  await saveConfig();
  running = true;
  runningMode = mode;
  btnCompile.disabled = true;
  btnExecution.disabled = true;
  btnRubric.disabled = true;

  const endpoint = PHASE_ENDPOINT[mode];
  const btn = phaseButton(mode);
  const orig = btn.innerHTML;
  btn.innerHTML = `<span style="animation:spin 1s linear infinite;display:inline-block">⟳</span> Running…`;

  clearLog();
  showProgress(true);
  setProgress(0, PHASE_PROGRESS[mode] || 'Running…');

  try {
    const res = await fetch(`${SERVER}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      appendLog(err.error || 'Failed to start.', 'err');
      finishRun(false, btn, orig);
      return;
    }
  } catch (e) {
    appendLog('Could not reach server: ' + e.message, 'err');
    finishRun(false, btn, orig);
    return;
  }

  const es = new EventSource(`${SERVER}/api/stream`);
  let total = 0;
  let done = 0;

  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.done) {
      es.close();
      if (msg.error) appendLog('ERROR: ' + msg.error, 'err');
      if (msg.summary?.text) appendLog(msg.summary.text, 'bold');
      setProgress(100, 'Done.');
      finishRun(true, btn, orig);
      setTimeout(() => {
        loadRubric();
        if (mode === 'compile') tryLoadCompileResults();
        else if (mode === 'execution') tryLoadExecutionResults();
        else tryLoadRubricResults();
      }, 500);
      return;
    }

    const line = msg.line || '';
    const foundMatch = line.match(/Found\s+(\d+)\s+submission/);
    if (foundMatch) total = parseInt(foundMatch[1], 10);

    const prog = line.match(/^\[\s*(\d+)\s*\/\s*(\d+)\s*\]/);
    if (prog) {
      done = parseInt(prog[1], 10);
      total = parseInt(prog[2], 10);
      setProgress(Math.min(95, Math.round((done / total) * 95)), `${done} / ${total}…`);
    }

    let cls = 'info';
    if (line.includes('✓')) cls = 'ok';
    else if (line.includes('✗') || line.toLowerCase().includes('error')) cls = 'err';
    else if (line.startsWith('Found') || line.startsWith('Rubric') || line.startsWith('Compile')
        || line.startsWith('Execution') || line.startsWith('Summary') || line.startsWith('Average')) cls = 'bold';
    appendLog(line, cls);
  };

  es.onerror = () => {
    es.close();
    finishRun(false, btn, orig); // btn/orig from closure
  };
}

function finishRun(success, btn, origHtml) {
  running = false;
  runningMode = null;
  btnCompile.disabled = !connected;
  btnExecution.disabled = !connected;
  btnRubric.disabled = !connected;
  if (btn && origHtml) btn.innerHTML = origHtml;
  runMeta.textContent = success
    ? 'Finished — tables updated below.'
    : 'Stopped — see log.';
}

/* ── Log / progress ──────────────────────────────────────── */

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
function showProgress(v) { progressWrap.classList.toggle('visible', v); }
function setProgress(pct, label) {
  progressFill.style.width = pct + '%';
  progressLbl.textContent = label;
  progressPct.textContent = pct + '%';
}

/* ── Fetch results ───────────────────────────────────────── */

async function tryLoadCompileResults() {
  const sec = document.getElementById('compile-results-section');
  const empty = document.getElementById('empty-compile');
  try {
    const res = await fetch(`${SERVER}/api/results-compile`);
    if (!res.ok) {
      sec.style.display = 'none';
      empty.style.display = 'block';
      return;
    }
    const data = await res.json();
    csvCompile = data;
    if (data.rows?.length) {
      renderCompileTable(data.headers, data.rows);
      sec.style.display = 'block';
      empty.style.display = 'none';
    } else {
      sec.style.display = 'none';
      empty.style.display = 'block';
    }
  } catch (_) {
    sec.style.display = 'none';
    empty.style.display = 'block';
  }
}

async function tryLoadExecutionResults() {
  const sec = document.getElementById('execution-results-section');
  const empty = document.getElementById('empty-execution');
  try {
    const res = await fetch(`${SERVER}/api/results-execution`);
    if (!res.ok) {
      sec.style.display = 'none';
      empty.style.display = 'block';
      return;
    }
    const data = await res.json();
    csvExecution = data;
    if (data.rows?.length) {
      renderExecutionTable(data.headers, data.rows);
      sec.style.display = 'block';
      empty.style.display = 'none';
    } else {
      sec.style.display = 'none';
      empty.style.display = 'block';
    }
  } catch (_) {
    sec.style.display = 'none';
    empty.style.display = 'block';
  }
}

async function tryLoadRubricResults() {
  const sec = document.getElementById('rubric-results-section');
  const empty = document.getElementById('empty-rubric');
  try {
    const res = await fetch(`${SERVER}/api/results-rubric`);
    if (!res.ok) {
      sec.style.display = 'none';
      empty.style.display = 'block';
      if (rubricItems.length) renderRubricLegend(rubricItems);
      return;
    }
    const data = await res.json();
    csvRubric = data;
    if (data.rows?.length) {
      renderRubricTable(data.headers, data.rows);
      sec.style.display = 'block';
      empty.style.display = 'none';
      if (rubricItems.length) renderRubricLegend(rubricItems);
    } else {
      sec.style.display = 'none';
      empty.style.display = 'block';
    }
  } catch (_) {
    sec.style.display = 'none';
    empty.style.display = 'block';
  }
}

function renderCompileTable(headers, rows) {
  document.getElementById('compile-results-title').textContent =
    `Compile report — ${rows.length} student${rows.length !== 1 ? 's' : ''}`;

  const preferred = ['Student_ID', 'Filename', 'Compiles', 'Compile_Error'];
  const legacyFile = headers.includes('File') && !headers.includes('Filename');
  const displayHeaders = preferred.filter(h => {
    if (h === 'Filename') return headers.includes('Filename') || legacyFile;
    return headers.includes(h);
  });
  const cellKey = h => (h === 'Filename' && legacyFile && !headers.includes('Filename') ? 'File' : h);

  const thead = document.getElementById('compile-thead');
  const tbody = document.getElementById('compile-tbody');
  thead.innerHTML = '<tr>' + displayHeaders.map(h => `<th>${esc(h.replace(/_/g, ' '))}</th>`).join('') + '</tr>';

  const longCols = new Set(['Compile_Error']);
  const compIdx = displayHeaders.indexOf('Compiles');

  tbody.innerHTML = rows.map(row => {
    return '<tr>' + displayHeaders.map((h, i) => {
      const key = cellKey(h);
      let val = row[key] ?? '';
      let cls = '';
      let display = esc(String(val));

      if (i === compIdx) cls = val === 'Y' ? 'compile-y' : val === 'N' ? 'compile-n' : '';

      if (longCols.has(h) && String(val).length > 100) {
        display = esc(String(val).slice(0, 100)) + '…';
      }

      return `<td class="${cls}" title="${esc(String(val))}">${display}</td>`;
    }).join('') + '</tr>';
  }).join('');
}

function renderExecutionTable(headers, rows) {
  document.getElementById('execution-results-title').textContent =
    `Execution report — ${rows.length} student${rows.length !== 1 ? 's' : ''}`;

  const thead = document.getElementById('execution-thead');
  const tbody = document.getElementById('execution-tbody');
  thead.innerHTML = '<tr>' + headers.map(h => `<th>${esc(h.replace(/_/g, ' '))}</th>`).join('') + '</tr>';

  const longCols = new Set(['Stdout', 'Stderr', 'Execution_Note', 'Binary_Path', 'Run_Error']);
  const execM = headers.indexOf('Execution_Marks');
  const execMax = headers.indexOf('Execution_Max');

  tbody.innerHTML = rows.map(row => {
    return '<tr>' + headers.map((h, i) => {
      let val = row[h] ?? '';
      let cls = '';
      let display = esc(String(val));

      if (longCols.has(h) && String(val).length > 100) {
        display = esc(String(val).slice(0, 100)) + '…';
      }

      if (h === 'Execution_Marks' && execMax !== -1 && val !== '') {
        const m = Number(val) || 0;
        const mx = Number(row['Execution_Max']) || 1;
        const ratio = m / mx;
        cls = ratio >= 1 ? 'score-full' : ratio > 0 ? 'score-partial' : 'score-zero';
        display = `${m}<span class="score-max">/${mx}</span>`;
      }

      return `<td class="${cls}" title="${esc(String(val))}">${display}</td>`;
    }).join('') + '</tr>';
  }).join('');
}

function renderRubricTable(headers, rows) {
  document.getElementById('rubric-results-title').textContent =
    `Rubric report — ${rows.length} student${rows.length !== 1 ? 's' : ''}`;

  const thead = document.getElementById('rubric-thead');
  const tbody = document.getElementById('rubric-tbody');
  const fixedCols = new Set(['Student_ID', 'File', 'Total_Score', 'Max_Score', 'Feedback']);
  const totalIdx = headers.indexOf('Total_Score');
  const maxIdx = headers.indexOf('Max_Score');
  const rubricCols = headers.filter(h => !fixedCols.has(h));

  const colMax = {};
  rubricCols.forEach(h => {
    colMax[h] = Math.max(...rows.map(r => Number(r[h]) || 0));
  });

  thead.innerHTML = '<tr>' + headers.map(h => `<th>${esc(h.replace(/_/g, ' '))}</th>`).join('') + '</tr>';

  tbody.innerHTML = rows.map(row => {
    return '<tr>' + headers.map((h, i) => {
      let val = row[h] ?? '';
      let cls = '';
      let display = esc(String(val));

      if (rubricCols.includes(h) && val !== '') {
        const n = Number(val);
        const max = colMax[h] || 1;
        const ratio = n / max;
        cls = ratio >= 1 ? 'score-full' : ratio > 0 ? 'score-partial' : 'score-zero';
        display = `${n}<span class="score-max">/${max}</span>`;
      } else if (i === totalIdx && maxIdx !== -1) {
        const total = Number(val) || 0;
        const max = Number(row['Max_Score']) || 1;
        const pct = Math.round(total / max * 100);
        display = `${total} <span class="score-max">(${pct}%)</span>`;
      } else if (h === 'Feedback') {
        display = val ? `<span title="${esc(String(val))}" style="cursor:help">⚠ hover</span>` : '';
      }
      return `<td class="${cls}" title="${esc(String(val))}">${display}</td>`;
    }).join('') + '</tr>';
  }).join('');
}

document.getElementById('btn-refresh-compile').addEventListener('click', tryLoadCompileResults);
document.getElementById('btn-refresh-execution').addEventListener('click', tryLoadExecutionResults);
document.getElementById('btn-refresh-rubric').addEventListener('click', tryLoadRubricResults);

document.getElementById('btn-download-compile-csv').addEventListener('click', () => {
  downloadCsv(csvCompile, 'results_compile.csv');
});
document.getElementById('btn-download-execution-csv').addEventListener('click', () => {
  downloadCsv(csvExecution, 'results_execution.csv');
});
document.getElementById('btn-download-rubric-csv').addEventListener('click', () => {
  downloadCsv(csvRubric, 'results_rubric.csv');
});

function downloadCsv(data, filename) {
  if (!data.headers?.length) return;
  const lines = [
    data.headers.map(csvCell).join(','),
    ...data.rows.map(row => data.headers.map(h => csvCell(row[h] ?? '')).join(',')),
  ];
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function csvCell(val) {
  const s = String(val);
  return (s.includes(',') || s.includes('"') || s.includes('\n'))
    ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const spinStyle = document.createElement('style');
spinStyle.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
document.head.appendChild(spinStyle);

checkServer();
setInterval(() => { if (!connected) checkServer(); }, 5000);
