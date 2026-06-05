# Expense Automation

Scrapes Amazon Pay UPI transactions and syncs to local ezBookkeeping instance.

## Dependencies
- Python 3.12+
- Playwright
- ezBookkeeping binary

## Setup

1. Clone repo
2. Create venv and install dependencies
```bash
python -m venv venv
source venv/bin/activate
pip install playwright python-dotenv requests
playwright install chromium
```

3. Copy `.env.example` to `.env` and fill in values
```bash
cp .env.example .env
```

4. Download ezBookkeeping binary, place in `ezbookkeeping/` directory

5. Run ezBookkeeping once manually to create account and categories, get API token
```bash
cd ezbookkeeping && ./ezbookkeeping server run
```

6. Add to `~/.zshrc`:
```bash
sync_and_shutdown() {
    ~/Projects/Expense-automation/venv/bin/python ~/Projects/Expense-automation/main.py
    if [ $? -eq 0 ]; then
        sudo shutdown -h +20
    else
        echo "SYNC FAILED! Shutdown aborted."
    fi
}
alias off="sync_and_shutdown"
```

## First Run
On a new machine, you need to log into Amazon Pay manually once so Playwright can save the session:
```bash
source venv/bin/activate
python extractor.py  # set headless=False temporarily
# log in manually, then Ctrl+C
# set headless back and run normally
```

## Files
- `extractor.py` — scrapes Amazon Pay, saves to SQLite
- `sync.py` — pushes SQLite data to ezBookkeeping API
- `main.py` — orchestrates everything
- `transactions.db` — local SQLite database (gitignored)
- `logs/` — timestamped logs per run (gitignored)

## Category Mapping
Notes written in Amazon Pay transaction description map to ezBookkeeping categories.
Supported: `Food`, `Education`, `Travel`, `Entertainment`, `Movies`
Anything else → `Miscellaneous`
