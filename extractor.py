import re
import sqlite3
import logging
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

# --- Logger Setup ---
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/extractor_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_filename)]
)
log = logging.getLogger(__name__)

# --- DB Setup ---
con = sqlite3.connect("transactions.db")
cur = con.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        idempotency_id   TEXT PRIMARY KEY,
        name             TEXT,
        payment_method   TEXT,
        display_time     TEXT,
        transaction_time TEXT,
        amount           REAL,
        status           TEXT,
        type             TEXT,
        detail_url       TEXT,
        note             TEXT,
        synced           INTEGER DEFAULT 0,
        inserted_at      TEXT DEFAULT (datetime('now'))
    )
""")
con.commit()

INSERT_SQL = """
    INSERT OR IGNORE INTO transactions
        (idempotency_id, name, payment_method, display_time,
         transaction_time, amount, status, type, detail_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

def save_to_db(transactions):
    new_count = 0
    for t in transactions:
        td = t.get('transactionDetails', {})
        url = t.get('transactionDetailPageURL', '')

        match = re.search(r'idempotencyId=([^&]+)', url)
        if not match:
            log.warning("No idempotencyId found, skipping")
            continue
        idempotency_id = match.group(1)

        cur.execute(INSERT_SQL, (
            idempotency_id,
            (td.get('authenticator') or '').removeprefix('Paid to ').strip(),
            td.get('authenticatorTwo'),
            td.get('authenticatorThree'),
            td.get('date'),
            float(td.get('amount', 0)),
            td.get('status'),
            td.get('type'),
            url,
        ))
        if cur.execute("SELECT changes()").fetchone()[0]:
            new_count += 1

    con.commit()
    return new_count

def fetch_notes(page):
    cur.execute("""
        SELECT idempotency_id, detail_url FROM transactions
        WHERE note IS NULL AND status = 'SUCCESS'
    """)
    rows = cur.fetchall()
    log.info(f"Fetching notes for {len(rows)} transactions")

    for idempotency_id, url in rows:
        try:
            page.goto(url, wait_until="domcontentloaded")

            page.wait_for_function("""
                () => {
                    const outer = document.querySelector('payui-transaction-receipt')?.shadowRoot;
                    const inner = outer?.querySelector('payment-status-header')?.shadowRoot;
                    return !!inner?.querySelector('tux-text.payment-note');
                }
            """, timeout=8000)

            note = page.evaluate("""
                () => {
                    const outer = document.querySelector('payui-transaction-receipt')?.shadowRoot;
                    const inner = outer?.querySelector('payment-status-header')?.shadowRoot;
                    return inner?.querySelector('tux-text.payment-note')?.textContent?.trim() ?? null;
                }
            """)

            note = note.strip().title()

            cur.execute(
                "UPDATE transactions SET note = ? WHERE idempotency_id = ?",
                (note, idempotency_id)
            )
            con.commit()
            log.info(f"Note fetched: {idempotency_id[-10:]} → {note}")

        except Exception as e:
            log.error(f"Failed note fetch {idempotency_id[-10:]}: {e}")

# --- Main ---
log.info("Extractor started")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir="./playwright-profile",
        headless=False,
    )

    page = context.new_page()
    log.info("Navigating to Amazon Pay history")
    page.goto("https://www.amazon.in/pay/history?ref_=apay_deskhome_ViewStatement")

    try:
        page.wait_for_function("""
            () => {
                const w = document.querySelector('payui-transaction-history-wrapper');
                if (!w) return false;
                const attr = w.getAttribute('transactions');
                if (!attr) return false;
                try { return JSON.parse(attr).length > 0; }
                catch { return false; }
            }
        """, timeout=15000)
        log.info("Transaction page loaded successfully")
    except Exception as e:
        log.error(f"Page failed to load: {e}")
        context.close()
        con.close()
        exit(1)

    # Step 1: scrape latest 20
    transactions = page.evaluate("""
        () => {
            const w = document.querySelector('payui-transaction-history-wrapper');
            return JSON.parse(w.getAttribute('transactions'));
        }
    """)
    new = save_to_db(transactions)
    log.info(f"Inserted {new} new | Skipped {len(transactions) - new} duplicates")

    # Step 2: fetch notes for all rows missing them
    fetch_notes(page)

    context.close()

con.close()
log.info("Extractor finished")
