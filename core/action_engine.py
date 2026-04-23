import psutil
import time
import os
import json
from core.learning_engine import get_learned_ignore_list

# =========================
# CONFIG & WHITELISTS
# =========================
SYSTEM_PROCESSES = {
    'system idle process', 'system', 'registry', 'smss.exe', 'csrss.exe',
    'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe', 'dwm.exe',
    'explorer.exe', 'taskhostw.exe', 'sihost.exe', 'fontdrvhost.exe',
    'wmiprvse.exe', 'audiodg.exe', 'wudfhost.exe', 'runtimebroker.exe',
    'searchhost.exe', 'searchindexer.exe', 'spoolsv.exe', 'msmpseng.exe',
    'ntoskrnl.exe', 'conhost.exe', 'dllhost.exe', 'winlogon.exe'
}

SAFE_USER_PROCESSES = {
    "code.exe", "chrome.exe", "firefox.exe", "msedge.exe", 
    "devenv.exe", "pycharm.exe", "obs64.exe"
}

# Dynamic Memory Injection
LEARNED_IGNORE_PROCESSES = get_learned_ignore_list()

SYS_ROOT = os.environ.get('SystemRoot', 'c:\\windows').lower()
SYSTEM_DIRS = [
    os.path.join(SYS_ROOT, 'system32'),
    os.path.join(SYS_ROOT, 'syswow64')
]

MIN_RAM_PERCENT = 10.0
MIN_CPU_PERCENT = 25.0
COOLDOWN_SECONDS = 60
ACTION_LOG_FILE = "data/action_log.jsonl"

LAST_CPU_ACTION = 0
LAST_RAM_ACTION = 0
CURRENT_PID = os.getpid()

# =========================
# INTELLIGENCE & UTILITIES
# =========================
def log_action(action_type, details, impact, success):
    try:
        os.makedirs(os.path.dirname(ACTION_LOG_FILE), exist_ok=True)
        entry = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "type": action_type,
            "actions_taken": details,
            "impact": impact,
            "batch_success": success
        }
        with open(ACTION_LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        pass

def can_take_action(action_type):
    global LAST_CPU_ACTION, LAST_RAM_ACTION
    now = time.time()
    
    if action_type == "CPU" and (now - LAST_CPU_ACTION >= COOLDOWN_SECONDS):
        LAST_CPU_ACTION = now
        return True
    elif action_type == "RAM" and (now - LAST_RAM_ACTION >= COOLDOWN_SECONDS):
        LAST_RAM_ACTION = now
        return True
    return False

def get_current_metrics():
    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "ram": psutil.virtual_memory().percent
    }

def is_cpu_really_high(threshold):
    """Debounces transient CPU spikes."""
    c1 = psutil.cpu_percent(interval=0.2)
    c2 = psutil.cpu_percent(interval=0.2)
    return (c1 + c2) / 2 >= threshold

def is_recent_or_child(proc):
    try:
        if time.time() - proc.create_time() < 10:
            return True
        if proc.ppid() == CURRENT_PID:
            return True
    except Exception:
        return True
    return False

def is_safe_process(proc):
    try:
        if proc.pid == CURRENT_PID or is_recent_or_child(proc):
            return True

        name = proc.name().lower()
        
        # Static + Dynamic Whitelists
        if name in SYSTEM_PROCESSES or name in SAFE_USER_PROCESSES:
            return True
        if name in LEARNED_IGNORE_PROCESSES:
            return True

        try:
            exe = proc.exe().lower() if proc.exe() else ""
            if any(exe.startswith(d) for d in SYSTEM_DIRS):
                return True
        except (psutil.AccessDenied, psutil.ZombieProcess):
            return True
    except Exception:
        return True
    return False

# =========================
# CORE ACTIONS
# =========================
def terminate_process(pid):
    try:
        proc = psutil.Process(pid)
        if is_safe_process(proc):
            return {"status": "blocked"}
            
        name = proc.name()
        proc.terminate()
        proc.wait(timeout=3)
        return {"status": "success", "process": name, "pid": pid}
    except psutil.TimeoutExpired:
        proc.kill()
        return {"status": "success", "process": name, "pid": pid}
    except Exception as e:
        return {"status": "error"}

def auto_clear_cpu(threshold_percent=80):
    metrics_before = get_current_metrics()
    
    if metrics_before["cpu"] < threshold_percent:
        return {"status": "skipped", "reason": "threshold_not_met"}
        
    if not is_cpu_really_high(threshold_percent):
        return {"status": "skipped", "reason": "transient_spike"}

    if not can_take_action("CPU"):
        return {"status": "skipped", "reason": "cooldown"}

    candidates = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if not is_safe_process(proc):
                proc.cpu_percent(interval=None) 
                candidates.append(proc)
        except Exception:
            pass

    time.sleep(0.1) 
    
    proc_stats = []
    for proc in candidates:
        try:
            cpu_usage = proc.cpu_percent(interval=None)
            if cpu_usage > MIN_CPU_PERCENT:
                proc_stats.append({'pid': proc.pid, 'name': proc.name(), 'cpu': cpu_usage})
        except Exception:
            pass

    proc_stats = sorted(proc_stats, key=lambda x: x['cpu'], reverse=True)

    actions_taken = []
    total_cpu_freed = 0.0
    baseline_cpu = metrics_before["cpu"]
    failures = 0
    
    for p in proc_stats[:3]:
        res = terminate_process(p['pid'])
        
        if res['status'] != 'success':
            failures += 1
            if failures >= 2: break
            continue
            
        time.sleep(1.5)
        current_cpu = get_current_metrics()["cpu"]
        freed = baseline_cpu - current_cpu
        
        res['freed'] = round(freed, 2)
        res['success'] = freed > 5.0
        
        actions_taken.append(res)
        total_cpu_freed += max(0.0, freed)
        baseline_cpu = current_cpu 
        
        if current_cpu < threshold_percent or res['success']:
            break 

    if actions_taken:
        metrics_after = get_current_metrics()
        impact = {"total_freed": round(total_cpu_freed, 2), "before": metrics_before, "after": metrics_after}
        batch_success = total_cpu_freed > 5.0 or metrics_after["cpu"] < threshold_percent
        log_action("CPU_CLEAR", actions_taken, impact, batch_success)
        return {"status": "executed", "actions": actions_taken, "impact": impact, "success": batch_success}

    return {"status": "skipped", "reason": "no_targets_found"}

def auto_clear_memory(threshold_percent=85):
    metrics_before = get_current_metrics()
    
    if metrics_before["ram"] < threshold_percent:
        return {"status": "skipped", "reason": "threshold_not_met"}

    if not can_take_action("RAM"):
        return {"status": "skipped", "reason": "cooldown"}

    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
        try:
            if proc.info['memory_percent'] > MIN_RAM_PERCENT and not is_safe_process(proc):
                procs.append(proc.info)
        except Exception:
            pass

    procs = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)
    
    actions_taken = []
    total_ram_freed = 0.0
    baseline_ram = metrics_before["ram"]
    failures = 0
    
    for p in procs[:3]:
        res = terminate_process(p['pid'])
        
        if res['status'] != 'success':
            failures += 1
            if failures >= 2: break
            continue
            
        time.sleep(1.5)
        current_ram = get_current_metrics()["ram"]
        freed = baseline_ram - current_ram
        
        res['freed'] = round(freed, 2)
        res['success'] = freed > 2.0 
        
        actions_taken.append(res)
        total_ram_freed += max(0.0, freed)
        baseline_ram = current_ram
        
        if current_ram < threshold_percent or res['success']:
            break

    if actions_taken:
        metrics_after = get_current_metrics()
        impact = {"total_freed": round(total_ram_freed, 2), "before": metrics_before, "after": metrics_after}
        batch_success = total_ram_freed > 2.0 or metrics_after["ram"] < threshold_percent
        log_action("RAM_CLEAR", actions_taken, impact, batch_success)
        return {"status": "executed", "actions": actions_taken, "impact": impact, "success": batch_success}
        
    return {"status": "skipped", "reason": "no_targets_found"}

def run_autopilot(current_health_score=None):
    current_metrics = get_current_metrics()
    
    if current_health_score is not None and current_health_score >= 75:
        if current_metrics["cpu"] < 80 and current_metrics["ram"] < 85:
            return {"status": "stable", "message": "System verified stable."}

    cpu_result = auto_clear_cpu()
    if cpu_result.get('status') == "executed":
        return {"type": "cpu_clear", "data": cpu_result}

    ram_result = auto_clear_memory()
    if ram_result.get('status') == "executed":
        return {"type": "ram_clear", "data": ram_result}
        
    if cpu_result.get('status') == 'skipped' and cpu_result.get('reason') != 'threshold_not_met':
        return {"status": "skipped", "message": f"CPU Action Skipped: {cpu_result['reason']}"}
    if ram_result.get('status') == 'skipped' and ram_result.get('reason') != 'threshold_not_met':
        return {"status": "skipped", "message": f"RAM Action Skipped: {ram_result['reason']}"}

    return {"status": "stable", "message": "No intervention required"}