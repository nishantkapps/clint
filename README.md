# C-Lab Autograder (clint)

A web-based autograder for C programming labs. The UI is hosted on GitHub Pages and talks to a companion Python server that runs `gcc`, runs programs against test cases, and scores rubric items in **separate phases** (three result tables: compile, execution, rubric; three CSV files).

**Live app:** https://nishantkapps.github.io/clint

---

## How It Works

```
Browser (GitHub Pages)
    │
    │  HTTP (fetch / SSE)
    ▼
server.py  ──►  grader.py --mode compile    ──►  gcc only      ──►  results_compile.csv
         ├──►  grader.py --mode execution ──►  run binaries  ──►  results_execution.csv
         └──►  grader.py --mode rubric     ──►  gcc + LLM     ──►  results_rubric.csv
```

The browser never touches student code. All compilation and grading happens on the machine running `server.py`.

---

## Setup — Remote Server (SSH access)

This is the recommended workflow when student code files are on a remote Linux server.

### 1. SSH into the server

```bash
ssh your-username@your-server-ip
```

### 2. Install dependencies (one-time)

```bash
sudo apt-get update
sudo apt-get install -y git gcc python3 python3-pip

git clone https://github.com/nishantkapps/clint.git
cd clint
pip3 install flask flask-cors litellm
cp config.example.json config.json   # local only — config.json is gitignored; never commit API keys
```

### 3. Place student submissions

Student `.c` files go in the `submissions/` folder. File names must contain the student ID — the default format is:

```
<StudentID>_<anything>.c
e.g.  2025A5PS0838H_lab1.c
```

```bash
# Copy files from wherever they are uploaded, e.g.:
cp /path/to/uploads/*.c ~/clint/submissions/
```

### 4. Copy your rubric (optional)

If you have a `rubric.json` exported from the Rubric Editor, copy it across:

```bash
scp rubric.json your-username@your-server-ip:~/clint/
```

Or you can create and export one from https://nishantkapps.github.io/clint/rubric.html and upload it manually.

### 5. Start the companion server

```bash
cd ~/clint
python3 server.py --host 0.0.0.0 --port 5001
```

> **Important:** `--host 0.0.0.0` makes the server reachable from outside. Make sure port `5001` is open in the server's firewall.

You should see:

```
============================================================
  C-Lab Autograder — Companion Server
============================================================
  Listening on:  http://<your-server-ip>:5001
  Remote access enabled.
  Enter  http://<this-server-ip>:5001  in the
  'Server URL' field on the Grader page.
============================================================
```

### 6. Open the app and connect

1. Go to https://nishantkapps.github.io/clint
2. Click **Change URL** in the server banner
3. Enter `http://<your-server-ip>:5001`
4. Click **Connect** — the dot turns green

---

## Setup — Local Machine (Ubuntu)

Use this if student code files are on your own Ubuntu machine.

### 1. Install dependencies (one-time)

```bash
sudo apt-get install -y gcc python3 python3-pip
cd /path/to/clint
pip3 install flask flask-cors litellm
```

### 2. Start the server

```bash
python3 server.py
# Listens on http://localhost:5001 by default
```

### 3. Open the app

Go to https://nishantkapps.github.io/clint — the server banner will show green automatically (default URL is `localhost:5001`).

---

## Setup — SSH Tunnel (run server remotely, access as localhost)

If the server is behind a firewall and you cannot open port 5001 publicly:

```bash
# Terminal 1 — on the remote server
ssh your-username@your-server-ip
cd clint && python3 server.py   # binds to 127.0.0.1:5001 (default)

# Terminal 2 — on your local machine
ssh -L 5001:localhost:5001 your-username@your-server-ip -N
```

The app at https://nishantkapps.github.io/clint connects to `localhost:5001` which tunnels transparently to the remote server. No URL change needed.

---

## Usage

### Build a Rubric

1. Go to https://nishantkapps.github.io/clint/rubric.html
2. Edit the default rubric items or add new ones
3. Each item has:
   - **Name** — shown in the Rubric key on the Grader page; CSV uses generic columns `Rubric_1`, `Rubric_2`, …
   - **Condition** — description of what the student must do
   - **Type** — see table below
   - **Max Marks** — points available for this criterion
   - **Patterns** — (static type only) one regex per line; grader checks the code against each
4. Click **Save JSON** — download the `rubric.json` file
5. Place `rubric.json` in the `clint/` folder on the server

### Rubric Item Types

| Type | How it is scored |
|------|-----------------|
| `static` | Regex patterns are matched against the student's `.c` source file. All patterns matched = full marks. Partial match = partial marks. |
| `llm` | The student's code and the criterion description are sent to an LLM (Claude or GPT). The LLM returns a score and a reason. |
| `test` | The compiled binary is run against input/expected-output pairs in `test_cases/<key>/`. Score is proportional to test cases passed. |

### Run grading (three separate steps)

1. Start `server.py` on the machine that has the `.c` files (see setup above).
2. Open https://nishantkapps.github.io/clint (set **Server URL** if using a remote machine).
3. **Compile** — For each `IDNumber.c`, the grader runs **`gcc /path/to/IDNumber.c -o <build_output_dir>/IDNumber -w -lm`**. The executable has the **same basename as the source file** (no `.c`). Binaries are **left in `build_output_dir`** so you can inspect them. Click **Run compile** (no execution in this step).
4. **Execution** — Set **Expected stdout**, optional **Stdin**, and **Execution max marks**, or enable **file-based test suites** and edit cases on the **Test cases** page. Click **Run execution** to run each retained binary (2s timeout per run), score stdout vs expected output (exact match after normalization = full marks; otherwise partial marks via `difflib`).
5. **Rubric scoring** — Ensure `rubric.json` is on the server. Enter LLM API key if you use `llm` items. Click **Run rubric scoring** when you want rubric-only results.
6. Three tables appear: **Compile report**, **Execution report**, and **Rubric report**, each with Refresh and Download CSV.

### Result files

| File | Written by |
|------|------------|
| `results_compile.csv` (path: `output_compile_csv`) | **Run compile** |
| `results_execution.csv` (path: `output_execution_csv`) | **Run execution** |
| `results_rubric.csv` (path: `output_rubric_csv`) | **Run rubric scoring** |

**Compile report columns:** `Student_ID`, `Filename`, `Compiles`, `Compile_Error`

**Execution report columns:** `Student_ID`, `Filename`, `Binary_Path`, `Test_Suite`, `Execution_Marks`, `Execution_Max`, `Match_Pct`, `Execution_Note`, `Run_Error`, `Stdout`, `Stderr`

**Rubric report columns:** `Student_ID`, `File`, `Rubric_1`, `Rubric_2`, …, `Total_Score`, `Max_Score`, `Feedback` (compile status is not included — use the compile report for that.)

---

## Configuration (`config.json`, not committed)

| Key | Default | Description |
|-----|---------|-------------|
| `build_output_dir` | `./output` | Where `gcc -o` writes executables (same stem as each `.c` file) |
| `submissions_dir` | `./submissions` | Folder containing student `.c` files |
| `rubric_file` | `./rubric.json` | Rubric exported from the editor |
| `output_compile_csv` | `./results_compile.csv` | Compile-only report |
| `output_execution_csv` | `./results_execution.csv` | Execution / test-case report |
| `output_rubric_csv` | `./results_rubric.csv` | Rubric-only report |
| `stdin_for_run` | `""` | Text fed to stdin when running each compiled binary |
| `expected_output` | `""` | Expected stdout for execution scoring (exact = full marks) |
| `compilation_max_marks` | `5` | Max points for successful compilation (0 if compile fails) |
| `execution_max_marks` | `10` | Max points for the execution / output match column |
| `tests_dir` | `./test_cases` | Root folder for rubric `test`-type items |
| `id_extraction.strategy` | `before_first_underscore` | How to extract student ID from filename |
| `compile_timeout_seconds` | `10` | Max seconds for gcc to compile |
| `run_timeout_seconds` | `2` | Max seconds for binary to run (prevents infinite loops) |
| `llm_provider` | `anthropic` | `anthropic` or `openai` |
| `llm_model` | `claude-3-haiku-20240307` | Model name passed to litellm |
| `llm_api_key` | `""` | Your API key (set via the UI — never committed) |

### ID extraction strategies

| Strategy | Example filename | Extracted ID |
|----------|-----------------|--------------|
| `before_first_underscore` | `2025A5PS0838H_lab1.c` | `2025A5PS0838H` |
| `whole_filename` | `2025A5PS0838H.c` (ID-only filename) | `2025A5PS0838H` (use this when files are named `IDNumber.c`) |
| `after_last_underscore` | `lab1_2025A5PS0838H.c` | `2025A5PS0838H` |
| `regex` | any | first capture group of your regex |

---

## Command Reference

```bash
# Start server (local)
python3 server.py

# Start server (remote — accessible from browser)
python3 server.py --host 0.0.0.0 --port 5001

# Run grader from command line (no browser needed)
python3 grader.py --mode compile
python3 grader.py --mode execution
python3 grader.py --mode rubric
python3 grader.py --mode compile-run   # legacy: compile then execution (both CSVs)
python3 grader.py --config config.json --mode compile

# Update the app (pulls latest code and redeploys via GitHub Actions)
git pull && git push
```

---

## Project Layout

```
clint/
├── index.html              # Grader page
├── rubric.html             # Rubric editor
├── css/style.css           # Shared styles
├── js/
│   ├── app.js              # Grader page logic
│   └── rubric.js           # Rubric editor logic
├── grader.py               # Modes: compile | execution | rubric
├── server.py               # Flask companion server
├── config.example.json     # Copy to config.json (gitignored) — never commit API keys
├── rubric.json             # Active rubric (edit via rubric.html, then copy here)
├── output/                 # gcc -o executables kept here (git-ignored)
├── submissions/            # Drop student .c files here (git-ignored)
├── test_cases/             # test_cases/<key>/input_N.txt + expected_N.txt
├── results_compile.csv     # Generated (git-ignored)
├── results_execution.csv   # Generated (git-ignored)
├── results_rubric.csv      # Generated (git-ignored)
├── requirements.txt        # Python dependencies
├── CLAUDE.md               # Developer reference
└── .github/workflows/
    └── pages.yml           # Deploy to GitHub Pages on push to main
```
