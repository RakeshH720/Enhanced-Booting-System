import psutil
import time
import winreg
import os

# =========================
# CONFIG
# =========================
THRESHOLDS = {
    "cpu_critical": 85,
    "cpu_warning": 60,
    "ram_critical": 85,
    "ram_warning": 60,
    "disk_critical": 90,
    "battery_low": 20,
}

REBOOT_CRITICAL = 60
REBOOT_SUGGESTED = 30

# =========================
# HELPERS
# =========================
def check_pending_reboot():
    reboot_keys = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
    ]

    for key_path in reboot_keys:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[Reboot Check Error] {e}")

    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager"
        )
        winreg.QueryValueEx(key, "PendingFileRenameOperations")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[Reboot Check Error] {e}")

    return False

def get_uptime_days():
    return (time.time() - psutil.boot_time()) / 86400

def count_bad_processes():
    bad_procs = []
    bad_statuses = {
        psutil.STATUS_ZOMBIE,
        psutil.STATUS_STOPPED,
        psutil.STATUS_DEAD,
    }
    for proc in psutil.process_iter(['name', 'status']):
        try:
            if proc.info['status'] in bad_statuses:
                bad_procs.append(proc.info['name'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            print(f"[Process Check Error] {e}")
    return bad_procs

def check_all_disks():
    """Check all mounted partitions, not just root."""
    disk_issues = []
    try:
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                if usage.percent > THRESHOLDS["disk_critical"]:
                    disk_issues.append({
                        "mountpoint": partition.mountpoint,
                        "percent": usage.percent
                    })
            except PermissionError:
                pass
            except Exception as e:
                print(f"[Disk Check Error] {partition.mountpoint}: {e}")
    except Exception as e:
        print(f"[Disk Partitions Error] {e}")
    return disk_issues

# =========================
# MAIN ENGINE
# =========================
def detect_anomalies():
    anomalies = {
        "critical": [],
        "warning": []
    }
    recommendations = []
    reboot_score = 0
    score_breakdown = []

    # --- CPU ---
    try:
        cpu = psutil.cpu_percent(interval=None)
        if cpu > THRESHOLDS["cpu_critical"]:
            anomalies["critical"].append(f"CPU usage at {cpu}%")
            recommendations.append("Kill heavy processes immediately")
            reboot_score += 15
            score_breakdown.append(("CPU Critical", 15))
        elif cpu > THRESHOLDS["cpu_warning"]:
            anomalies["warning"].append(f"CPU usage at {cpu}%")
            recommendations.append("Monitor CPU usage closely")
            reboot_score += 5
            score_breakdown.append(("CPU Warning", 5))
    except Exception as e:
        print(f"[CPU Check Error] {e}")
        cpu = 0

    # --- RAM ---
    try:
        ram = psutil.virtual_memory()
        if ram.percent > THRESHOLDS["ram_critical"]:
            anomalies["critical"].append(f"RAM usage at {ram.percent}%")
            recommendations.append("Close unused applications")
            reboot_score += 15
            score_breakdown.append(("RAM Critical", 15))
        elif ram.percent > THRESHOLDS["ram_warning"]:
            anomalies["warning"].append(f"RAM usage at {ram.percent}%")
            recommendations.append("Consider closing background apps")
            reboot_score += 5
            score_breakdown.append(("RAM Warning", 5))
    except Exception as e:
        print(f"[RAM Check Error] {e}")
        ram = None

    # --- Disk (all partitions) ---
    try:
        disk_issues = check_all_disks()
        for issue in disk_issues:
            anomalies["critical"].append(
                f"Disk {issue['mountpoint']} at {issue['percent']}%"
            )
            recommendations.append(f"Free up space on {issue['mountpoint']}")
            reboot_score += 10
            score_breakdown.append((f"Disk Critical {issue['mountpoint']}", 10))
    except Exception as e:
        print(f"[Disk Check Error] {e}")

    # --- Battery ---
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            if not battery.power_plugged and battery.percent < THRESHOLDS["battery_low"]:
                anomalies["warning"].append(f"Battery at {battery.percent}%")
                recommendations.append("Plug in charger soon")
                reboot_score += 5
                score_breakdown.append(("Battery Low", 5))
    except Exception as e:
        print(f"[Battery Check Error] {e}")
        battery = None

    # --- Uptime ---
    try:
        uptime_days = get_uptime_days()
        uptime_hours = uptime_days * 24
        if uptime_days > 7:
            anomalies["critical"].append(f"System running for {int(uptime_days)} days")
            recommendations.append("Long uptime — reboot recommended")
            reboot_score += 35
            score_breakdown.append(("Uptime > 7 days", 35))
        elif uptime_days > 3:
            anomalies["warning"].append(f"System running for {int(uptime_hours)} hours")
            recommendations.append("Consider restarting soon")
            reboot_score += 20
            score_breakdown.append(("Uptime > 3 days", 20))
        elif uptime_days > 1:
            anomalies["warning"].append(f"System running for {int(uptime_hours)} hours")
            reboot_score += 5
            score_breakdown.append(("Uptime > 1 day", 5))
    except Exception as e:
        print(f"[Uptime Check Error] {e}")
        uptime_days = 0
        uptime_hours = 0

    # --- Pending reboot ---
    try:
        pending = check_pending_reboot()
        if pending:
            anomalies["critical"].append("Windows update pending reboot")
            recommendations.append("Save work and restart to apply updates")
            reboot_score += 35
            score_breakdown.append(("Pending Windows Update", 35))
    except Exception as e:
        print(f"[Pending Reboot Error] {e}")
        pending = False

    # --- Bad processes ---
    try:
        bad_procs = count_bad_processes()
        if bad_procs:
            anomalies["warning"].append(
                f"Unresponsive processes: {', '.join(bad_procs[:3])}"
            )
            recommendations.append("Restart affected applications")
            score = min(len(bad_procs) * 5, 20)
            reboot_score += score
            score_breakdown.append(("Bad Processes", score))
    except Exception as e:
        print(f"[Bad Process Error] {e}")
        bad_procs = []

    # --- Finalize ---
    recommendations = list(dict.fromkeys(recommendations))
    reboot_score = min(reboot_score, 100)

    if reboot_score >= REBOOT_CRITICAL:
        reboot_status = "REBOOT RECOMMENDED"
    elif reboot_score >= REBOOT_SUGGESTED:
        reboot_status = "REBOOT SUGGESTED"
    else:
        reboot_status = "STABLE"

    return {
        "anomalies": anomalies,
        "recommendations": recommendations,
        "reboot_score": reboot_score,
        "reboot_status": reboot_status,
        "score_breakdown": score_breakdown,
        "cpu": cpu,
        "ram": ram.percent if ram else 0,
        "disk_issues": disk_issues if 'disk_issues' in locals() else [],
        "uptime_days": round(uptime_days, 1),
        "uptime_hours": round(uptime_hours, 1),
        "bad_processes": bad_procs,
        "pending_reboot": pending
    }