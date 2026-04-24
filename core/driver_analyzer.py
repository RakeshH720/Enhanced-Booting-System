import winreg
import time
import threading
import heapq

DRIVER_REGISTRY_PATH = r"SYSTEM\CurrentControlSet\Services"

# Severity Constants
SEV_MISSING = 4.5
SEV_DISABLED = 1.0
SEV_NORMAL = 0.0

# Whitelist for Windows Core Drivers that intentionally lack ImagePaths
CORE_GHOST_DRIVERS = {
    "beep", "cimfs", "exfat", "fastfat", "fs_rec", 
    "msfs", "npfs", "null", "ntfs", "ndis"
}

_cache_lock = threading.Lock()
_cache = {"data": None, "last_scan": 0}

def get_driver_status_meaning(start_value):
    meanings = {0: "Boot Start", 1: "System Start", 2: "Auto Start", 3: "Manual", 4: "Disabled"}
    return meanings.get(start_value, "Unknown")

def analyze_drivers(force_refresh=False):
    global _cache
    now = time.time()
    
    # 1. First Pass (Fast Read)
    with _cache_lock:
        if not force_refresh and _cache["data"] and (now - _cache["last_scan"] < 300):
            return _cache["data"]

    drivers = []
    summary = {
        "disabled": 0, "system": 0, "missing_path": 0, 
        "total": 0, "total_severity": 0.0, "severity_ratio": 0.0,
        "flagged": 0, "top_issue": "NONE"
    }

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DRIVER_REGISTRY_PATH) as reg_key:
            total = winreg.QueryInfoKey(reg_key)[0]
            summary["total"] = total

            for i in range(total):
                try:
                    driver_name = winreg.EnumKey(reg_key, i)
                    with winreg.OpenKey(reg_key, driver_name) as driver_key:
                        try:
                            start_val = winreg.QueryValueEx(driver_key, "Start")[0]
                            status_meaning = get_driver_status_meaning(start_val)
                            
                            try: image_path = winreg.QueryValueEx(driver_key, "ImagePath")[0]
                            except: image_path = "N/A"

                            try: display_name = winreg.QueryValueEx(driver_key, "DisplayName")[0]
                            except: display_name = driver_name

                            driver_info = {
                                "display_name": display_name,
                                "start_type": status_meaning,
                                "flag": "UNCLASSIFIED",
                                "severity": SEV_NORMAL
                            }

                            if image_path == "N/A":
                                if driver_name.lower() in CORE_GHOST_DRIVERS:
                                    driver_info["flag"] = "SYSTEM"
                                    summary["system"] += 1
                                else:
                                    driver_info["flag"] = "MISSING PATH"
                                    driver_info["severity"] = SEV_MISSING
                                    summary["missing_path"] += 1
                                    summary["total_severity"] += SEV_MISSING
                            elif start_val == 4:
                                driver_info["flag"] = "DISABLED"
                                driver_info["severity"] = SEV_DISABLED
                                summary["disabled"] += 1
                                summary["total_severity"] += SEV_DISABLED
                            elif start_val in [0, 1]:
                                driver_info["flag"] = "SYSTEM"
                                summary["system"] += 1
                            elif start_val in [2, 3]:
                                driver_info["flag"] = "NORMAL"

                            drivers.append(driver_info)
                        except FileNotFoundError: pass
                except OSError: pass
    except Exception:
        # Production safe: fail silently, do not print to stdout in a daemon
        pass

    # 2. Advanced Metrics
    summary["severity_ratio"] = round(summary["total_severity"] / max(summary["total"], 1), 4)

    # 3. Payload Optimization
    flagged_drivers = [d for d in drivers if d["severity"] > 0]
    top_drivers = heapq.nlargest(50, flagged_drivers, key=lambda x: x["severity"])

    # 4. Final UX Polish
    summary["flagged"] = len(flagged_drivers)
    summary["top_issue"] = top_drivers[0]["flag"] if top_drivers else "NONE"

    result = {"drivers": top_drivers, "summary": summary}
    
    # 5. Double-Check Lock Write
    with _cache_lock:
        if force_refresh or (now - _cache["last_scan"] >= 300):
            _cache["data"] = result
            _cache["last_scan"] = time.time()
        
    return result