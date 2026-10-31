use std::fs;
use std::path::Path;

pub struct FakeItem {
    pub name: String,
    pub is_active: bool,
}

pub fn list_fake_payloads(orig_dir: &Path) -> Vec<FakeItem> {
    let bin_dir = orig_dir.join("bin");
    let mut list = Vec::new();
    if let Ok(entries) = fs::read_dir(bin_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(ext) = path.extension() {
                if ext.to_string_lossy().eq_ignore_ascii_case("bin") {
                    if let Some(name) = path.file_name() {
                        let name_str = name.to_string_lossy().to_string();
                        let is_active = name_str.to_ascii_uppercase().starts_with("ACTIVE_");
                        list.push(FakeItem {
                            name: name_str,
                            is_active,
                        });
                    }
                }
            }
        }
    }
    list.sort_by(|a, b| a.name.cmp(&b.name));
    list
}

pub fn format_fakes_info(orig_dir: &Path) -> String {
    let list = list_fake_payloads(orig_dir);
    if list.is_empty() {
        return "В папке bin/ не найдены файлы payload (*.bin).\nРекомендуется выполнить распаковку полного архива zapret.\n".into();
    }
    let mut out = String::from("Найденные fake-payloads (*.bin) в bin/:\n");
    for item in list {
        let tag = if item.is_active { "[АКТИВЕН] " } else { "          " };
        out.push_str(&format!("{tag}{}\n", item.name));
    }
    out
}
