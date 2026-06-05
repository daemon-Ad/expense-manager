import sqlite3
import requests
import logging
import os
from datetime import datetime

# --- Logger Setup ---
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/sync_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_filename)]
)
log = logging.getLogger(__name__)

# --- Config ---
EZBOOK_URL = "http://localhost:8080"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyVG9rZW5JZCI6IjM4NzY2MzMyMjE5NjE4MTQxMjQiLCJqdGkiOiIzODIzOTQwOTUzNjQzNjc5NzQ0IiwidXNlcm5hbWUiOiJhZGl0eWEiLCJ0eXBlIjo4LCJpYXQiOjE3ODA2NjE3ODUsImV4cCI6MTc4MDc0ODE4NX0.8QKdnN32odDA8i1FtH1LthGE-SAkACDQa7TJJOr_r8Q"
ACCOUNT_ID = "3823945800648491008"
UTC_OFFSET = 330

CATEGORY_MAP = {
    "Food":          "3823990129274388480",
    "Education":     "3823990191551414272",
    "Travel":        "3823990255975923712",
    "Entertainment": "3823990318252949504",
    "Movies":        "3823990318252949504",
}
MISC_ID = "3823990333285335040"
SKIP_NOTES = {"Automation Trial", "Failed"}

# --- Main ---
log.info("Sync started")

con = sqlite3.connect("transactions.db")
cur = con.cursor()

cur.execute("""
    SELECT idempotency_id, name, amount, transaction_time, note
    FROM transactions
    WHERE synced = 0 AND status = 'SUCCESS'
""")
rows = cur.fetchall()
log.info(f"Found {len(rows)} unsynced transactions")

for idempotency_id, name, amount, transaction_time, note in rows:
    if note in SKIP_NOTES:
        cur.execute("UPDATE transactions SET synced = 1 WHERE idempotency_id = ?", (idempotency_id,))
        con.commit()
        log.info(f"Skipped: {name} | {note}")
        continue

    dt = datetime.fromisoformat(transaction_time.replace('Z', '+00:00'))
    unix_time = int(dt.timestamp())
    category_id = CATEGORY_MAP.get(note, MISC_ID)

    payload = {
        "type": 3,
        "categoryId": category_id,
        "time": unix_time,
        "utcOffset": UTC_OFFSET,
        "sourceAccountId": ACCOUNT_ID,
        "sourceAmount": int(float(amount) * 100),
        "comment": name,
        "hideAmount": False,
        "clientSessionId": idempotency_id
    }

    try:
        r = requests.post(
            f"{EZBOOK_URL}/api/v1/transactions/add.json",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "X-Timezone-Name": "Asia/Kolkata",
                "X-Timezone-offset": "330"
            },
            json=payload,
            timeout=10
        )

        if r.status_code == 200:
            cur.execute("UPDATE transactions SET synced = 1 WHERE idempotency_id = ?", (idempotency_id,))
            con.commit()
            log.info(f"Synced: {name} ₹{amount} [{note}]")
        else:
            log.error(f"Failed: {name} → {r.status_code} {r.text}")

    except Exception as e:
        log.error(f"Exception syncing {name}: {e}")

con.close()
log.info("Sync finished")
