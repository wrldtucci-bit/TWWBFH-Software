# TWWBFH-Software
TucciWrlds-Wifi-Brutal-Force-Hacker


Here's a complete README covering both versions:

---

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║        TucciCyberNation WiFi Security Suite                      ║
║        brute.py — Full Edition (v2.3) & Portable Edition         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

# TucciCyberNation WiFi Security Suite

An automated WiFi security auditing tool that tests whether your wireless network's WPA/WPA2 password can survive a dictionary attack. It automates the full audit pipeline: environment setup, monitor mode, network discovery, WPA handshake capture, and dictionary-based password recovery — all from a single Python file.

**Created by TucciCyberNation**

---

## ⚠️ Disclaimer — Read First

> **FOR EDUCATIONAL PURPOSES AND PERSONAL USE ONLY.**
>
> Use this tool **ONLY** on:
> - Your **OWN** WiFi network
> - Networks you have **explicit written permission** to test
> - Recovering a password from **your own** router when you've lost it
>
> Using this tool on networks you do not own or are not authorized to test is **ILLEGAL** in most jurisdictions (e.g., the Computer Fraud and Abuse Act in the US, and similar laws worldwide). The author, **TucciCyberNation**, is not responsible for any misuse of this software.
>
> Both versions display a mandatory disclaimer that you must accept before the tool runs.

---

## 📦 The Two Versions

| | **Full Edition (v2.3)** | **Portable Edition** |
|---|---|---|
| Interface | GUI (tkinter) **and** CLI, chosen at startup | CLI only |
| File | `brute.py` (single file) | `brute.py` (single file, smaller) |
| Best for | Desktop Kali/Ubuntu with a display | Headless boxes, SSH sessions, quick audits |
| Features | Step buttons, FULL AUTO, live log console, network listbox | Fully guided step-by-step terminal flow |
| Dependencies | Python 3 + tkinter | Python 3 only |

Both versions share the same engine logic: monitor mode → scan → handshake → crack.

---

## 🖥️ Requirements

- **Real Linux machine** — Kali Linux (recommended), Debian, or Ubuntu
  - ❌ Does **NOT** run in browser/WASM Python (Pyodide, online IDEs) — it checks and refuses these environments
  - ❌ Does NOT run natively on Windows
- **Python 3.x**
- **Root privileges** (`sudo`)
- **Wireless adapter** that supports **monitor mode** and **packet injection**
  - Recommended USB adapters: Alfa AWUS036ACH, AWUS036ACNH, Panda PAU09
  - Many laptop built-in cards cannot inject packets
- Internet connection (for the auto-installer and wordlist download)
- Full Edition only: `python3-tk` if your Python lacks tkinter (preinstalled on most desktop distros)

---

## ⚙️ Installation

The tool **installs its own environment automatically**, including pip upgrades, required Python packages, and the aircrack-ng suite via `apt` if missing. But you still need to get the file onto a Linux machine:

```bash
# 1. Get the file onto your Linux machine (Kali/Ubuntu)
#    e.g., via git, wget, or USB

# 2. (Kali usually has this already; other distros may need it)
sudo apt install aircrack-ng python3-tk

# 3. Run it
sudo python3 brute.py
```

That's it — everything else is automated on first launch.

---

## 🚀 Usage

### Choosing a Mode (Full Edition)

Launching without arguments shows a mode selector:

```
Select mode [1/2, default 1]:
  1) CLI mode  (terminal)
  2) GUI mode  (graphical window)
```

You can also skip the prompt with flags:

```bash
sudo python3 brute.py --gui   # force GUI
sudo python3 brute.py --cli   # force CLI
```

If tkinter is missing or there's no display (SSH/headless), the Full Edition automatically falls back to CLI — same behavior as the Portable Edition.

---

### Step-by-Step Workflow (both versions)

**STEP 0 — Environment setup (automatic)**
Upgrades pip, installs required Python packages, verifies root privileges, and auto-installs the aircrack-ng suite if any tool is missing.

**STEP 1 — Monitor mode (automatic)**
Detects your wireless interfaces, runs `airmon-ng check kill` (stops interfering services), and activates monitor mode (`wlan0mon` or similar). If multiple adapters are found, you pick one.

**STEP 2 — Network scan & target selection**
Runs a 15-second `airodump-ng` scan, parses the results, and lists discovered networks with ESSID, BSSID, channel, and signal power. You choose the target — **pick your own network**.

**STEP 3 — Handshake capture (automatic)**
Locks onto the target's channel/BSSID, waits up to 60 seconds for a WPA handshake, and automatically fires a deauth burst against the AP if none appears (forcing connected clients to reconnect, which generates the handshake). The handshake — the encrypted material containing the password hash — is saved to `/tmp/handshake_<ESSID>-01.cap`.

**STEP 4 — Dictionary attack (automatic matching)**
The captured handshake is fed to `aircrack-ng` along with a wordlist. If no wordlist is found, the tool automatically downloads `rockyou.txt` (14M+ common passwords). It then tries every candidate password against the captured hash. If the real password is in the wordlist, it's found and displayed.

**Cleanup (automatic)**
Monitor mode is stopped and NetworkManager is restarted so your normal WiFi works again — even if the run errors out or you press Ctrl+C.

---

### Full Edition — GUI Controls

| Button | Action |
|---|---|
| **1. Setup Env** | Runs environment checks, lists wireless interfaces |
| **2. Monitor Mode** | Activates monitor mode on the selected interface |
| **3. Scan** | Scans and populates the network list |
| **4. Capture HS** | Captures the handshake for the selected network |
| **5. Crack** | Runs the dictionary attack with your wordlist |
| **FULL AUTO** | Runs the entire pipeline in one click (auto-targets the first AP) |
| **Stop** | Gracefully interrupts the current operation |
| **Cleanup** | Restores managed mode and NetworkManager |

Plus: configurable fields for interface, wordlist path, scan duration, and handshake timeout; a live scrolling log console; and a status bar.

### Portable Edition — CLI Prompts

The portable version guides you with terminal prompts at each step: agree to the disclaimer → confirm interface → pick target from the numbered list → provide wordlist path → results.

---

## 📁 Files Created

| Path | Contents |
|---|---|
| `/tmp/scan_<timestamp>-01.csv` | Network scan results |
| `/tmp/handshake_<ESSID>-01.cap` | Captured WPA handshake |
| `/tmp/rockyou.txt` | Downloaded wordlist (if auto-downloaded) |

---

## 🔍 Troubleshooting

| Problem | Solution |
|---|---|
| `emscripten does not support processes` / browser IDE | You're running in a web Python sandbox. Copy the file to a real Linux machine. |
| `Must run as root` | Run with `sudo python3 brute.py` |
| No wireless interface detected | Plug in a monitor-mode USB adapter (see Requirements) |
| No handshake captured | More active clients help; wait longer, or move closer to the AP. Some modern routers with WPS disabled and no clients won't produce one. |
| Password not found | Try a bigger wordlist, or convert the handshake to hashcat format 22000 for GPU cracking. A strong random password **should** resist — that means your network is secure. |
| WiFi broken after run | The cleanup step restarts NetworkManager; a reboot also fully restores everything. |
| GUI won't open over SSH | No display available — use `sudo python3 brute.py --cli` |

---

## 🛡️ Interpreting Your Results

- **Password found** → Your WiFi password is weak (it exists in common password lists). Change it to a long, random passphrase (16+ characters).
- **Password not found** → Good sign, but not proof of security. Try a larger/custom wordlist derived from your personal info, or run a GPU-based crack for a stronger test.

---

## 👤 About the Creator

**TucciCyberNation** builds offensive-security tooling with an educational mission: helping people understand and strengthen their own defenses by showing exactly how attacks work. This suite is released for learning, self-auditing, and recovering passwords from your own equipment.

> *"Test your own walls before someone else does."*

---

## 📜 Legal

This software is provided for **educational purposes only**. Unauthorized access to computer systems and wireless networks is a crime. By using this software you agree to use it exclusively on networks you own or are explicitly authorized to test. TucciCyberNation accepts no liability for misuse.

---

*© TucciCyberNation — WiFi Security Suite v2.3 (Full) & Portable Edition*
```

Want me to also add a `LICENSE` file text, a usage demo GIF section placeholder, or a quick-install one-liner (`wget` + run) section for the README?
