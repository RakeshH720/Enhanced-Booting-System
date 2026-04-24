import time
import psutil
from core.health_monitor import get_system_health, get_dual_trend
from core.learning_engine import get_learned_ignore_list, get_adaptive_thresholds
from core.action_engine import run_autopilot
from core.anomaly_engine import calculate_raw_score, check_pending_reboot
from core.state_manager import get_state, increment_failure, reset_failures
from core.driver_analyzer import analyze_drivers


def evaluate_system_state(autopilot_enabled=True):
    # 1. GATHER STATE
    health = get_system_health()
    trend = get_dual_trend()
    learned_ignore = get_learned_ignore_list()
    state = get_state()

    # 🔥 Adaptive thresholds (long-term learning)
    thresholds = get_adaptive_thresholds()
    trigger_cpu = thresholds.get('cpu_warn', 80.0)
    trigger_ram = thresholds.get('ram_warn', 85.0)

    # Driver analysis
    driver_data = analyze_drivers()
    driver_summary = driver_data.get("summary", {}) if isinstance(driver_data, dict) else {}

    autopilot_result = None

    # 2. FEEDBACK LOOP & VALIDATION (Dynamic triggers)
    if autopilot_enabled and (trend['short_cpu'] > trigger_cpu or health['ram_used_percent'] > trigger_ram):
        autopilot_result = run_autopilot()

        if autopilot_result and autopilot_result.get('status') == 'executed':
            time.sleep(3.0)

            post_trend = get_dual_trend()
            post_health = get_system_health()

            if post_trend['short_cpu'] < trigger_cpu and post_health['ram_used_percent'] < trigger_ram:
                reset_failures()
                state["consecutive_failures"] = 0
            else:
                state["consecutive_failures"] = increment_failure()

            trend = post_trend
            health = post_health

    # 3. BASELINE EVALUATION
    uptime_days = (time.time() - psutil.boot_time()) / 86400

    raw_anomaly = calculate_raw_score(
        health,
        trend['long_cpu'],
        uptime_days,
        check_pending_reboot()
    )

    # 4. DRIVER TELEMETRY INTEGRATION
    ratio = driver_summary.get("severity_ratio", 0.0)

    if ratio > 0.15:
        raw_anomaly['reboot_score'] += 15
        raw_anomaly['breakdown'].append(("Severe Driver Instability", 15))
        raw_anomaly['recommendations'].append(
            f"🔴 CRITICAL: {driver_summary.get('top_issue', 'Unknown')} causing widespread registry issues."
        )

    elif ratio > 0.05:
        raw_anomaly['reboot_score'] += 5
        raw_anomaly['breakdown'].append(("Moderate Driver Instability", 5))

    # 5. EXPECTED LOAD DAMPENER
    if trend['long_cpu'] > 85:
        candidates = list(psutil.process_iter(['name']))

        for p in candidates:
            try:
                p.cpu_percent(None)
            except:
                pass

        time.sleep(0.2)

        heavy_procs = []
        for p in candidates:
            try:
                cpu_val = p.cpu_percent(None)
                if cpu_val > 5:
                    heavy_procs.append({
                        'name': p.info['name'].lower(),
                        'cpu': cpu_val
                    })
            except:
                pass

        total_load = sum(p['cpu'] for p in heavy_procs)
        ignored_load = sum(p['cpu'] for p in heavy_procs if p['name'] in learned_ignore)

        if total_load > 0:
            expected_ratio = ignored_load / total_load
            if expected_ratio > 0.6:
                reduction = raw_anomaly['reboot_score'] * expected_ratio
                raw_anomaly['reboot_score'] -= reduction
                raw_anomaly['breakdown'].append(
                    (f"Expected Load Dampener ({round(expected_ratio * 100)}%)", -round(reduction))
                )

    # 6. SELF-HEALING REWARD
    if autopilot_result and autopilot_result.get('status') == 'executed':
        original = raw_anomaly['reboot_score']
        raw_anomaly['reboot_score'] *= 0.8
        reduction = original - raw_anomaly['reboot_score']
        raw_anomaly['breakdown'].append(("Self-Healing Dampener", -round(reduction)))

    # 7. FINAL JUDGMENT (Clean + UI synced)
    current_failures = state["consecutive_failures"]
    final_score = min(max(raw_anomaly['reboot_score'], 0), 100)

    if current_failures >= 3:
        status = "REBOOT REQUIRED"
        severity = "CRITICAL"
        raw_anomaly['recommendations'].insert(
            0,
            f"🔴 CRITICAL: Autopilot failed {current_failures} times. Possible memory leak."
        )

    elif final_score >= 60:
        status = "REBOOT RECOMMENDED"
        severity = "WARNING"

    elif final_score >= 30:
        status = "REBOOT SUGGESTED"
        severity = "WARNING"

    else:
        status = "STABLE"
        severity = "NORMAL"

    # 🔥 FINAL RETURN (Perfectly aligned with UI)
    return {
        "health": health,
        "trend": trend,
        "reboot_score": round(final_score),
        "reboot_status": status,
        "severity": severity,
        "breakdown": raw_anomaly['breakdown'],
        "recommendations": raw_anomaly['recommendations'],
        "autopilot_feedback": autopilot_result,
        "driver_data": driver_data
    }