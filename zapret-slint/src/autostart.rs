use std::env;
use winreg::enums::*;
use winreg::RegKey;

const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const APP_NAME: &str = "zapret-rs";

pub fn is_autostart_enabled() -> bool {
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    if let Ok(key) = hkcu.open_subkey_with_flags(RUN_KEY, KEY_READ)
        && let Ok(val) = key.get_value::<String, _>(APP_NAME) {
            return !val.is_empty();
        }
    false
}

pub fn set_autostart_enabled(enabled: bool) -> Result<(), String> {
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let (key, _) = hkcu
        .create_subkey(RUN_KEY)
        .map_err(|e| format!("Не удалось открыть ветку реестра Run: {e}"))?;

    if enabled {
        let exe_path = env::current_exe()
            .map_err(|e| format!("Не удалось определить путь к exe: {e}"))?;
        let cmd = format!("\"{}\" --minimized", exe_path.display());
        key.set_value(APP_NAME, &cmd)
            .map_err(|e| format!("Не удалось записать значение в реестр: {e}"))?;
    } else {
        let _ = key.delete_value(APP_NAME);
    }
    Ok(())
}

pub fn toggle_autostart() -> Result<bool, String> {
    let new_val = !is_autostart_enabled();
    set_autostart_enabled(new_val)?;
    Ok(new_val)
}
