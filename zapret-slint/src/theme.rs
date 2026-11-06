use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use winreg::enums::*;
use winreg::RegKey;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AppTheme {
    System,
    Dark,
    Light,
}

impl AppTheme {
    pub fn as_str(&self) -> &'static str {
        match self {
            AppTheme::System => "Системная",
            AppTheme::Dark => "Темная",
            AppTheme::Light => "Светлая",
        }
    }

    #[allow(dead_code)]
    pub fn next(&self) -> Self {
        match self {
            AppTheme::System => AppTheme::Dark,
            AppTheme::Dark => AppTheme::Light,
            AppTheme::Light => AppTheme::System,
        }
    }

    pub fn is_dark(&self) -> bool {
        match self {
            AppTheme::Dark => true,
            AppTheme::Light => false,
            AppTheme::System => is_windows_dark_mode(),
        }
    }
}

pub fn is_windows_dark_mode() -> bool {
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    if let Ok(key) = hkcu.open_subkey(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        && let Ok(val) = key.get_value::<u32, _>("AppsUseLightTheme") {
            return val == 0;
        }
    true // default to dark if unknown
}

fn get_theme_file_path() -> Option<PathBuf> {
    std::env::var("LOCALAPPDATA")
        .ok()
        .map(|p| PathBuf::from(p).join("zapret-simple").join("theme.json"))
}

pub fn load_saved_theme() -> AppTheme {
    if let Some(p) = get_theme_file_path()
        && p.is_file()
            && let Ok(txt) = fs::read_to_string(&p)
                && let Ok(t) = serde_json::from_str::<AppTheme>(&txt) {
                    return t;
                }
    AppTheme::System
}

pub fn save_theme(theme: AppTheme) {
    if let Some(p) = get_theme_file_path() {
        if let Some(parent) = p.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(s) = serde_json::to_string(&theme) {
            let _ = fs::write(p, s);
        }
    }
}
