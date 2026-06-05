import os
import subprocess
import time
import requests
import sys
import socket

# Paths
PROJECT_ROOT = os.path.expanduser("~/Projects/Expense-automation")
EZ_DIR = os.path.join(PROJECT_ROOT, "ezbookkeeping")
PYTHON_EXEC = os.path.join(PROJECT_ROOT, "venv/bin/python")

EZ_SERVER_CMD = ["./ezbookkeeping", "server", "run"]
EZ_HEALTH_URL = "http://localhost:8080"
PORT = 8080

def is_server_running(host="localhost", port=PORT):
    """Checks if the given port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def wait_for_server(url, timeout=30):
    """Polls the server until it responds via HTTP or times out."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url)
            if response.status_code in (200, 401, 403, 404): 
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False

def main():
    server_process = None
    server_was_running = is_server_running()

    try:
        # 1. Start or Borrow the Server
        if server_was_running:
            print(f"ezBookkeeping already running on port {PORT}, skipping startup.")
        else:
            print("Starting ezBookkeeping server...")
            server_process = subprocess.Popen(
                EZ_SERVER_CMD, 
                cwd=EZ_DIR, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            
            # 2. Wait for it to be ready (only necessary if we just started it)
            if not wait_for_server(EZ_HEALTH_URL):
                raise RuntimeError("Server failed to start within timeout.")

        # 3. Run Extractor
        print("Running extractor...")
        extractor_result = subprocess.run([PYTHON_EXEC, "extractor.py"], cwd=PROJECT_ROOT)
        if extractor_result.returncode != 0:
            raise RuntimeError(f"Extractor failed!")

        # 4. Run Sync
        print("Running sync...")
        sync_result = subprocess.run([PYTHON_EXEC, "sync.py"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        if sync_result.returncode != 0:
            raise RuntimeError(f"Sync failed:\n{sync_result.stderr}")

        print("Automation complete. All data synced successfully.")

    except Exception as e:
        print(f"Orchestration Error: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        # 5. Guaranteed Teardown (ONLY if we started the process ourselves)
        if server_process:
            print("Shutting down ezBookkeeping server...")
            server_process.terminate()
            server_process.wait()

if __name__ == "__main__":
    main()
