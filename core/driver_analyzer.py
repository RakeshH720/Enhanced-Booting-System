import winreg
import datetime

DRIVER_REGISTRY_PATH = r"SYSTEM\CurrentControlSet\Services"

def get_driver_status_meaning(start_value):
    meanings = {
        0: "Boot Start",
        1: "System Start",
        2: "Auto Start",
        3: "Manual",
        4: "Disabled"
    }
    return meanings.get(start_value, "Unknown")

def analyze_drivers():
    drivers = []
    disabled_count = 0
    auto_count = 0
    unknown_count = 0

    try:
        reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DRIVER_REGISTRY_PATH)
        total = winreg.QueryInfoKey(reg_key)[0]

        for i in range(total):
            try:
                driver_name = winreg.EnumKey(reg_key, i)
                driver_key = winreg.OpenKey(reg_key, driver_name)

                try:
                    start_val = winreg.QueryValueEx(driver_key, "Start")[0]
                    status_meaning = get_driver_status_meaning(start_val)

                    try:
                        image_path = winreg.QueryValueEx(driver_key, "ImagePath")[0]
                    except:
                        image_path = "N/A"

                    try:
                        display_name = winreg.QueryValueEx(driver_key, "DisplayName")[0]
                    except:
                        display_name = driver_name

                    driver_info = {
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "driver_name": driver_name,
                        "display_name": display_name,
                        "start_type": status_meaning,
                        "image_path": image_path,
                        "flag": ""
                    }

                    if start_val == 4:
                        driver_info["flag"] = "DISABLED"
                        disabled_count += 1
                    elif start_val == 0 or start_val == 1:
                        driver_info["flag"] = "CRITICAL"
                        auto_count += 1
                    elif image_path == "N/A":
                        driver_info["flag"] = "MISSING PATH"
                        unknown_count += 1
                    else:
                        driver_info["flag"] = "OK"

                    drivers.append(driver_info)

                except FileNotFoundError:
                    pass

                winreg.CloseKey(driver_key)

            except OSError:
                pass

        winreg.CloseKey(reg_key)

    except Exception as e:
        print(f"Error accessing registry: {e}")
        return []

    return drivers