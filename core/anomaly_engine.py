import psutil
import winreg

def check_pending_reboot():
    reboot_keys = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"
    ]
    for key_path in reboot_keys:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            winreg.CloseKey(key)
            return True
        except: pass
    return False

def check_all_disks():
    issues = []
    try:
        for p in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(p.mountpoint)
                if usage.percent > 90: issues.append({"mountpoint": p.mountpoint, "percent": usage.percent})
            except: pass
    except: pass
    return issues

def eval_cpu(long_cpu):
    if long_cpu > 85: return 15, "CPU Critical"
    if long_cpu > 60: return 5, "CPU Warning"
    return 0, None

def eval_ram(health):
    if health['ram_used_percent'] > 85: return 15, "RAM Critical"
    if health['ram_used_percent'] > 70: return 5, "RAM Warning"
    return 0, None

def eval_disk():
    issues = check_all_disks()
    score = 0
    msgs = []
    for issue in issues:
        msgs.append(f"Disk {issue['mountpoint']} Critical ({issue['percent']}%)")
        score += 10
    return score, msgs

def eval_fatigue(long_cpu):
    if long_cpu > 75: return 10, "System Fatigue (Sustained High Load)"
    return 0, None

def eval_uptime(uptime_days):
    if uptime_days > 7: return 15, "Uptime > 7 days"
    if uptime_days > 3: return 10, "Uptime > 3 days"
    if uptime_days > 1: return 2, "Uptime > 1 day"
    return 0, None

def calculate_raw_score(health, long_cpu, uptime_days, pending_reboot):
    score = 0
    breakdown = []
    recommendations = []

    c_score, c_msg = eval_cpu(long_cpu)
    if c_score: score += c_score; breakdown.append((c_msg, c_score)); recommendations.append("High CPU Load detected.")
    
    r_score, r_msg = eval_ram(health)
    if r_score: score += r_score; breakdown.append((r_msg, r_score)); recommendations.append("Free up RAM immediately.")
    
    d_score, d_msgs = eval_disk()
    if d_score:
        score += d_score
        for msg in d_msgs: breakdown.append((msg, 10))
        recommendations.append("Clear disk space on critical drives.")

    f_score, f_msg = eval_fatigue(long_cpu)
    if f_score: score += f_score; breakdown.append((f_msg, f_score))

    u_score, u_msg = eval_uptime(uptime_days)
    if u_score: score += u_score; breakdown.append((u_msg, u_score))
    
    if pending_reboot:
        score += 15
        breakdown.append(("Pending Windows Update", 15))
        recommendations.append("Restart to apply updates.")

    return {"reboot_score": score, "breakdown": breakdown, "recommendations": recommendations}