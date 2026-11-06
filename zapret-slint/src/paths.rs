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

        // 2. Портативный режим: подпапка engine/ или zapret/ или сама папка рядом с zapret-rs.exe
        if let Ok(exe) = env::current_exe()
            && let Some(parent) = exe.parent()
        {
            candidates.push(parent.join("engine"));
            candidates.push(parent.join("zapret"));
            candidates.push(parent.to_path_buf());
        }

        // 3. Saved user path from ui_settings.json
        if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
            let settings_file = PathBuf::from(&local_app_data)
                .join("zapret-rs")
                .join("ui_settings.json");
            let legacy_settings_file = PathBuf::from(&local_app_data)
                .join("zapret-simple")
                .join("ui_settings.json");
            let target_settings = if settings_file.is_file() {
                settings_file
            } else {
                legacy_settings_file
            };
            if target_settings.is_file()
                && let Ok(content) = fs::read_to_string(&target_settings)
                && let Ok(val) = serde_json::from_str::<serde_json::Value>(&content)
                && let Some(p) = val.get("zapret_dir").and_then(|v| v.as_str()) {
                    candidates.push(PathBuf::from(p));
                }
        }

        // 4. Active Windows service ImagePath directory (внешний zapret в системе)
        let hklm = winreg::RegKey::predef(winreg::enums::HKEY_LOCAL_MACHINE);
        if let Ok(svc_key) = hklm.open_subkey(r"System\CurrentControlSet\Services\zapret")
            && let Ok(image_path) = svc_key.get_value::<String, _>("ImagePath") {
                let clean = image_path.trim_matches('"');
                if let Some(exe_idx) = clean.to_lowercase().find("winws.exe") {
                    let exe_sub = &clean[..exe_idx + "winws.exe".len()];
                    let p = PathBuf::from(exe_sub);
                    if let Some(bin_dir) = p.parent()
                        && let Some(orig_dir) = bin_dir.parent() {
                            candidates.push(orig_dir.to_path_buf());
                        }
                }
            }

        // 5. Local relative ./zapret/ or current exe dir
        if let Ok(exe) = env::current_exe()
            && let Some(parent) = exe.parent() {
                candidates.push(parent.join("zapret"));
                candidates.push(parent.to_path_buf());
            }

        // 6. %LOCALAPPDATA%\zapret-rs\engine or legacy zapret-simple\zapret
        if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
            candidates.push(PathBuf::from(&local_app_data).join("zapret-rs").join("engine"));
            candidates.push(PathBuf::from(&local_app_data).join("zapret-rs").join("zapret"));
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
        if self.service_bat.is_file()
            && let Ok(content) = fs::read_to_string(&self.service_bat)
                && let Ok(re) = regex::Regex::new(r#"set\s+"LOCAL_VERSION=([^"]+)""#)
                    && let Some(caps) = re.captures(&content)
                        && let Some(m) = caps.get(1) {
                            return format!("v{}", m.as_str().trim());
                        }
        let ver_file = self.orig_dir.join("version.txt");
        if ver_file.is_file()
            && let Ok(content) = fs::read_to_string(&ver_file) {
                return format!("v{}", content.trim());
            }
        "v?".to_string()
    }
}

pub fn get_internal_zapret_dir() -> Option<PathBuf> {
    env::var("LOCALAPPDATA")
        .ok()
        .map(|app_data| PathBuf::from(app_data).join("zapret-rs").join("engine"))
}

/// Выполняет миграцию (копирование) файлов из внешнего каталога zapret в постоянное хранилище
/// приложения %LOCALAPPDATA%\zapret-rs\engine.
pub fn migrate_to_internal_storage(source_dir: &std::path::Path) -> Result<PathBuf, String> {
    let target = get_internal_zapret_dir()
        .ok_or_else(|| "Не удалось определить LOCALAPPDATA".to_string())?;

    if !source_dir.is_dir() {
        return Err(format!("Исходный каталог не существует: {}", source_dir.display()));
    }

    if source_dir == target {
        return Ok(target);
    }

    let _ = fs::create_dir_all(&target);

    // Используем robocopy для надежного рекурсивного копирования всех поддиректорий
    let src_str = source_dir.to_string_lossy().trim_end_matches('\\').to_string();
    let tgt_str = target.to_string_lossy().trim_end_matches('\\').to_string();

    let output = std::process::Command::new("robocopy")
        .args([&src_str, &tgt_str, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns"])
        .output();

    if let Ok(res) = output {
        // Robocopy return codes 0..7 mean success / files copied
        if res.status.code().unwrap_or(0) <= 7
            && target.join("bin").join("winws.exe").is_file() {
                let _ = save_custom_zapret_dir(&target);
                return Ok(target);
            }
    }

    Err(format!("Не удалось скопировать zapret из {} в {}", source_dir.display(), target.display()))
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
        let dir_path = PathBuf::from(&local_app_data).join("zapret-rs");
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
