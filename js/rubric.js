/**
 * rubric.js — Rubric state management
 * Handles CRUD, localStorage persistence, JSON save/load, drag-to-reorder.
 */

const STORAGE_KEY = 'clint_rubric_v1';

const DEFAULT_RUBRIC = {
  lab: 'Lab 1 — C Basics',
  created: new Date().toISOString().slice(0, 10),
  items: [
    {
      id: 'default_header_files',
      name: 'Header_Files',
      condition: 'Must include stdio.h and stdlib.h',
      type: 'static',
      max_marks: 2,
      patterns: [
        '#include\\s*[<"]stdio\\.h[>"]',
        '#include\\s*[<"]stdlib\\.h[>"]'
      ]
    },
    {
      id: 'default_memory_mgmt',
      name: 'Memory_Management',
      condition: 'Uses malloc and free correctly — no memory leaks',
      type: 'static',
      max_marks: 5,
      patterns: [
        'malloc\\s*\\(',
        'free\\s*\\('
      ]
    },
    {
      id: 'default_print_output',
      name: 'Print_Output',
      condition: 'Uses printf to print output',
      type: 'static',
      max_marks: 3,
      patterns: [
        'printf\\s*\\('
      ]
    },
    {
      id: 'default_loop_logic',
      name: 'Loop_Logic',
      condition: 'Uses a loop construct (for or while)',
      type: 'static',
      max_marks: 5,
      patterns: [
        'for\\s*\\(',
        'while\\s*\\('
      ]
    },
    {
      id: 'default_pointer_logic',
      name: 'Pointer_Logic',
      condition: 'Correct use of pointers — dereferencing and pointer arithmetic',
      type: 'llm',
      max_marks: 5,
      patterns: []
    },
    {
      id: 'default_output_correct',
      name: 'Output_Correctness',
      condition: 'Program output matches expected results for all test cases',
      type: 'test',
      max_marks: 10,
      patterns: []
    }
  ]
};

let state = {
  lab: '',
  created: new Date().toISOString().slice(0, 10),
  items: []
};

/* ── Persistence ─────────────────────────────────────────── */

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      state = JSON.parse(raw);
    }
    // Seed defaults if nothing is saved OR saved state has no items
    if (!state.items || state.items.length === 0) {
      state = JSON.parse(JSON.stringify(DEFAULT_RUBRIC));
      state.created = new Date().toISOString().slice(0, 10);
      saveToStorage();
    }
  } catch (_) {
    state = JSON.parse(JSON.stringify(DEFAULT_RUBRIC));
    saveToStorage();
  }
}

function saveToStorage() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

/* ── CRUD ────────────────────────────────────────────────── */

function generateId(name) {
  return name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') + '_' + Date.now();
}

function addItem(item) {
  state.items.push({ id: generateId(item.name), ...item });
  saveToStorage();
}

function updateItem(id, patch) {
  const idx = state.items.findIndex(i => i.id === id);
  if (idx === -1) return;
  state.items[idx] = { ...state.items[idx], ...patch };
  saveToStorage();
}

function deleteItem(id) {
  state.items = state.items.filter(i => i.id !== id);
  saveToStorage();
}

function reorder(fromIdx, toIdx) {
  if (fromIdx === toIdx) return;
  const items = [...state.items];
  const [moved] = items.splice(fromIdx, 1);
  items.splice(toIdx, 0, moved);
  state.items = items;
  saveToStorage();
}

function setLab(name) {
  state.lab = name;
  saveToStorage();
}

function getState() { return state; }

/* ── JSON export / import ────────────────────────────────── */

function exportJSON() {
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const safeName = (state.lab || 'rubric').replace(/[^a-z0-9_\-]/gi, '_').toLowerCase();
  a.download = `${safeName}_rubric.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function importJSON(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result);
        if (!Array.isArray(parsed.items)) throw new Error('Invalid rubric JSON — missing items array');
        state = {
          lab: parsed.lab || '',
          created: parsed.created || new Date().toISOString().slice(0, 10),
          items: parsed.items
        };
        saveToStorage();
        resolve(state);
      } catch (err) { reject(err); }
    };
    reader.onerror = reject;
    reader.readAsText(file);
  });
}

/* ── Totals ──────────────────────────────────────────────── */

function totalMarks() {
  return state.items.reduce((sum, i) => sum + (Number(i.max_marks) || 0), 0);
}
