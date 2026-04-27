# C-Lab Autograder (clint)

## What This Is

A client-side web app hosted on GitHub Pages at `nishantkapps.github.io/clint` plus a **Python companion server** (`server.py`) that runs on the instructor’s machine (or SSH server). The browser UI triggers `grader.py`, which uses **gcc** to compile, runs binaries in a separate execution phase against test cases, and scores rubric items (static regex / LLM / file-based tests).

## Architecture

- **GitHub Pages**: `index.html` (grader), `rubric.html` (rubric editor) — vanilla JS, no build step
- **Companion server** (`server.py`): Flask + CORS; same process also serves the static UI at `/`, `/index.html`, `/rubric.html`, `/tests.html`, `/css/`, `/js/` so you can open `http://127.0.0.1:5001/` and use the same origin as `/api/...` (avoids mixed-content and many `NetworkError` cases). API routes: `/api/run-compile`, `/api/run-execution`, `/api/run-rubric`, `/api/stream`, results, config, rubric, test-suites.
- **Grader** (`grader.py`): Modes — `compile`, `execution`, `rubric`; **`compile-run`** is a legacy alias (compile then execution, writes both CSVs). `gcc file.c -o <build_output_dir>/<stem> -lm` for compile; execution uses file suites or `stdin_for_run` / `expected_output`; rubric → `results_rubric.csv`. Executables stay under `build_output_dir` (default `./output`).
- **localStorage**: Rubric editor state + default seed; Grader page stores **Server URL** (`clint_server_url`)
- **config.json** (on server, gitignored): copy from `config.example.json`; paths, test suite flags, LLM keys, CSV paths. Never commit real API keys — GitHub push protection will block the push.

## Key Commands

```bash
# Static site local preview
python3 -m http.server 8787
# http://localhost:8787/rubric.html

# Companion + grading (on machine with gcc + submissions)
python3 server.py                    # localhost:5001
python3 server.py --host 0.0.0.0 --port 5001   # remote browser access

python3 grader.py --mode compile
python3 grader.py --mode execution
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
├── js/app.js               # Grader UI (compile, execution, rubric; three tables)
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
