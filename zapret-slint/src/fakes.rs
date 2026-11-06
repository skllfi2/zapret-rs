use std::fs;
use std::path::Path;

#[derive(Clone, Debug)]
pub struct FakeFileInfo {
    pub name: String,
    pub label: String,
    pub description: String,
}

#[derive(Clone, Debug, Default)]
pub struct ActiveFakesStatus {
    pub discord_active_name: String,
    pub game_active_name: String,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum FakeTarget {
    DiscordUdp,
    GameUdp,
}

/// Дружелюбное пояснение к известным типам фейков для обычного пользователя
fn describe_fake(name: &str) -> (&'static str, &'static str) {
    if name.starts_with("stun") {
        ("WebRTC STUN (Голос/Игры)", "Имитирует пакет подключения к голосовому серверу WebRTC. Идеально для Discord Voice и сетевых игр.")
    } else if name.starts_with("quic_") {
        ("QUIC / HTTP/3", "Современный протокол UDP (Google, Steam, Rutube). Эффективно обходит блокировки UDP провайдерами.")
    } else if name.starts_with("tls_clienthello_sochi_park") {
        ("TLS Sochi Park (Рекомендуется)", "Имитация защищенного рукопожатия HTTPS. Наиболее стабильный выбор для Discord.")
    } else if name.starts_with("tls_clienthello_") {
        ("TLS ClientHello (HTTPS)", "Маскирует UDP-пакет под начало стандартной защищенной веб-сессии популярных сервисов.")
    } else {
        ("Стандартный бинарный фейк", "Бинарный шаблон маскировки пакетов zapret.")
    }
}

/// Возвращает список всех доступных файлов фейков в папке bin/ (за исключением активных)
pub fn list_available_fakes(orig_dir: &Path) -> Vec<FakeFileInfo> {
    let bin_dir = orig_dir.join("bin");
    let mut list = Vec::new();

    if let Ok(entries) = fs::read_dir(bin_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(ext) = path.extension()
                && ext.to_string_lossy().eq_ignore_ascii_case("bin")
                && let Some(file_name) = path.file_name()
            {
                let name = file_name.to_string_lossy().to_string();
                if name.starts_with("ACTIVE_") {
                    continue;
                }
                let (label, desc) = describe_fake(&name);
                list.push(FakeFileInfo {
                    name,
                    label: label.to_string(),
                    description: desc.to_string(),
                });
            }
        }
    }

    list.sort_by(|a, b| a.name.cmp(&b.name));
    list
}

/// Сравнивает содержимое двух файлов побайтово
fn files_are_identical(path_a: &Path, path_b: &Path) -> bool {
    let meta_a = match fs::metadata(path_a) {
        Ok(m) => m,
        Err(_) => return false,
    };
    let meta_b = match fs::metadata(path_b) {
        Ok(m) => m,
        Err(_) => return false,
    };
    if meta_a.len() != meta_b.len() {
        return false;
    }

    let bytes_a = match fs::read(path_a) {
        Ok(b) => b,
        Err(_) => return false,
    };
    let bytes_b = match fs::read(path_b) {
        Ok(b) => b,
        Err(_) => return false,
    };

    bytes_a == bytes_b
}

/// Определяет, какие файлы сейчас активны в качестве Discord UDP и Game UDP
pub fn get_active_fakes_status(orig_dir: &Path) -> ActiveFakesStatus {
    let bin_dir = orig_dir.join("bin");
    let discord_active_path = bin_dir.join("ACTIVE_DISCORD_UDP.bin");
    let game_active_path = bin_dir.join("ACTIVE_GAME_UDP.bin");

    let available = list_available_fakes(orig_dir);

    let mut status = ActiveFakesStatus {
        discord_active_name: if discord_active_path.is_file() {
            "Пользовательский / не опознан".into()
        } else {
            "Не установлен".into()
        },
        game_active_name: if game_active_path.is_file() {
            "Пользовательский / не опознан".into()
        } else {
            "Не установлен".into()
        },
    };

    // Ищем точные побайтовые совпадения
    for item in &available {
        let candidate_path = bin_dir.join(&item.name);
        if discord_active_path.is_file() && files_are_identical(&candidate_path, &discord_active_path) {
            status.discord_active_name = item.name.clone();
        }
        if game_active_path.is_file() && files_are_identical(&candidate_path, &game_active_path) {
            status.game_active_name = item.name.clone();
        }
    }

    status
}

/// Назначает выбранный фейк для Discord UDP или Game UDP
pub fn set_active_fake(orig_dir: &Path, target: FakeTarget, source_name: &str) -> Result<(), String> {
    let bin_dir = orig_dir.join("bin");
    let source_path = bin_dir.join(source_name);
    if !source_path.is_file() {
        return Err(format!("Исходный файл фейка '{}' не найден в bin/", source_name));
    }

    let target_name = match target {
        FakeTarget::DiscordUdp => "ACTIVE_DISCORD_UDP.bin",
        FakeTarget::GameUdp => "ACTIVE_GAME_UDP.bin",
    };
    let target_path = bin_dir.join(target_name);

    fs::copy(&source_path, &target_path)
        .map_err(|e| format!("Не удалось скопировать фейк в {target_name}: {e}"))?;

    Ok(())
}

/// Сбрасывает активные фейки на эталонные значения по умолчанию
pub fn reset_to_recommended_fakes(orig_dir: &Path) -> Result<(), String> {
    let bin_dir = orig_dir.join("bin");

    // Ищем рекомендуемый для Discord
    let preferred_discord = [
        "tls_clienthello_sochi_park.bin",
        "quic_initial_steamcommunity_com.bin",
        "stun2.bin",
    ];
    let mut discord_applied = false;
    for cand in preferred_discord {
        if bin_dir.join(cand).is_file() {
            set_active_fake(orig_dir, FakeTarget::DiscordUdp, cand)?;
            discord_applied = true;
            break;
        }
    }

    // Ищем рекомендуемый для Игр
    let preferred_game = [
        "quic_initial_5ka_ru.bin",
        "quic_initial_4pda_to.bin",
        "stun.bin",
    ];
    let mut game_applied = false;
    for cand in preferred_game {
        if bin_dir.join(cand).is_file() {
            set_active_fake(orig_dir, FakeTarget::GameUdp, cand)?;
            game_applied = true;
            break;
        }
    }

    if !discord_applied && !game_applied {
        return Err("В каталоге bin/ не найдены стандартные файлы фейков".into());
    }

    Ok(())
}

/// Форматированный отчёт о фейках для вывода в журнал логов
pub fn format_fakes_info(orig_dir: &Path) -> String {
    let available = list_available_fakes(orig_dir);
    let active = get_active_fakes_status(orig_dir);

    if available.is_empty() {
        return "В папке bin/ не найдены файлы payload (*.bin).\nРекомендуется распаковать полный дистрибутив zapret.\n".into();
    }

    let mut out = String::from("=== ТЕКУЩИЕ АКТИВНЫЕ ФЕЙКИ (UDP) ===\n");
    out.push_str(&format!("• Discord UDP (Голос): {}\n", active.discord_active_name));
    out.push_str(&format!("• Игровой UDP:        {}\n\n", active.game_active_name));
    out.push_str("Доступные шаблоны в bin/:\n");
    for item in available {
        out.push_str(&format!("  - {} ({})\n", item.name, item.label));
    }
    out
}
