"""Run the dashboard, with an optional Cloudflare tunnel for a demonstration."""
import argparse
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--share", action="store_true", help="requires an installed cloudflared executable")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    tunnel_exe = shutil.which("cloudflared")
    if args.share and not tunnel_exe:
        parser.error("Install cloudflared before using --share, or run without --share.")
    if not (ROOT / "data" / "processed_data.csv").is_file():
        parser.error("Missing data/processed_data.csv; run the analysis notebook first.")
    command = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
               "--server.port", str(args.port), "--server.headless", "true"]
    server = subprocess.Popen(command, cwd=ROOT)
    tunnel = None
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("Streamlit exited before startup completed")
            try:
                with urllib.request.urlopen(f"http://localhost:{args.port}/_stcore/health", timeout=1):
                    break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(1)
        else:
            raise RuntimeError("Streamlit did not become ready within one minute")
        print(f"Dashboard: http://localhost:{args.port}", flush=True)
        if args.share:
            tunnel = subprocess.Popen([tunnel_exe, "tunnel", "--url", f"http://localhost:{args.port}"])
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in (tunnel, server):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
