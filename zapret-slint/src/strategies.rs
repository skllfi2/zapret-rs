use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use crate::settings::{self, GameFilterMode};

pub fn list_strategies(orig_dir: &Path) -> Vec<String> {
    let mut strats = Vec::new();
    if let Ok(entries) = fs::read_dir(orig_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(ext) = path.extension()
                && ext.to_string_lossy().eq_ignore_ascii_case("bat")
                    && let Some(stem) = path.file_stem() {
                        let name = stem.to_string_lossy();
                        if !name.to_lowercase().starts_with("service") {
                            strats.push(name.to_string());
                        }
                    }
        }
    }
    strats.sort();
    strats
}

pub fn strategy_file_path() -> Option<PathBuf> {
    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        let p = PathBuf::from(&local_app_data).join("zapret-rs").join(".strategy");
        if p.is_file() {
            return Some(p);
        }
        let legacy = PathBuf::from(&local_app_data).join("zapret-simple").join(".strategy");
        if legacy.is_file() {
            return Some(legacy);
        }
        Some(p)
    } else {
        None
    }
}

pub fn current_strategy() -> Option<String> {
    // 1. Проверяем значение в реестре службы Windows (куда пишет оригинальный service.bat)
    let hklm = winreg::RegKey::predef(winreg::enums::HKEY_LOCAL_MACHINE);
    if let Ok(svc_key) = hklm.open_subkey(r"System\CurrentControlSet\Services\zapret")
        && let Ok(val) = svc_key.get_value::<String, _>("zapret-discord-youtube") {
            let trimmed = val.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
        }

    // 2. Локальный кэш пользователя (.strategy)
    if let Some(path) = strategy_file_path()
        && path.is_file()
            && let Ok(content) = fs::read_to_string(path) {
                let trimmed = content.trim();
                if !trimmed.is_empty() {
                    return Some(trimmed.to_string());
                }
            }
    None
}

pub fn save_current_strategy(strategy: &str) -> std::io::Result<()> {
    // 1. Сохраняем в реестр Windows службы zapret (как оригинальный service.bat)
    let hklm = winreg::RegKey::predef(winreg::enums::HKEY_LOCAL_MACHINE);
    if let Ok(svc_key) = hklm.open_subkey_with_flags(
        r"System\CurrentControlSet\Services\zapret",
        winreg::enums::KEY_SET_VALUE,
    ) {
        let _ = svc_key.set_value("zapret-discord-youtube", &strategy);
    }

    // 2. Локальный файл .strategy
    if let Some(path) = strategy_file_path() {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, strategy)?;
    }
    Ok(())
}

fn game_filter_ranges(orig_dir: &Path) -> (&'static str, &'static str) {
    let mode = settings::read_game_filter(orig_dir);
    match mode {
        GameFilterMode::All => ("1024-65535", "1024-65535"),
        GameFilterMode::Tcp => ("1024-65535", "12"),
        GameFilterMode::Udp => ("12", "1024-65535"),
        GameFilterMode::Disabled => ("12", "12"),
    }
}

/// Разбирает .bat файл выбранной стратегии и возвращает строку аргументов для winws.exe.
/// Учитывает продолжения строк через `^`, подстановку переменных %BIN%, %LISTS%, %GameFilter*%, %~dp0.
pub fn parse_strategy_args(orig_dir: &Path, strategy_id: &str) -> Result<String, String> {
    let bat_file = orig_dir.join(format!("{strategy_id}.bat"));
    if !bat_file.is_file() {
        return Err(format!("Файл стратегии не найден: {}", bat_file.display()));
    }

    let content = fs::read_to_string(&bat_file)
        .map_err(|e| format!("Ошибка чтения {}: {e}", bat_file.display()))?;

    let mut logical_lines = Vec::new();
    let mut current_line = String::new();

    for raw_line in content.lines() {
        let trimmed = raw_line.trim();
        if trimmed.is_empty()
            || trimmed.starts_with("::")
            || trimmed.starts_with('@')
            || trimmed.to_uppercase().starts_with("REM")
        {
            continue;
        }

        if let Some(stripped) = trimmed.strip_suffix('^') {
            current_line.push(' ');
            current_line.push_str(stripped.trim_end());
            continue;
        }

        if !current_line.is_empty() {
            current_line.push(' ');
            current_line.push_str(trimmed);
            logical_lines.push(std::mem::take(&mut current_line));
        } else {
            logical_lines.push(trimmed.to_string());
        }
    }

    let winws_line = logical_lines
        .into_iter()
        .find(|line| line.to_lowercase().contains("winws.exe"))
        .ok_or_else(|| format!("В файле {strategy_id}.bat не найдена команда запуска winws.exe"))?;

    let winws_idx = winws_line
        .to_lowercase()
        .find("winws.exe")
        .ok_or_else(|| "winws.exe не найден".to_string())?;

    let after_winws = &winws_line[winws_idx + "winws.exe".len()..];
    let args_raw = after_winws.trim_start_matches('"').trim();

    let bin_dir = orig_dir.join("bin").to_string_lossy().trim_end_matches('\\').to_string() + "\\";
    let lists_dir = orig_dir.join("lists").to_string_lossy().trim_end_matches('\\').to_string() + "\\";
    let dp0_dir = orig_dir.to_string_lossy().trim_end_matches('\\').to_string() + "\\";
    let (gf_tcp, gf_udp) = game_filter_ranges(orig_dir);

    let resolved_args = args_raw
        .replace("%BIN%", &bin_dir)
        .replace("%LISTS%", &lists_dir)
        .replace("%~dp0", &dp0_dir)
        .replace("%GameFilterTCP%", gf_tcp)
        .replace("%GameFilterUDP%", gf_udp);

    Ok(resolved_args.trim().to_string())
}

