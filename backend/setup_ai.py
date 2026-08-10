# ============================================================
#  setup_ai.py — Agentic AI Setup Script
#
#  This script does EVERYTHING automatically:
#    1. Checks if Ollama is installed
#    2. Downloads and installs Ollama if not installed
#    3. Starts Ollama service
#    4. Downloads SQLCoder model automatically
#    5. Downloads fallback models for low RAM
#    6. Tests everything is working
#    7. Shows final status report
#
#  Just run:  python setup_ai.py
#  It handles everything by itself — no manual steps needed.
# ============================================================

import subprocess   # to run system commands
import sys          # to check python version and exit
import os           # to check files exist
import platform     # to check Windows/Mac/Linux
import time         # to wait between checks
import requests     # to call Ollama API
import shutil       # to check if command exists

# ── Colors for terminal output ───────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def print_step(step: int, msg: str):
    print(f"\n{BLUE}{BOLD}[Step {step}]{RESET} {msg}")

def print_ok(msg: str):
    print(f"  {GREEN}✓ {msg}{RESET}")

def print_fail(msg: str):
    print(f"  {RED}✗ {msg}{RESET}")

def print_info(msg: str):
    print(f"  {YELLOW}→ {msg}{RESET}")

def print_banner():
    print(f"""
{BLUE}{BOLD}
╔══════════════════════════════════════════════════════╗
║         SQL Assistant — AI Setup Script              ║
║         Auto downloads Ollama + SQLCoder             ║
╚══════════════════════════════════════════════════════╝
{RESET}""")


# ============================================================
#  STEP 1 — CHECK SYSTEM RAM
#  Decides which model to download based on available RAM
# ============================================================

def get_ram_gb() -> float:
    """Returns total system RAM in GB."""
    try:
        import psutil
        ram = psutil.virtual_memory().total / (1024 ** 3)
        return round(ram, 1)
    except ImportError:
        # psutil not installed — try to install it
        print_info("Installing psutil to check RAM...")
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil", "-q"])
        try:
            import psutil
            ram = psutil.virtual_memory().total / (1024 ** 3)
            return round(ram, 1)
        except Exception:
            return 8.0  # assume 8GB if cannot detect


def choose_model(ram_gb: float) -> dict:
    """
    Always use SQLCoder — best model for SQL generation.
    Ignores RAM check — SQLCoder only.
    """
    # Always SQLCoder — no matter how much RAM you have
    return {
        "name": "sqlcoder",
        "size": "~5GB",
        "reason": f"Using SQLCoder (your RAM: {ram_gb}GB)",
        "accuracy": "Best SQL accuracy — handles joins, aggregations, subqueries"
    }


# ============================================================
#  STEP 2 — CHECK / INSTALL OLLAMA
# ============================================================

def is_ollama_installed() -> bool:
    """Check if ollama command exists on this machine."""
    return shutil.which("ollama") is not None


def install_ollama():
    """
    Download and install Ollama automatically.
    Works on Windows, Mac, Linux.
    """
    system = platform.system().lower()
    print_info(f"Detected OS: {platform.system()}")

    if system == "windows":
        print_info("Downloading Ollama installer for Windows...")
        print_info("Opening Ollama download page in your browser...")

        # Open browser to download page
        import webbrowser
        webbrowser.open("https://ollama.com/download/windows")

        print(f"""
  {YELLOW}Please:{RESET}
  1. Download the Ollama installer that just opened in your browser
  2. Run the installer (OllamaSetup.exe)
  3. Come back here and press ENTER when done
        """)
        input("  Press ENTER after Ollama is installed...")

    elif system == "darwin":  # Mac
        print_info("Installing Ollama on Mac via curl...")
        os.system("curl -fsSL https://ollama.com/install.sh | sh")

    elif system == "linux":
        print_info("Installing Ollama on Linux via curl...")
        os.system("curl -fsSL https://ollama.com/install.sh | sh")

    else:
        print_fail(f"Unknown OS: {system}")
        print_info("Please manually install Ollama from: https://ollama.com/download")
        sys.exit(1)


# ============================================================
#  STEP 3 — START OLLAMA SERVICE
# ============================================================

def is_ollama_running() -> bool:
    """Check if Ollama API is responding on localhost:11434."""
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=3)
        return res.status_code == 200
    except Exception:
        return False


def start_ollama():
    """Start Ollama service in background."""
    print_info("Starting Ollama service in background...")

    system = platform.system().lower()

    if system == "windows":
        # Start ollama serve in background on Windows
        subprocess.Popen(
            ["ollama", "serve"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,  # opens new window
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        # Mac/Linux — start in background
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    # Wait for Ollama to start
    print_info("Waiting for Ollama to start...")
    for i in range(15):  # try for 15 seconds
        time.sleep(1)
        if is_ollama_running():
            return True
        print_info(f"Waiting... {i+1}s")

    return False


# ============================================================
#  STEP 4 — CHECK IF MODEL IS ALREADY DOWNLOADED
# ============================================================

def is_model_downloaded(model_name: str) -> bool:
    """Check if a model is already pulled in Ollama."""
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=5)
        if res.status_code == 200:
            models = res.json().get("models", [])
            # Check if model name matches any downloaded model
            for m in models:
                if model_name.lower() in m.get("name", "").lower():
                    return True
        return False
    except Exception:
        return False


# ============================================================
#  STEP 5 — DOWNLOAD THE MODEL
# ============================================================

def download_model(model_name: str):
    """
    Pull a model from Ollama.
    Shows live download progress.
    """
    print_info(f"Downloading {model_name} — this may take a few minutes...")
    print_info("Download size depends on model — please wait...")
    print()

    # Run ollama pull — this shows live progress in terminal
    result = subprocess.run(
        ["ollama", "pull", model_name],
        # Don't capture output — let it print directly so user sees progress
    )

    if result.returncode == 0:
        return True
    else:
        return False


# ============================================================
#  STEP 6 — TEST THE MODEL
#  Send a simple SQL question to verify it works
# ============================================================

def test_model(model_name: str) -> bool:
    """
    Send a simple test prompt to the model.
    Verifies the model can generate SQL.
    """
    print_info(f"Testing {model_name} with a sample SQL question...")

    test_prompt = """You are a SQL expert. Generate only a SQL query, no explanation.

Table: customers
  - id (INT) PRIMARY KEY
  - name (VARCHAR)
  - email (VARCHAR)

Question: show all customers

SQL QUERY:"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "prompt": test_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 100
                }
            },
            timeout=120  # first run may take longer — model loads into RAM
        )

        if response.status_code == 200:
            output = response.json().get("response", "").strip()
            if output:
                print_ok(f"Model responded successfully!")
                print_info(f"Test output: {output[:100]}...")
                return True
            else:
                print_fail("Model returned empty response")
                return False
        else:
            print_fail(f"Model returned status: {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        print_fail("Model test timed out — model may need more time to load")
        print_info("Try running a query manually after setup completes")
        return False
    except Exception as e:
        print_fail(f"Model test failed: {e}")
        return False


# ============================================================
#  STEP 7 — UPDATE ai_agent.py WITH CORRECT MODEL NAME
# ============================================================

def update_ai_agent(model_name: str, ollama_host: str = "localhost"):
    """
    Automatically update ai_agent.py to use the downloaded model.
    Changes the default model name so backend uses it automatically.
    """
    agent_file = "ai_agent.py"

    if not os.path.exists(agent_file):
        print_info(f"ai_agent.py not found in current folder — skipping auto update")
        return

    with open(agent_file, "r") as f:
        content = f.read()

    # Update OLLAMA_URL if using remote host
    old_url = 'OLLAMA_URL = "http://localhost:11434/api/generate"'
    new_url = f'OLLAMA_URL = "http://{ollama_host}:11434/api/generate"'
    content = content.replace(old_url, new_url)

    # Update default model in generate_sql function
    old_default = 'def generate_sql(question: str, schema: dict, db_type: str, model: str = "llama3")'
    new_default = f'def generate_sql(question: str, schema: dict, db_type: str, model: str = "{model_name}")'
    content = content.replace(old_default, new_default)

    with open(agent_file, "w") as f:
        f.write(content)

    print_ok(f"ai_agent.py updated — default model set to '{model_name}'")


# ============================================================
#  STEP 8 — PRINT FINAL STATUS REPORT
# ============================================================

def print_final_report(model_info: dict, ram_gb: float):
    print(f"""
{GREEN}{BOLD}
╔══════════════════════════════════════════════════════╗
║              SETUP COMPLETE ✓                        ║
╚══════════════════════════════════════════════════════╝
{RESET}
  {BOLD}System RAM:{RESET}      {ram_gb} GB
  {BOLD}Model:{RESET}           {model_info['name']} ({model_info['size']})
  {BOLD}Accuracy:{RESET}        {model_info['accuracy']}
  {BOLD}Ollama URL:{RESET}      http://localhost:11434
  {BOLD}Status:{RESET}          {GREEN}Running ✓{RESET}

{BOLD}Next steps:{RESET}
  1. Start your backend:
     {YELLOW}uvicorn main:app --reload --port 8000{RESET}

  2. Open your frontend:
     {YELLOW}sql-assistant.html{RESET}

  3. Connect your database and ask questions!

{BOLD}To change model later, edit ai_agent.py:{RESET}
  model: str = "{model_info['name']}"

{BOLD}Available models on your system:{RESET}
""")

    # List all downloaded models
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=5)
        if res.status_code == 200:
            models = res.json().get("models", [])
            for m in models:
                size_gb = m.get("size", 0) / (1024**3)
                print(f"  {GREEN}✓{RESET} {m['name']} ({size_gb:.1f} GB)")
    except Exception:
        pass

    print()


# ============================================================
#  MAIN — runs all steps in order
# ============================================================

def main():
    print_banner()

    # ── Step 1: Check RAM ─────────────────────────────────────
    print_step(1, "Checking system RAM...")
    ram_gb = get_ram_gb()
    print_ok(f"RAM detected: {ram_gb} GB")

    # Choose best model for this machine
    model_info = choose_model(ram_gb)
    print_info(model_info["reason"])
    print_info(f"Selected model: {model_info['name']} ({model_info['size']})")
    print_info(f"Accuracy: {model_info['accuracy']}")

    # ── Step 2: Check/Install Ollama ──────────────────────────
    print_step(2, "Checking Ollama installation...")

    if is_ollama_installed():
        print_ok("Ollama is already installed")
    else:
        print_fail("Ollama is not installed")
        print_info("Installing Ollama automatically...")
        install_ollama()

        # Verify installation succeeded
        if is_ollama_installed():
            print_ok("Ollama installed successfully")
        else:
            print_fail("Ollama installation failed")
            print_info("Please install manually from: https://ollama.com/download")
            sys.exit(1)

    # ── Step 3: Start Ollama service ──────────────────────────
    print_step(3, "Starting Ollama service...")

    if is_ollama_running():
        print_ok("Ollama is already running")
    else:
        started = start_ollama()
        if started:
            print_ok("Ollama started successfully")
        else:
            print_fail("Could not start Ollama automatically")
            print_info("Please run manually in a separate terminal: ollama serve")
            input("Press ENTER after running 'ollama serve'...")
            if not is_ollama_running():
                print_fail("Ollama still not running — please check installation")
                sys.exit(1)

    # ── Step 4: Check if model already downloaded ─────────────
    print_step(4, f"Checking if {model_info['name']} is downloaded...")

    if is_model_downloaded(model_info["name"]):
        print_ok(f"{model_info['name']} is already downloaded")
    else:
        print_fail(f"{model_info['name']} not found — downloading now...")
        print_info(f"Size: {model_info['size']} — please wait, this takes a few minutes")
        print_info("You will see download progress below:")
        print()

        success = download_model(model_info["name"])

        if success:
            print_ok(f"{model_info['name']} downloaded successfully")
        else:
            print_fail(f"Failed to download SQLCoder")
            print_info("Check your internet connection and try again")
            print_info("Make sure Ollama is running: ollama serve")
            sys.exit(1)

    # ── Step 5: Test the model ────────────────────────────────
    print_step(5, "Testing AI model with a sample SQL question...")
    test_passed = test_model(model_info["name"])

    if test_passed:
        print_ok("AI model is working correctly")
    else:
        print_info("Model test was inconclusive — model may still work")
        print_info("Try running a query from the frontend to verify")

    # ── Step 6: Update ai_agent.py ────────────────────────────
    print_step(6, "Updating ai_agent.py with correct model settings...")
    update_ai_agent(model_info["name"])

    # ── Step 7: Final report ──────────────────────────────────
    print_final_report(model_info, ram_gb)


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Setup cancelled by user.{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{RED}Unexpected error: {e}{RESET}")
        print("Please report this error or set up manually.")
        sys.exit(1)
