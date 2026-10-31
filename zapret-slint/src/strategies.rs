use std::env;
use std::fs;
use std::path::{Path, PathBuf};

pub fn list_strategies(orig_dir: &Path) -> Vec<String> {
    let mut strats = Vec::new();
    if let Ok(entries) = fs::read_dir(orig_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(ext) = path.extension() {
                if ext.to_string_lossy().eq_ignore_ascii_case("bat") {
                    if let Some(stem) = path.file_stem() {
                        let name = stem.to_string_lossy();
                        if !name.to_lowercase().starts_with("service") {
                            strats.push(name.to_string());
                        }
                    }
                }
            }
        }
    }
    strats.sort();
    strats
}

pub fn strategy_file_path() -> Option<PathBuf> {
    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        Some(
            PathBuf::from(local_app_data)
                .join("zapret-simple")
                .join(".strategy"),
        )
    } else {
        None
    }
}

pub fn current_strategy() -> Option<String> {
    if let Some(path) = strategy_file_path() {
        if path.is_file() {
            if let Ok(content) = fs::read_to_string(path) {
                let trimmed = content.trim();
                if !trimmed.is_empty() {
                    return Some(trimmed.to_string());
                }
            }
        }
    }
    None
}

pub fn save_current_strategy(strategy: &str) -> std::io::Result<()> {
    if let Some(path) = strategy_file_path() {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, strategy)?;
    }
    Ok(())
}
