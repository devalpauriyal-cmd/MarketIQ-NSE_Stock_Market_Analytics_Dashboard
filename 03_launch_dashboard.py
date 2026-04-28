# ============================================================
#  MarketIQ — Notebook 3: Launch Dashboard
#  Run AFTER Notebook 2 has completed.
#  Paste each CELL block into a separate Google Colab cell.
# ============================================================


# ══ CELL 19 ══════════════════════════════════════════════════
# Install dashboard dependencies
# ════════════════════════════════════════════════════════════
!pip install streamlit plotly openpyxl -q
print("✅ Dashboard dependencies installed")


# ══ CELL 20 ══════════════════════════════════════════════════
# Verify all required files exist before launching
# ALL three must show ✅ before running Cell 21
# ════════════════════════════════════════════════════════════
import os

checks = {
    "data/processed_data.csv": "Processed data (required by dashboard)",
    "data/stocks_raw.xlsx":     "Raw stock data",
    "data/news_raw.xlsx":       "News data",
    "app.py":                   "Dashboard app file",
}

all_ok = True
for path, label in checks.items():
    exists = os.path.exists(path)
    size   = os.path.getsize(path)/(1024*1024) if exists else 0
    icon   = "✅" if exists else "❌"
    print(f"  {icon}  {label:<40}  ({size:.1f} MB)")
    if not exists:
        all_ok = False

if all_ok:
    print("\n✅ All files present. Run Cell 21 to launch the dashboard.")
else:
    print("\n❌ Some files are missing. Check the notebooks above.")


# ══ CELL 21 ══════════════════════════════════════════════════
# Launch Streamlit + Cloudflare tunnel
# Wait for the public URL to appear, then share it.
# Keep this Colab tab open while presenting.
# ════════════════════════════════════════════════════════════
import subprocess, threading, time, re, urllib.request, os

# Kill any old processes
subprocess.run(["pkill", "-f", "streamlit"],   capture_output=True)
subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True)
time.sleep(2)

# Start Streamlit in a background thread
def run_streamlit():
    subprocess.run([
        "streamlit", "run", "app.py",
        "--server.port=8501",
        "--server.headless=true",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
        "--theme.base=dark",
    ])

threading.Thread(target=run_streamlit, daemon=True).start()

# Wait until Streamlit is actually ready
print("Starting Streamlit", end="", flush=True)
for _ in range(40):
    try:
        urllib.request.urlopen("http://localhost:8501/_stcore/health", timeout=2)
        print(" ✓")
        break
    except:
        print(".", end="", flush=True)
        time.sleep(1)

# Download cloudflared if not present
if not os.path.exists("cloudflared"):
    print("Downloading cloudflared...", end="", flush=True)
    subprocess.run([
        "wget", "-q",
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
        "-O", "cloudflared"
    ], check=True)
    subprocess.run(["chmod", "+x", "cloudflared"], check=True)
    print(" ✓")

# Open Cloudflare tunnel
cf = subprocess.Popen(
    ["./cloudflared", "tunnel", "--url", "http://localhost:8501"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)

print("Opening tunnel", end="", flush=True)
for line in cf.stdout:
    text = line.decode().strip()
    if "trycloudflare.com" in text:
        match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", text)
        if match:
            print(" ✓")
            print("\n" + "="*55)
            print("  ✅  MarketIQ Dashboard is LIVE!")
            print(f"  🌐  {match.group(0)}")
            print("  Share this URL with anyone — no login needed.")
            print("="*55)
            break
    print(".", end="", flush=True)
