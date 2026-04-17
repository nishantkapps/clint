# C-Lab Autograder (clint)

## What This Is

A client-side web app hosted on GitHub Pages at `nishantkapps.github.io/clint` that lets instructors define a marking rubric for C programming labs and (eventually) grade student submissions — all without a server.

## Architecture

- **Pure client-side**: HTML + CSS + vanilla JS, no build step
- **rubric.html**: Rubric editor — add/edit/delete/reorder grading criteria, save/load as JSON
- **index.html**: Grader — (in progress) upload submissions, run grading, download results CSV
- **localStorage**: Rubric state persisted in the browser between sessions
- **JSON**: Rubric exported/imported as `<lab>_rubric.json`

## Key Commands

```bash
# Local dev server
python3 -m http.server 8787
# then open http://localhost:8787/rubric.html

# Deploy: just push to main — GitHub Actions handles the rest
git add . && git commit -m "message" && git push
```

## Project Layout

```
clint/
├── index.html              # Grader page (in progress)
├── rubric.html             # Rubric editor
├── css/
│   └── style.css           # Shared styles (dark theme)
├── js/
│   └── rubric.js           # Rubric CRUD, localStorage, JSON save/load
└── .github/workflows/
    └── pages.yml           # Deploy to GitHub Pages on push to main
```

## Rubric JSON Format

```json
{
  "lab": "Lab 3 — Linked Lists",
  "created": "2026-04-17",
  "items": [
    {
      "id": "header_files_1234567890",
      "name": "Header Files",
      "condition": "Must include stdio.h and stdlib.h",
      "type": "static",
      "max_marks": 2
    }
  ]
}
```

## Grading Types (planned)

| Type     | How it works                                      |
|----------|---------------------------------------------------|
| `static` | Regex pattern match against the student's .c file |
| `llm`    | AI model evaluates the code against the criterion |
| `test`   | Compile + run against test cases, check output    |

## Conventions

- No build step — vanilla JS only
- After changing `css/style.css` or any JS file, bump the `?v=` query string on the `<link>`/`<script>` tags in HTML so GitHub Pages visitors get fresh assets
- Rubric JSON files are **not** committed — they live on the instructor's machine
- GitHub Pages source must be set to **GitHub Actions** in repo Settings → Pages
