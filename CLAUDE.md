# C-Lab Autograder (clint)

## What This Is

A client-side web app hosted on GitHub Pages at `nishantkapps.github.io/clint` plus a **Python companion server** (`server.py`) that runs on the instructor’s machine (or SSH server). The browser UI triggers `grader.py`, which uses **gcc** to compile, runs binaries, compares stdout to expected output, and scores rubric items (static regex / LLM / file-based tests).

## Architecture

- **GitHub Pages**: `index.html` (grader), `rubric.html` (rubric editor) — vanilla JS, no build step
- **Companion server** (`server.py`): Flask + CORS; exposes `/api/run-compile`, `/api/run-rubric`, `/api/stream`, `/api/results-compile`, `/api/results-rubric`, `/api/config`, `/api/rubric`
- **Grader** (`grader.py`): Two modes — `--mode compile-run` (compile + run + execution marks vs `expected_output` in config) and `--mode rubric` (rubric columns only → `results_rubric.csv`)
- **localStorage**: Rubric editor state + default seed; Grader page stores **Server URL** (`clint_server_url`)
- **config.json** (on server): paths, `stdin_for_run`, `expected_output`, `execution_max_marks`, LLM keys, CSV output paths

## Key Commands

```bash
# Static site local preview
python3 -m http.server 8787
# http://localhost:8787/rubric.html

# Companion + grading (on machine with gcc + submissions)
python3 server.py                    # localhost:5001
python3 server.py --host 0.0.0.0 --port 5001   # remote browser access

python3 grader.py --mode compile-run
python3 grader.py --mode rubric

# Deploy UI: push to main — GitHub Actions → Pages
git add . && git commit -m "message" && git push
```

## Project Layout

```
clint/
├── index.html
├── rubric.html
├── css/style.css
├── js/app.js               # Grader UI (two phases, two tables)
├── js/rubric.js            # Rubric CRUD + default seed
├── grader.py
├── server.py
├── config.json
├── rubric.json             # optional sample / server copy
├── submissions/            # gitignored
├── results_compile.csv     # gitignored
├── results_rubric.csv      # gitignored
├── README.md
└── .github/workflows/pages.yml
```

## Conventions

- Bump `?v=` on `<script>` / `<link>` in HTML after JS/CSS changes (cache bust on Pages)
- Rubric JSON from the editor: same shape as `rubric.json` on the server (`items` array)
- GitHub Pages source: **GitHub Actions** (repo Settings → Pages)
