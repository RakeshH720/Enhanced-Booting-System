import psutil
import winreg
from collections import deque

# ==========================================
# 🧠 DYNAMIC BASELINE ENGINE
# ==========================================
class DynamicAnomalyDetector:
    def __init__(self, window_size=20):
        self.cpu_history = deque(maxlen=window_size)
        self.mem_history = deque(maxlen=window_size)

    def update_metrics(self, cpu, memory):
        self.cpu_history.append(cpu)
        self.mem_history.append(memory)

    def get_baseline(self):
        if len(self.cpu_history) == 0:
            return 0, 0
        avg_cpu = sum(self.cpu_history) / len(self.cpu_history)
        avg_mem = sum(self.mem_history) / len(self.mem_history)
        return avg_cpu, avg_mem

    def detect_anomaly(self, cpu, memory):
        # Startup Guard: Wait for minimum data
        if len(self.cpu_history) < 5:
            return 0, [("Collecting baseline data...", 0)]

        avg_cpu, avg_mem = self.get_baseline()
        deviation_threshold = 1.5
        
        score = 0
        breakdown = []

        # CPU Deviation Check
        if cpu > (avg_cpu * deviation_threshold) and cpu > 40:
            pts = 10
            score += pts
            breakdown.append((f"CPU Spike: {round(cpu)}% vs baseline {avg_cpu:.1f}%", pts))
        elif cpu > 85: # Absolute Fallback
            pts = 15
            score += pts
            breakdown.append(("CPU Critical: Sustained > 85%", pts))

        # RAM Deviation Check
        if memory > (avg_mem * deviation_threshold) and memory > 40:
            pts = 10
            score += pts
            breakdown.append((f"RAM Spike: {round(memory)}% vs baseline {avg_mem:.1f}%", pts))
        elif memory > 85: # Absolute Fallback
            pts = 15
            score += pts
            breakdown.append(("RAM Critical: Sustained > 85%", pts))

        return score, breakdown

# Initialize global instance for the session
detector = DynamicAnomalyDetector(window_size=20)


# ==========================================
# 🔧 STATIC SYSTEM CHECKS
# ==========================================
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

# ==========================================
# ⚡ MAIN EVALUATION LOOP
# ==========================================
def calculate_raw_score(health, long_cpu, uptime_days, pending_reboot):
    score = 0
    breakdown = []
    recommendations = []

    current_cpu = health['cpu_percent']
    current_ram = health['ram_used_percent']

    # 1. Evaluate current state AGAINST the clean baseline FIRST
    dyn_score, dyn_breakdown = detector.detect_anomaly(current_cpu, current_ram)

    # 2. THEN update the baseline (keeps spikes from normalizing themselves)
    detector.update_metrics(current_cpu, current_ram)

    if dyn_score > 0:
        score += dyn_score
        for msg, pts in dyn_breakdown:
            if pts > 0: 
                breakdown.append((msg, pts))
        
        if any("Spike" in msg for msg, pts in dyn_breakdown):
            recommendations.append("Abnormal resource deviation detected.")

    # 3. Static infrastructure checks
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

    # 4. Determine Severity Status
    severity = "NORMAL"
    if score >= 30:
        severity = "CRITICAL"
    elif score >= 15:
        severity = "WARNING"

    return {
        "reboot_score": score,
        "severity": severity,
        "breakdown": breakdown,
        "recommendations": recommendations
    }