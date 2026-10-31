use std::env;
use std::fs;
use std::path::PathBuf;

#[allow(dead_code)]
pub struct ZapretPaths {
    pub orig_dir: PathBuf,
    pub bin_dir: PathBuf,
    pub winws_exe: PathBuf,
    pub service_bat: PathBuf,
}

impl ZapretPaths {
    pub fn detect() -> Option<Self> {
        let mut candidates = Vec::new();

        // 1. ZAPRET_DIR env
        if let Ok(val) = env::var("ZAPRET_DIR") {
            candidates.push(PathBuf::from(val));
        }

        // 2. Saved user path from ui_settings.json
        if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
            let settings_file = PathBuf::from(&local_app_data)
                .join("zapret-simple")
                .join("ui_settings.json");
            if settings_file.is_file() {
                if let Ok(content) = fs::read_to_string(&settings_file) {
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                        if let Some(p) = val.get("zapret_dir").and_then(|v| v.as_str()) {
                            candidates.push(PathBuf::from(p));
                        }
                    }
                }
            }
        }

        // 3. Local relative ./zapret/ or current exe dir
        if let Ok(exe) = env::current_exe() {
            if let Some(parent) = exe.parent() {
                candidates.push(parent.join("zapret"));
                candidates.push(parent.to_path_buf());
            }
        }

        // 4. %LOCALAPPDATA%\zapret-simple\zapret or AppWatch
        if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
            candidates.push(PathBuf::from(&local_app_data).join("zapret-simple").join("zapret"));
            candidates.push(PathBuf::from(&local_app_data).join("AppWatch").join("Apps").join("zapret-discord-youtube"));
        }

        // 5. ~/Pictures/zapret-discord-youtube
        if let Ok(userprofile) = env::var("USERPROFILE") {
            candidates.push(PathBuf::from(userprofile).join("Pictures").join("zapret-discord-youtube"));
        }

        for c in candidates {
            let winws = c.join("bin").join("winws.exe");
            if winws.is_file() {
                return Some(Self {
                    bin_dir: c.join("bin"),
                    winws_exe: winws,
                    service_bat: c.join("service.bat"),
                    orig_dir: c,
                });
            }
        }

        None
    }

    pub fn local_version(&self) -> String {
        if self.service_bat.is_file() {
            if let Ok(content) = fs::read_to_string(&self.service_bat) {
                if let Ok(re) = regex::Regex::new(r#"set\s+"LOCAL_VERSION=([^"]+)""#) {
                    if let Some(caps) = re.captures(&content) {
                        if let Some(m) = caps.get(1) {
                            return format!("v{}", m.as_str().trim());
                        }
                    }
                }
            }
        }
        let ver_file = self.orig_dir.join("version.txt");
        if ver_file.is_file() {
            if let Ok(content) = fs::read_to_string(&ver_file) {
                return format!("v{}", content.trim());
            }
        }
        "v?".to_string()
    }
}

pub fn save_custom_zapret_dir(dir: &std::path::Path) -> Result<(), String> {
    if !dir.is_dir() {
        return Err(format!("Папка не существует: {}", dir.display()));
    }
    let winws = dir.join("bin").join("winws.exe");
    if !winws.is_file() {
        return Err(format!("В папке не найден bin\\winws.exe: {}", dir.display()));
    }

    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        let dir_path = PathBuf::from(&local_app_data).join("zapret-simple");
        let _ = fs::create_dir_all(&dir_path);
        let settings_file = dir_path.join("ui_settings.json");

        let mut obj = if settings_file.is_file() {
            fs::read_to_string(&settings_file)
                .ok()
                .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
                .unwrap_or_else(|| serde_json::json!({}))
        } else {
            serde_json::json!({})
        };

        if let Some(map) = obj.as_object_mut() {
            map.insert("zapret_dir".to_string(), serde_json::Value::String(dir.to_string_lossy().to_string()));
            if let Ok(text) = serde_json::to_string_pretty(&obj) {
                let _ = fs::write(settings_file, text);
            }
        }
        return Ok(());
    }
    Err("Не удалось определить LOCALAPPDATA".into())
}

pub fn unpack_zapret_zip(zip_path: &std::path::Path, target_dir: Option<&std::path::Path>) -> Result<PathBuf, String> {
    if !zip_path.is_file() {
        return Err(format!("Файл архива не найден: {}", zip_path.display()));
    }

    let dest = if let Some(d) = target_dir {
        d.to_path_buf()
    } else if let Ok(exe) = env::current_exe() {
        exe.parent().map(|p| p.join("zapret")).unwrap_or_else(|| PathBuf::from("zapret"))
    } else {
        PathBuf::from("zapret")
    };

    let _ = fs::create_dir_all(&dest);

    let script = format!(
        "Expand-Archive -LiteralPath '{}' -DestinationPath '{}' -Force",
        zip_path.to_string_lossy().replace('\'', "''"),
        dest.to_string_lossy().replace('\'', "''")
    );

    let res = std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", &script])
        .output()
        .map_err(|e| format!("Ошибка выполнения Expand-Archive: {e}"))?;

    if !res.status.success() {
        return Err(format!("Не удалось распаковать архив: {}", String::from_utf8_lossy(&res.stderr)));
    }

    // Проверяем: winws лежит прямо в dest/bin/winws.exe или во вложенной папке
    if dest.join("bin").join("winws.exe").is_file() {
        save_custom_zapret_dir(&dest)?;
        return Ok(dest);
    }

    // Поиск во вложенных поддиректориях
    if let Ok(entries) = fs::read_dir(&dest) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() && path.join("bin").join("winws.exe").is_file() {
                save_custom_zapret_dir(&path)?;
                return Ok(path);
            }
        }
    }

    Err("Архив распакован, но bin\\winws.exe не обнаружен.".into())
}
