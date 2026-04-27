/**
 * tests.js — Edit per-suite stdin/expected pairs (saved on companion server).
 */

const SERVER_KEY = 'clint_server_url';
let SERVER = localStorage.getItem(SERVER_KEY) || 'http://localhost:5001';

const banner = document.getElementById('tests-banner');
const root = document.getElementById('suites-root');

function showBanner(text, cls = '') {
  banner.className = 'banner-tests ' + cls;
  banner.innerHTML = text;
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function ping() {
  try {
    const res = await fetch(`${SERVER}/api/ping`, { signal: AbortSignal.timeout(2500) });
    return res.ok;
  } catch (_) {
    return false;
  }
}

function caseRowHtml(suiteName, index, stdin, expected) {
  const n = index + 1;
  return `
    <div class="case-card" data-case-index="${index}">
      <div class="case-head">
        <span>Case ${String(n).padStart(2, '0')}</span>
        <button type="button" class="btn btn-ghost btn-sm btn-remove-case">Remove</button>
      </div>
      <div class="case-grid">
        <div>
          <label>Stdin</label>
          <textarea class="inp-stdin" spellcheck="false">${esc(stdin)}</textarea>
        </div>
        <div>
          <label>Expected stdout</label>
          <textarea class="inp-expected" spellcheck="false">${esc(expected)}</textarea>
        </div>
      </div>
    </div>`;
}

function suiteBlockHtml(suite) {
  let cases = suite.cases && suite.cases.length
    ? suite.cases.map((c, i) => caseRowHtml(suite.name, i, c.stdin, c.expected))
    : [caseRowHtml(suite.name, 0, '', '')];
  return `
    <section class="suite-block" data-suite="${esc(suite.name)}">
      <h2>${esc(suite.name)}</h2>
      <div class="cases-list">${cases.join('')}</div>
      <div class="suite-toolbar">
        <button type="button" class="btn btn-ghost btn-sm btn-add-case">Add case</button>
        <button type="button" class="btn btn-primary btn-sm btn-save-suite">Save ${esc(suite.name)}</button>
      </div>
    </section>`;
}

function collectCases(section) {
  const cards = section.querySelectorAll('.case-card');
  const cases = [];
  cards.forEach(card => {
    cases.push({
      stdin: card.querySelector('.inp-stdin')?.value ?? '',
      expected: card.querySelector('.inp-expected')?.value ?? '',
    });
  });
  return cases;
}

function renumberCases(section) {
  section.querySelectorAll('.case-card').forEach((card, i) => {
    card.dataset.caseIndex = String(i);
    const head = card.querySelector('.case-head span');
    if (head) head.textContent = `Case ${String(i + 1).padStart(2, '0')}`;
  });
}

root.addEventListener('click', e => {
  const add = e.target.closest('.btn-add-case');
  const rem = e.target.closest('.btn-remove-case');
  const save = e.target.closest('.btn-save-suite');
  const section = e.target.closest('.suite-block');
  if (!section) return;
  const suiteName = section.dataset.suite;

  if (add) {
    const list = section.querySelector('.cases-list');
    const idx = list.querySelectorAll('.case-card').length;
    list.insertAdjacentHTML('beforeend', caseRowHtml(suiteName, idx, '', ''));
    renumberCases(section);
  }
  if (rem) {
    const cards = section.querySelectorAll('.case-card');
    if (cards.length <= 1) {
      const ta = cards[0]?.querySelectorAll('textarea');
      if (ta) ta.forEach(t => { t.value = ''; });
      return;
    }
    e.target.closest('.case-card')?.remove();
    renumberCases(section);
  }
  if (save) {
    saveSuite(suiteName, section);
  }
});

async function saveSuite(suiteName, section) {
  const cases = collectCases(section);
  try {
    const res = await fetch(`${SERVER}/api/test-suites/${encodeURIComponent(suiteName)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cases }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showBanner(esc(data.error || res.statusText), 'error');
      return;
    }
    showBanner(
      `Saved <strong>${esc(suiteName)}</strong> — ${data.saved} case file pair(s) on the grader server disk (local <code>server.py</code> machine).`,
      'ok'
    );
  } catch (err) {
    showBanner(esc(String(err.message || err)), 'error');
  }
}

async function loadSuites() {
  root.innerHTML = '';
  const ok = await ping();
  if (!ok) {
    showBanner(
      'Cannot reach the grader server at <code>' + esc(SERVER) + '</code>. ' +
      'Set the server URL on the <a href="index.html">Grade</a> page and retry.',
      'error'
    );
    return;
  }
  try {
    const res = await fetch(`${SERVER}/api/test-suites`);
    if (!res.ok) {
      showBanner('Failed to load test suites: ' + res.status, 'error');
      return;
    }
    const data = await res.json();
    const strat = esc(data.test_suite_strategy || 'mod3_id_charsum');
    const use = data.use_test_suites ? 'On' : 'Off';
    showBanner(
      `Connected — cases load/save on this server only. Suite assignment: <code>${strat}</code> · File suites on Grade page: <strong>${use}</strong>.`,
      'ok'
    );
    if (!data.suites?.length) {
      root.innerHTML = '<p style="color:var(--text-muted)">No suites in config.</p>';
      return;
    }
    root.innerHTML = data.suites.map(s => suiteBlockHtml(s)).join('');
  } catch (err) {
    showBanner(esc(String(err.message || err)), 'error');
  }
}

loadSuites();
