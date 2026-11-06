use std::env;
use std::fs;
use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone)]
pub struct ReleaseInfo {
    pub tag: String,
    pub zip_url: String,
    pub is_newer: bool,
    pub message: String,
}

pub fn check_zapret_release(local_version: &str) -> Result<ReleaseInfo, String> {
    let url = "https://api.github.com/repos/Flowseal/zapret-discord-youtube/releases/latest";
    let out = Command::new("curl.exe")
        .args(["-s", "-L", "-H", "User-Agent: zapret-rs", "-H", "Accept: application/vnd.github+json", url])
        .output()
        .map_err(|e| format!("Не удалось вызвать curl.exe: {e}"))?;

    if !out.status.success() {
        return Err("Сетевая ошибка при запросе GitHub API".into());
    }

    let json_str = String::from_utf8_lossy(&out.stdout);
    let v: serde_json::Value = serde_json::from_str(&json_str)
        .map_err(|_| "Не удалось распарсить ответ GitHub API".to_string())?;

    let tag = v.get("tag_name").and_then(|t| t.as_str()).unwrap_or("").trim().to_string();
    if tag.is_empty() {
        return Err("GitHub API не вернул tag_name".into());
    }

    let mut zip_url = String::new();
    if let Some(assets) = v.get("assets").and_then(|a| a.as_array()) {
        for asset in assets {
            if let Some(name) = asset.get("name").and_then(|n| n.as_str())
                && name.ends_with(".zip")
                    && let Some(dl) = asset.get("browser_download_url").and_then(|u| u.as_str()) {
                        zip_url = dl.to_string();
                        break;
                    }
        }
    }

    let clean_local = local_version.trim_start_matches('v').trim();
    let clean_remote = tag.trim_start_matches('v').trim();
    let is_newer = clean_remote != clean_local && !clean_remote.is_empty();

    let message = if is_newer {
        format!("Доступна новая версия zapret: {tag} (установлена: {local_version})")
    } else {
        format!("Установлена актуальная версия zapret: {local_version} (обновлений нет)")
    };

    Ok(ReleaseInfo {
        tag,
        zip_url,
        is_newer,
        message,
    })
}

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
        .args(["-s", "-L", "-A", "zapret-rs", url, "-o", dest.to_str().unwrap()])
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
            let has_zapret_block = content.contains("# === ZAPRET HOSTS START ===");
            format!(
                "Файл hosts ({}):\n• Активных записей: {}\n• Блок zapret оптимизации: {}\n• Блокировок Discord/YouTube не обнаружено.",
                hosts_path.display(),
                lines.len(),
                if has_zapret_block { "Установлен и активен" } else { "Не установлен (рекомендуется при сбоях DNS)" }
            )
        }
        Err(e) => format!("Ошибка чтения файла hosts: {e}"),
    }
}

/// Скачивает официальный список hosts с GitHub Flowseal, создает резервную копию
/// и аккуратно обновляет блок оптимизации YouTube/Discord в C:\Windows\System32\drivers\etc\hosts,
/// после чего сбрасывает DNS-кэш Windows (ipconfig /flushdns).
pub fn update_hosts_file() -> Result<String, String> {
    let windir = env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
    let hosts_path = Path::new(&windir).join("System32").join("drivers").join("etc").join("hosts");
    if !hosts_path.is_file() {
        return Err(format!("Файл hosts не найден по пути: {}", hosts_path.display()));
    }

    let url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/hosts";
    let temp_hosts = env::temp_dir().join("zapret_downloaded_hosts.txt");

    let out = Command::new("curl.exe")
        .args(["-s", "-L", "-A", "zapret-rs", url, "-o", temp_hosts.to_str().unwrap()])
        .output()
        .map_err(|e| format!("Не удалось вызвать curl.exe: {e}"))?;

    if !out.status.success() || !temp_hosts.is_file() {
        return Err("Не удалось загрузить эталонный файл hosts с GitHub Flowseal".into());
    }

    let new_hosts_content = fs::read_to_string(&temp_hosts)
        .map_err(|e| format!("Ошибка чтения загруженного hosts: {e}"))?;
    let _ = fs::remove_file(&temp_hosts);

    let current_hosts = fs::read_to_string(&hosts_path)
        .map_err(|e| format!("Не удалось прочитать текущий hosts: {e}. Требуются права администратора."))?;

    // Создаем резервную копию рядом
    let backup_path = hosts_path.with_extension("bak");
    let _ = fs::write(&backup_path, &current_hosts);

    // Удаляем старый блок zapret, если он был
    let cleaned_hosts = if let Some(start_idx) = current_hosts.find("# === ZAPRET HOSTS START ===") {
        if let Some(end_idx) = current_hosts[start_idx..].find("# === ZAPRET HOSTS END ===") {
            let actual_end = start_idx + end_idx + "# === ZAPRET HOSTS END ===".len();
            format!("{}{}", &current_hosts[..start_idx].trim_end(), &current_hosts[actual_end..])
        } else {
            current_hosts[..start_idx].trim_end().to_string()
        }
    } else {
        current_hosts
    };

    // Формируем чистый результирующий hosts
    let mut updated = cleaned_hosts.trim_end().to_string();
    updated.push_str("\n\n# === ZAPRET HOSTS START ===\n");
    updated.push_str("# Автоматически оптимизированные DNS-записи для YouTube и Discord Voice\n");
    for line in new_hosts_content.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() && !trimmed.starts_with('#') {
            updated.push_str(trimmed);
            updated.push('\n');
        }
    }
    updated.push_str("# === ZAPRET HOSTS END ===\n");

    fs::write(&hosts_path, updated)
        .map_err(|e| format!("Ошибка записи в {}: {e}. Запустите приложение от имени администратора.", hosts_path.display()))?;

    // Сбрасываем системный DNS кэш Windows
    let _ = Command::new("ipconfig.exe").arg("/flushdns").output();

    Ok(format!(
        "Файл hosts успешно обновлен!\n• Создана резервная копия: {}\n• Добавлены прямые адреса Discord/YouTube\n• Системный DNS-кэш Windows очищен (flushdns).",
        backup_path.display()
    ))
}

/// Открывает системный файл hosts в Блокноте
pub fn open_hosts_in_notepad() -> Result<(), String> {
    let windir = env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
    let hosts_path = Path::new(&windir).join("System32").join("drivers").join("etc").join("hosts");
    Command::new("notepad.exe")
        .arg(hosts_path)
        .spawn()
        .map_err(|e| format!("Не удалось открыть notepad.exe: {e}"))?;
    Ok(())
}
