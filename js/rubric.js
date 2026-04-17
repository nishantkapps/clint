/**
 * rubric.js — Rubric state management
 * Handles CRUD, localStorage persistence, JSON save/load, drag-to-reorder.
 */

const STORAGE_KEY = 'clint_rubric_v1';

let state = {
  lab: '',
  created: new Date().toISOString().slice(0, 10),
  items: []
};

/* ── Persistence ─────────────────────────────────────────── */

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) state = JSON.parse(raw);
  } catch (_) {}
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
