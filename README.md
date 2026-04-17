# C-Lab Autograder (clint)

A web-based autograder for C programming labs. The UI is hosted on GitHub Pages and talks to a companion Python server that runs `gcc`, scores rubric items, and generates a results CSV.

**Live app:** https://nishantkapps.github.io/clint

---

## How It Works

```
Browser (GitHub Pages)
    │
    │  HTTP (fetch / SSE)
    ▼
server.py  ──►  grader.py  ──►  gcc  ──►  results.csv
    │                └──►  LLM API (optional, for llm-type rubric items)
    └── reads rubric.json + submissions/
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
   - **Name** — becomes a column header in the results CSV (`Rubric_1`, `Rubric_2`, …)
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

### Run the Grader

1. Start `server.py` on the machine that has the `.c` files (see setup above)
2. Open https://nishantkapps.github.io/clint
3. Check paths in the config panel (submissions folder, rubric file, output CSV)
4. If using LLM items, enter your API key in the **LLM Grading** section
5. Click **Run Grader**
6. Watch the live progress log — each file shows ✓ or ✗
7. Results appear in the table below, colour-coded by score
8. Click **Download CSV** to save the spreadsheet

### Results CSV columns

```
Student_ID | File | Compiles | Compile_Error | Rubric_1 | Rubric_2 | ... | Total_Score | Max_Score | Feedback
```

---

## Configuration (`config.json`)

| Key | Default | Description |
|-----|---------|-------------|
| `submissions_dir` | `./submissions` | Folder containing student `.c` files |
| `rubric_file` | `./rubric.json` | Rubric exported from the editor |
| `output_csv` | `./results.csv` | Where to write the results |
| `tests_dir` | `./test_cases` | Root folder for test case pairs |
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
| `after_last_underscore` | `lab1_2025A5PS0838H.c` | `2025A5PS0838H` |
| `whole_filename` | `2025A5PS0838H.c` | `2025A5PS0838H` |
| `regex` | any | first capture group of your regex |

---

## Command Reference

```bash
# Start server (local)
python3 server.py

# Start server (remote — accessible from browser)
python3 server.py --host 0.0.0.0 --port 5001

# Run grader from command line (no browser needed)
python3 grader.py
python3 grader.py --submissions ./submissions --rubric rubric.json --output results.csv

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
├── grader.py               # Grading engine (static / LLM / test scoring)
├── server.py               # Flask companion server
├── config.json             # Runtime configuration
├── rubric.json             # Active rubric (edit via rubric.html, then copy here)
├── submissions/            # Drop student .c files here (git-ignored)
├── test_cases/             # test_cases/<key>/input_N.txt + expected_N.txt
├── results.csv             # Generated output (git-ignored)
├── requirements.txt        # Python dependencies
├── CLAUDE.md               # Developer reference
└── .github/workflows/
    └── pages.yml           # Deploy to GitHub Pages on push to main
```
