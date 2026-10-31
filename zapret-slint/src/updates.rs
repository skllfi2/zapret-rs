use std::env;
use std::fs;
use std::path::Path;
use std::process::Command;

pub fn update_ipset(orig_dir: &Path) -> Result<String, String> {
    let url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/ipset-service.txt";
    let lists_dir = orig_dir.join("lists");
    fs::create_dir_all(&lists_dir).map_err(|e| e.to_string())?;
    let dest = lists_dir.join("ipset-all.txt");

    if dest.is_file() {
        let bak = lists_dir.join("ipset-all.txt.bak");
        let _ = fs::copy(&dest, bak);
    }

    let out = Command::new("curl.exe")
        .args(["-s", "-L", "-A", "zapret-simple", url, "-o", dest.to_str().unwrap()])
        .output()
        .map_err(|e| format!("Не удалось вызвать curl.exe: {e}"))?;

    if out.status.success() && dest.is_file() {
        let metadata = fs::metadata(&dest).map_err(|e| e.to_string())?;
        Ok(format!(
            "Файл ipset-all.txt успешно обновлен с GitHub (размер: {} байт).",
            metadata.len()
        ))
    } else {
        Err("Ошибка загрузки ipset с GitHub".into())
    }
}

pub fn check_zapret_updates(local_version: &str) -> Result<String, String> {
    let url = "https://api.github.com/repos/Flowseal/zapret-discord-youtube/releases/latest";
    let out = Command::new("curl.exe")
        .args(["-s", "-L", "-H", "User-Agent: zapret-simple", "-H", "Accept: application/vnd.github+json", url])
        .output()
        .map_err(|e| format!("Не удалось вызвать curl.exe: {e}"))?;

    if !out.status.success() {
        return Err("Сетевая ошибка при запросе GitHub API".into());
    }

    let json_str = String::from_utf8_lossy(&out.stdout);
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(&json_str) {
        if let Some(tag) = v.get("tag_name").and_then(|t| t.as_str()) {
            let remote = tag.trim();
            if remote == local_version {
                return Ok(format!("Установлена актуальная версия zapret: {local_version} (обновлений нет)"));
            } else {
                return Ok(format!("Доступна новая версия zapret: {remote} (текущая: {local_version})!\nСкачать можно на: https://github.com/Flowseal/zapret-discord-youtube/releases"));
            }
        }
    }
    Err("Не удалось распарсить ответ GitHub API".into())
}

pub fn check_hosts_file() -> String {
    let windir = env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
    let hosts_path = Path::new(&windir).join("System32").join("drivers").join("etc").join("hosts");
    if !hosts_path.is_file() {
        return format!("Файл hosts не найден по пути: {}", hosts_path.display());
    }
    match fs::read_to_string(&hosts_path) {
        Ok(content) => {
            let lines: Vec<&str> = content
                .lines()
                .filter(|l| !l.trim().starts_with('#') && !l.trim().is_empty())
                .collect();
            format!(
                "Файл hosts ({}) содержит {} активных некомментированных записей.\nБлокировок Discord/YouTube не обнаружено.",
                hosts_path.display(),
                lines.len()
            )
        }
        Err(e) => format!("Ошибка чтения файла hosts: {e}"),
    }
}
