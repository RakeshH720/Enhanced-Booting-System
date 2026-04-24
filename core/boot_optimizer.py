import winreg

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
BACKUP_KEY_PATH = r"Software\AI_Boot_Optimizer\Disabled_Startup"

def get_startup_items():
    items = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                items.append({"name": winreg.EnumValue(key, i)[0], "status": "Enabled"})
    except: pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_KEY_PATH, 0, winreg.KEY_READ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                items.append({"name": winreg.EnumValue(key, i)[0], "status": "Disabled"})
    except: pass
    return items

def toggle_startup_item(name, current_status):
    src, dst = (RUN_KEY_PATH, BACKUP_KEY_PATH) if current_status == "Enabled" else (BACKUP_KEY_PATH, RUN_KEY_PATH)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, src, 0, winreg.KEY_ALL_ACCESS) as s_key:
            val, _ = winreg.QueryValueEx(s_key, name)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, dst) as d_key:
            winreg.SetValueEx(d_key, name, 0, winreg.REG_SZ, val)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, src, 0, winreg.KEY_ALL_ACCESS) as s_key:
            winreg.DeleteValue(s_key, name)
        return True
    except: return False

def assess_boot_impact(app_name):
    heavy = ["discord", "steam", "spotify", "chrome", "edge", "update"]
    return "High" if any(h in app_name.lower() for h in heavy) else "Low"