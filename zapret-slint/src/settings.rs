use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GameFilterMode {
    Disabled,
    Tcp,
    Udp,
    All,
}

impl GameFilterMode {
    pub fn as_label(&self) -> &'static str {
        match self {
            GameFilterMode::Disabled => "Отключен",
            GameFilterMode::Tcp => "Включен (TCP)",
            GameFilterMode::Udp => "Включен (UDP)",
            GameFilterMode::All => "Включен (Все)",
        }
    }

    pub fn next(&self) -> Self {
        match self {
            GameFilterMode::Disabled => GameFilterMode::Tcp,
            GameFilterMode::Tcp => GameFilterMode::Udp,
            GameFilterMode::Udp => GameFilterMode::All,
            GameFilterMode::All => GameFilterMode::Disabled,
        }
    }
}

pub fn read_game_filter(orig_dir: &Path) -> GameFilterMode {
    let path = orig_dir.join("utils").join("game_filter.enabled");
    if !path.is_file() {
        return GameFilterMode::Disabled;
    }
    if let Ok(content) = fs::read_to_string(path) {
        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') || !line.contains('=') {
                continue;
            }
            let parts: Vec<&str> = line.splitn(2, '=').map(|s| s.trim()).collect();
            if parts.len() == 2 && parts[0].eq_ignore_ascii_case("mode") {
                return match parts[1].to_ascii_lowercase().as_str() {
                    "tcp" => GameFilterMode::Tcp,
                    "udp" => GameFilterMode::Udp,
                    "all" => GameFilterMode::All,
                    _ => GameFilterMode::Disabled,
                };
            }
        }
    }
    GameFilterMode::Disabled
}

pub fn set_game_filter_mode(orig_dir: &Path, mode: GameFilterMode) -> Result<(), std::io::Error> {
    let utils_dir = orig_dir.join("utils");
    fs::create_dir_all(&utils_dir)?;
    let path = utils_dir.join("game_filter.enabled");

    let mode_str = match mode {
        GameFilterMode::Disabled => "disabled",
        GameFilterMode::Tcp => "tcp",
        GameFilterMode::Udp => "udp",
        GameFilterMode::All => "all",
    };
    let content = format!("mode={mode_str}\ntcp=1024-65535\nudp=1024-65535\n");
    fs::write(path, content)?;
    Ok(())
}

pub fn cycle_game_filter(orig_dir: &Path) -> Result<GameFilterMode, std::io::Error> {
    let current = read_game_filter(orig_dir);
    let next = current.next();
    set_game_filter_mode(orig_dir, next)?;
    Ok(next)
}

pub fn read_ipset_status(orig_dir: &Path) -> bool {
    let path = orig_dir.join("lists").join("ipset-all.txt");
    path.is_file()
}

pub fn toggle_ipset(orig_dir: &Path) -> Result<bool, std::io::Error> {
    let lists_dir = orig_dir.join("lists");
    let active = lists_dir.join("ipset-all.txt");
    let disabled = lists_dir.join("ipset-all.txt.disabled");

    if active.is_file() {
        fs::rename(active, disabled)?;
        Ok(false)
    } else if disabled.is_file() {
        fs::rename(disabled, active)?;
        Ok(true)
    } else {
        // If neither exists, create dummy/stub ipset file
        fs::create_dir_all(&lists_dir)?;
        fs::write(active, "# IPSet list\n")?;
        Ok(true)
    }
}

pub fn read_check_updates_flag(orig_dir: &Path) -> bool {
    orig_dir.join("utils").join("check_updates.enabled").exists()
}

pub fn toggle_check_updates(orig_dir: &Path) -> Result<bool, std::io::Error> {
    let utils = orig_dir.join("utils");
    fs::create_dir_all(&utils)?;
    let flag = utils.join("check_updates.enabled");
    if flag.exists() {
        fs::remove_file(flag)?;
        Ok(false)
    } else {
        fs::write(flag, "")?;
        Ok(true)
    }
}
