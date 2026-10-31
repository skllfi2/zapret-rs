use std::env;
use std::fs;
use std::path::Path;
use std::process::Command;
use winreg::enums::{HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE};
use winreg::RegKey;

use crate::process;
use crate::scm::{self, ServiceState};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiagLevel {
    Ok,
    Warn,
    Bad,
}

impl DiagLevel {
    pub fn tag(&self) -> &'static str {
        match self {
            DiagLevel::Ok => "[+]",
            DiagLevel::Warn => "[?]",
            DiagLevel::Bad => "[X]",
        }
    }
}

pub struct DiagItem {
    pub name: &'static str,
    pub level: DiagLevel,
    pub msg: String,
}

pub struct DiagReport {
    pub items: Vec<DiagItem>,
    pub ok_count: usize,
    pub warn_count: usize,
    pub bad_count: usize,
}

impl DiagReport {
    pub fn format_text(&self) -> String {
        let mut out = String::new();
        out.push_str("================ ДИАГНОСТИКА СИСТЕМЫ (18 проверок) ================\n\n");
        for item in &self.items {
            out.push_str(&format!("{:<4} {:<24} : {}\n", item.level.tag(), item.name, item.msg));
        }
        out.push_str("\n--------------------------------------------------------------------\n");
        out.push_str(&format!(
            "ИТОГ: Всего: {} | Успешно [+]: {} | Внимание [?]: {} | Ошибок [X]: {}\n",
            self.items.len(),
            self.ok_count,
            self.warn_count,
            self.bad_count
        ));
        out.push_str("====================================================================\n");
        out
    }
}

pub fn run_full_diagnostics(orig_dir: &Path) -> DiagReport {
    let mut items = Vec::new();

    // 1. Path
    let winws = orig_dir.join("bin").join("winws.exe");
    if winws.is_file() {
        items.push(DiagItem {
            name: "Каталог zapret",
            level: DiagLevel::Ok,
            msg: format!("Установлен в: '{}'", orig_dir.display()),
        });
    } else {
        items.push(DiagItem {
            name: "Каталог zapret",
            level: DiagLevel::Bad,
            msg: format!("winws.exe не найден в '{}'", orig_dir.display()),
        });
    }

    // 2. BFE (Base Filtering Engine)
    let bfe_state = scm::query_named_service("BFE");
    if bfe_state == ServiceState::Running {
        items.push(DiagItem {
            name: "Служба BFE",
            level: DiagLevel::Ok,
            msg: "Служба Base Filtering Engine запущена и активна".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Служба BFE",
            level: DiagLevel::Bad,
            msg: format!("Служба BFE в состоянии: {}", bfe_state.as_str()),
        });
    }

    // 3. Proxy (HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings)
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let proxy_item = if let Ok(sub) = hkcu.open_subkey("Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings") {
        let enable: u32 = sub.get_value("ProxyEnable").unwrap_or(0);
        if enable == 1 {
            let server: String = sub.get_value("ProxyServer").unwrap_or_else(|_| "?".into());
            DiagItem {
                name: "Системный прокси",
                level: DiagLevel::Warn,
                msg: format!("Включен системный прокси: {server}"),
            }
        } else {
            DiagItem {
                name: "Системный прокси",
                level: DiagLevel::Ok,
                msg: "Системный прокси отключен (прямое подключение)".into(),
            }
        }
    } else {
        DiagItem {
            name: "Системный прокси",
            level: DiagLevel::Ok,
            msg: "Параметры прокси не заданы".into(),
        }
    };
    items.push(proxy_item);

    // 4. TCP timestamps
    let ts_output = Command::new("netsh")
        .args(["interface", "tcp", "show", "global"])
        .output();
    let ts_item = match ts_output {
        Ok(out) => {
            let s = String::from_utf8_lossy(&out.stdout).to_lowercase();
            if s.contains("disabled") {
                // Try auto-enabling
                let _ = Command::new("netsh")
                    .args(["int", "tcp", "set", "global", "timestamps=enabled"])
                    .output();
                DiagItem {
                    name: "TCP Timestamps (RFC1323)",
                    level: DiagLevel::Warn,
                    msg: "Были отключены, отправлена команда на авто-включение".into(),
                }
            } else if s.contains("enabled") {
                DiagItem {
                    name: "TCP Timestamps (RFC1323)",
                    level: DiagLevel::Ok,
                    msg: "Включены (RFC 1323 timestamps active)".into(),
                }
            } else {
                DiagItem {
                    name: "TCP Timestamps (RFC1323)",
                    level: DiagLevel::Ok,
                    msg: "Параметры стека TCP в норме".into(),
                }
            }
        }
        Err(e) => DiagItem {
            name: "TCP Timestamps (RFC1323)",
            level: DiagLevel::Warn,
            msg: format!("Ошибка вызова netsh: {e}"),
        },
    };
    items.push(ts_item);

    // 5. Adguard
    if process::is_process_running("AdguardSvc.exe") || process::is_process_running("Adguard.exe") {
        items.push(DiagItem {
            name: "Adguard",
            level: DiagLevel::Bad,
            msg: "Обнаружен процесс Adguard — конфликт фильтрации пакетов WFP".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Adguard",
            level: DiagLevel::Ok,
            msg: "Процессы Adguard не обнаружены".into(),
        });
    }

    // 6. Killer Network
    let k1 = scm::query_named_service("KNDBWM");
    let k2 = scm::query_named_service("Killer Network Service");
    if k1 != ServiceState::NotInstalled || k2 != ServiceState::NotInstalled {
        items.push(DiagItem {
            name: "Killer Network",
            level: DiagLevel::Bad,
            msg: "Обнаружена служба Killer Network — вызывает сбои WinDivert".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Killer Network",
            level: DiagLevel::Ok,
            msg: "Служба Killer Network отсутствует".into(),
        });
    }

    // 7. Intel Connectivity
    let ic = scm::query_named_service("Intel Connectivity Network Service");
    if ic != ServiceState::NotInstalled {
        items.push(DiagItem {
            name: "Intel Connectivity",
            level: DiagLevel::Bad,
            msg: "Обнаружена служба Intel Connectivity — возможны сбои сокетов".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Intel Connectivity",
            level: DiagLevel::Ok,
            msg: "Служба Intel Connectivity отсутствует".into(),
        });
    }

    // 8. Check Point / ZoneAlarm
    let cp1 = scm::query_named_service("tracsrvwrapper");
    let cp2 = scm::query_named_service("epwd");
    let cp3 = scm::query_named_service("vsmon");
    if cp1 != ServiceState::NotInstalled || cp2 != ServiceState::NotInstalled || cp3 != ServiceState::NotInstalled {
        items.push(DiagItem {
            name: "Check Point / ZoneAlarm",
            level: DiagLevel::Bad,
            msg: "Обнаружены компоненты Check Point / ZoneAlarm".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Check Point / ZoneAlarm",
            level: DiagLevel::Ok,
            msg: "Конфликтов с Check Point не обнаружено".into(),
        });
    }

    // 9. SmartByte
    let sb1 = scm::query_named_service("SmartByte Network Service");
    let sb2 = scm::query_named_service("SmartByteTelemetry");
    if sb1 != ServiceState::NotInstalled || sb2 != ServiceState::NotInstalled {
        items.push(DiagItem {
            name: "SmartByte",
            level: DiagLevel::Bad,
            msg: "Обнаружен SmartByte — принудительно ограничивает трафик".into(),
        });
    } else {
        items.push(DiagItem {
            name: "SmartByte",
            level: DiagLevel::Ok,
            msg: "SmartByte отсутствует".into(),
        });
    }

    // 10. Cyrillic in path
    let path_str = orig_dir.to_string_lossy();
    if path_str.chars().any(|c| (c as u32) > 127) {
        items.push(DiagItem {
            name: "Символы в пути",
            level: DiagLevel::Warn,
            msg: "Путь содержит кириллицу или спецсимволы — рекомендуется путь только на латинице".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Символы в пути",
            level: DiagLevel::Ok,
            msg: "Путь содержит только стандартные латинские символы".into(),
        });
    }

    // 11. OneDrive sync folder
    let is_onedrive = if let Ok(od) = env::var("OneDrive") {
        !od.is_empty() && path_str.to_lowercase().starts_with(&od.to_lowercase())
    } else {
        false
    };
    if is_onedrive {
        items.push(DiagItem {
            name: "Папка OneDrive",
            level: DiagLevel::Bad,
            msg: "Каталог zapret находится в папке OneDrive (блокирует WinDivert драйвер)".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Папка OneDrive",
            level: DiagLevel::Ok,
            msg: "Каталог находится вне синхронизации облачных дисков".into(),
        });
    }

    // 12. WinDivert driver file
    let bin_dir = orig_dir.join("bin");
    let mut sys_found = false;
    if let Ok(entries) = fs::read_dir(&bin_dir) {
        for entry in entries.flatten() {
            if let Some(ext) = entry.path().extension() {
                if ext.to_string_lossy().eq_ignore_ascii_case("sys") {
                    sys_found = true;
                    break;
                }
            }
        }
    }
    if sys_found {
        items.push(DiagItem {
            name: "Файлы драйвера WinDivert",
            level: DiagLevel::Ok,
            msg: "Файл WinDivert*.sys присутствует в bin/".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Файлы драйвера WinDivert",
            level: DiagLevel::Bad,
            msg: "Файл драйвера .sys не найден в bin/".into(),
        });
    }

    // 13. VPN services
    let vpn1 = scm::query_named_service("wintun");
    let vpn2 = scm::query_named_service("wireguard");
    let vpn3 = scm::query_named_service("OpenVPNService");
    if vpn1 != ServiceState::NotInstalled || vpn2 != ServiceState::NotInstalled || vpn3 != ServiceState::NotInstalled {
        items.push(DiagItem {
            name: "VPN адаптеры",
            level: DiagLevel::Warn,
            msg: "Обнаружены службы VPN (Wintun/WireGuard/OpenVPN). При активном VPN zapret не требуется".into(),
        });
    } else {
        items.push(DiagItem {
            name: "VPN адаптеры",
            level: DiagLevel::Ok,
            msg: "Конфликтных служб VPN не обнаружено".into(),
        });
    }

    // 14. DoH (DNS over HTTPS)
    let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
    let doh_found = if let Ok(sub) = hklm.open_subkey("SYSTEM\\CurrentControlSet\\Services\\Dnscache\\Parameters") {
        let flags: u32 = sub.get_value("DohFlags").unwrap_or(0);
        flags > 0
    } else {
        false
    };
    if doh_found {
        items.push(DiagItem {
            name: "Secure DNS (DoH)",
            level: DiagLevel::Ok,
            msg: "Безопасный DNS over HTTPS включен в Windows".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Secure DNS (DoH)",
            level: DiagLevel::Warn,
            msg: "DoH не включен на уровне системы (рекомендуется включить шифрование DNS)".into(),
        });
    }

    // 15. Hosts file
    let windir = env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
    let hosts_path = Path::new(&windir).join("System32").join("drivers").join("etc").join("hosts");
    let hosts_item = if hosts_path.is_file() {
        if let Ok(hcontent) = fs::read_to_string(&hosts_path) {
            let lower = hcontent.to_lowercase();
            if lower.contains("youtube.com") || lower.contains("googlevideo.com") || lower.contains("discord.gg") {
                DiagItem {
                    name: "Файл hosts",
                    level: DiagLevel::Warn,
                    msg: "Файл hosts содержит записи YouTube/Discord, которые могут мешать обходу".into(),
                }
            } else {
                DiagItem {
                    name: "Файл hosts",
                    level: DiagLevel::Ok,
                    msg: "Файл hosts чист, блокирующих записей нет".into(),
                }
            }
        } else {
            DiagItem {
                name: "Файл hosts",
                level: DiagLevel::Ok,
                msg: "Файл hosts доступен".into(),
            }
        }
    } else {
        DiagItem {
            name: "Файл hosts",
            level: DiagLevel::Ok,
            msg: "Файл hosts стандартный".into(),
        }
    };
    items.push(hosts_item);

    // 16. WinDivert conflict
    let winws_running = process::is_process_running("winws.exe");
    let wd_running = scm::is_service_running("WinDivert") || scm::is_service_running("WinDivert14");
    if wd_running && !winws_running {
        items.push(DiagItem {
            name: "Конфликт WinDivert",
            level: DiagLevel::Bad,
            msg: "Служба WinDivert активна, но winws.exe не запущен (зависший драйвер)".into(),
        });
    } else {
        items.push(DiagItem {
            name: "Конфликт WinDivert",
            level: DiagLevel::Ok,
            msg: "Драйвер WinDivert согласован с процессом winws".into(),
        });
    }

    // 17. Conflicting bypass utilities
    let bypasses = ["goodbyedpi", "discordfix_zapret", "winws1", "winws2"];
    let mut found_bypasses = Vec::new();
    for b in bypasses {
        if scm::query_named_service(b) != ServiceState::NotInstalled {
            found_bypasses.push(b);
        }
    }
    if !found_bypasses.is_empty() {
        items.push(DiagItem {
            name: "Сторонние обходы DPI",
            level: DiagLevel::Bad,
            msg: format!("Обнаружены другие установленные службы: {}", found_bypasses.join(", ")),
        });
    } else {
        items.push(DiagItem {
            name: "Сторонние обходы DPI",
            level: DiagLevel::Ok,
            msg: "Конкурирующих служб обхода DPI не обнаружено".into(),
        });
    }

    // 18. Discord cache folders
    let mut discs = Vec::new();
    if let Ok(appdata) = env::var("APPDATA") {
        for name in &["discord", "discordptb", "discordcanary"] {
            let p = Path::new(&appdata).join(name);
            if p.is_dir() {
                discs.push(*name);
            }
        }
    }
    if !discs.is_empty() {
        items.push(DiagItem {
            name: "Кэш Discord",
            level: DiagLevel::Ok,
            msg: format!("Найдены папки клиентов: {}", discs.join(", ")),
        });
    } else {
        items.push(DiagItem {
            name: "Кэш Discord",
            level: DiagLevel::Ok,
            msg: "Клиенты Discord в APPDATA не найдены".into(),
        });
    }

    let ok_count = items.iter().filter(|i| i.level == DiagLevel::Ok).count();
    let warn_count = items.iter().filter(|i| i.level == DiagLevel::Warn).count();
    let bad_count = items.iter().filter(|i| i.level == DiagLevel::Bad).count();

    DiagReport {
        items,
        ok_count,
        warn_count,
        bad_count,
    }
}

pub fn remove_conflicts() -> Vec<String> {
    let mut logs = Vec::new();
    logs.push("Запущено устранение конфликтов...".into());

    // 1. Enable TCP timestamps
    let ts = Command::new("netsh")
        .args(["int", "tcp", "set", "global", "timestamps=enabled"])
        .output();
    if let Ok(out) = ts {
        if out.status.success() {
            logs.push("[+] Включение TCP Timestamps: успешно".into());
        } else {
            logs.push("[-] Не удалось включить TCP Timestamps".into());
        }
    }

    // 2. Stop and remove conflicting services
    for svc in &["WinDivert", "WinDivert14", "goodbyedpi", "discordfix_zapret", "winws1", "winws2"] {
        if scm::query_named_service(svc) != ServiceState::NotInstalled {
            match scm::delete_service_named(svc) {
                Ok(_) => logs.push(format!("[+] Удалена конфликтующая служба: {svc}")),
                Err(e) => logs.push(format!("[-] Ошибка удаления службы {svc}: {e}")),
            }
        }
    }

    logs.push("Устранение конфликтов завершено.".into());
    logs
}
