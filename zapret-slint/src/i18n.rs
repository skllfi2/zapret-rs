use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use windows::Win32::Globalization::GetUserDefaultUILanguage;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AppLanguage {
    System,
    Russian,
    English,
}

impl AppLanguage {
    pub fn as_str(&self) -> &'static str {
        match self {
            AppLanguage::System => "Авто",
            AppLanguage::Russian => "Русский",
            AppLanguage::English => "English",
        }
    }

    /// Определяет фактический активный язык (с учетом системной локали Windows)
    pub fn resolve(&self) -> &'static str {
        match self {
            AppLanguage::Russian => "ru",
            AppLanguage::English => "en",
            AppLanguage::System => {
                let lcid = unsafe { GetUserDefaultUILanguage() };
                let primary_lang = lcid & 0x03FF;
                // 0x19: Russian, 0x22: Ukrainian, 0x23: Belarusian, 0x2B: Kazakh
                if primary_lang == 0x19 || primary_lang == 0x22 || primary_lang == 0x23 || primary_lang == 0x2B {
                    "ru"
                } else {
                    "en"
                }
            }
        }
    }
}

fn get_language_file_path() -> Option<PathBuf> {
    std::env::var("LOCALAPPDATA")
        .ok()
        .map(|p| PathBuf::from(p).join("zapret-simple").join("language.json"))
}

pub fn load_saved_language() -> AppLanguage {
    if let Some(p) = get_language_file_path()
        && p.is_file()
        && let Ok(txt) = fs::read_to_string(&p)
        && let Ok(lang) = serde_json::from_str::<AppLanguage>(&txt)
    {
        return lang;
    }
    AppLanguage::System
}

pub fn save_language(lang: AppLanguage) {
    if let Some(p) = get_language_file_path() {
        if let Some(parent) = p.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(s) = serde_json::to_string(&lang) {
            let _ = fs::write(p, s);
        }
    }
}
