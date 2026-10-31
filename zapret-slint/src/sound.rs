use std::env;
use std::fs;
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};

#[link(name = "winmm")]
unsafe extern "system" {
    fn PlaySoundW(pszSound: *const u16, hmod: *mut std::ffi::c_void, fdwSound: u32) -> i32;
}

const SND_ASYNC: u32 = 0x0001;
const SND_NODEFAULT: u32 = 0x0002;
const SND_FILENAME: u32 = 0x00020000;

fn settings_path() -> Option<PathBuf> {
    env::var("LOCALAPPDATA").ok().map(|appdata| {
        PathBuf::from(appdata)
            .join("zapret-simple")
            .join("ui_settings.json")
    })
}

pub fn is_sound_enabled() -> bool {
    if let Some(path) = settings_path() {
        if path.is_file() {
            if let Ok(content) = fs::read_to_string(&path) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let Some(b) = val.get("sound_enabled").and_then(|v| v.as_bool()) {
                        return b;
                    }
                }
            }
        }
    }
    true
}

pub fn set_sound_enabled(enabled: bool) -> bool {
    if let Some(path) = settings_path() {
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let mut obj = if path.is_file() {
            fs::read_to_string(&path)
                .ok()
                .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
                .unwrap_or_else(|| serde_json::json!({}))
        } else {
            serde_json::json!({})
        };
        if let Some(map) = obj.as_object_mut() {
            map.insert("sound_enabled".to_string(), serde_json::Value::Bool(enabled));
            if let Ok(text) = serde_json::to_string_pretty(&obj) {
                return fs::write(&path, text).is_ok();
            }
        }
    }
    false
}

pub fn toggle_sound() -> bool {
    let new_val = !is_sound_enabled();
    set_sound_enabled(new_val);
    new_val
}

fn find_sound_file(name: &str) -> Option<PathBuf> {
    let filename = format!("{name}.wav");
    let candidates = [
        env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join("assets").join("sounds").join(&filename))),
        Some(Path::new("assets").join("sounds").join(&filename)),
        Some(Path::new("..").join("assets").join("sounds").join(&filename)),
    ];
    for cand in candidates.into_iter().flatten() {
        if cand.is_file() {
            return Some(cand);
        }
    }
    None
}

pub fn play_sound(name: &str) {
    if !is_sound_enabled() {
        return;
    }
    if let Some(sound_path) = find_sound_file(name) {
        let wide: Vec<u16> = sound_path
            .as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();
        unsafe {
            PlaySoundW(
                wide.as_ptr(),
                std::ptr::null_mut(),
                SND_ASYNC | SND_FILENAME | SND_NODEFAULT,
            );
        }
    }
}
