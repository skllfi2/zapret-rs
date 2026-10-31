use std::os::windows::process::CommandExt;
use std::process::Command;
use windows::Win32::UI::Shell::IsUserAnAdmin;
use winreg::enums::*;
use winreg::RegKey;

const CREATE_NO_WINDOW: u32 = 0x08000000;

#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct DohProviderInfo {
    pub key: &'static str,
    pub name: &'static str,
    pub ipv4: &'static [&'static str],
    pub template: &'static str,
    pub description: &'static str,
}

pub const PROVIDERS: &[DohProviderInfo] = &[
    DohProviderInfo {
        key: "cloudflare",
        name: "Cloudflare",
        ipv4: &["1.1.1.1", "1.0.0.1"],
        template: "https://cloudflare-dns.com/dns-query",
        description: "Быстрый глобальный DoH (1.1.1.1)",
    },
    DohProviderInfo {
        key: "google",
        name: "Google DNS",
        ipv4: &["8.8.8.8", "8.8.4.4"],
        template: "https://dns.google/dns-query",
        description: "Надёжный Google Public DNS (8.8.8.8)",
    },
    DohProviderInfo {
        key: "quad9",
        name: "Quad9",
        ipv4: &["9.9.9.9", "149.112.112.112"],
        template: "https://dns.quad9.net/dns-query",
        description: "Приватный Quad9 без логирования (9.9.9.9)",
    },
    DohProviderInfo {
        key: "adguard",
        name: "AdGuard DNS",
        ipv4: &["94.140.14.14", "94.140.15.15"],
        template: "https://dns.adguard-dns.com/dns-query",
        description: "Фильтрация рекламы и трекеров (94.140.14.14)",
    },
];

#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct DohStatus {
    pub enabled: bool,
    pub provider: String,
    pub provider_name: String,
    pub servers: Vec<String>,
    pub adapters: Vec<String>,
    pub autodoh: bool,
}

fn run_silent_cmd(cmd: &str, args: &[&str]) -> (bool, String) {
    match Command::new(cmd).args(args).creation_flags(CREATE_NO_WINDOW).output() {
        Ok(out) => {
            let s = String::from_utf8_lossy(&out.stdout).to_string()
                + &String::from_utf8_lossy(&out.stderr);
            (out.status.success(), s.trim().to_string())
        }
        Err(e) => (false, e.to_string()),
    }
}

pub fn get_active_adapter_names() -> Vec<String> {
    let script = "(Get-NetAdapter | Where-Object Status -eq 'Up').InterfaceAlias";
    let (ok, out) = run_silent_cmd(
        "powershell",
        &["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
    );
    if ok && !out.is_empty() {
        out.lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect()
    } else {
        vec!["Ethernet".to_string()]
    }
}

pub fn get_doh_status() -> DohStatus {
    let adapters = get_active_adapter_names();
    if adapters.is_empty() {
        return DohStatus {
            enabled: false,
            provider: "disabled".into(),
            provider_name: "Нет адаптеров".into(),
            servers: vec![],
            adapters: vec![],
            autodoh: false,
        };
    }

    let first = adapters[0].replace('\'', "''");
    let ps = format!(
        "(Get-DnsClientServerAddress -InterfaceAlias '{first}' -AddressFamily IPv4).ServerAddresses -join ','"
    );
    let (ok, dns_out) = run_silent_cmd(
        "powershell",
        &["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", &ps],
    );
    let servers: Vec<String> = if ok {
        dns_out
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect()
    } else {
        vec![]
    };

    let mut autodoh = false;
    let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
    if let Ok(k) = hklm.open_subkey_with_flags(
        r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters",
        KEY_READ,
    ) {
        if let Ok(val) = k.get_value::<u32, _>("EnableAutoDoh") {
            autodoh = val == 1 || val == 2;
        }
    }

    let mut detected_provider = "disabled".to_string();
    let mut provider_name = "Отключен (DHCP)".to_string();

    if !servers.is_empty() {
        let mut matched = false;
        for p in PROVIDERS {
            if servers.iter().any(|s| p.ipv4.contains(&s.as_str())) {
                detected_provider = p.key.to_string();
                provider_name = format!("{} ({})", p.name, servers[0]);
                matched = true;
                break;
            }
        }
        if !matched {
            detected_provider = "custom".to_string();
            provider_name = format!("Кастомный ({})", servers.join(", "));
        }
    }

    let enabled = detected_provider != "disabled";

    DohStatus {
        enabled,
        provider: detected_provider,
        provider_name,
        servers,
        adapters,
        autodoh,
    }
}

pub fn set_doh(provider_key: &str) -> Result<String, String> {
    let is_admin = unsafe { IsUserAnAdmin().as_bool() };
    if !is_admin {
        return Err("Для настройки DoH требуются права администратора (UAC).".into());
    }

    let info = PROVIDERS
        .iter()
        .find(|p| p.key.eq_ignore_ascii_case(provider_key))
        .ok_or_else(|| format!("Неизвестный провайдер DoH: {provider_key}"))?;

    let adapters = get_active_adapter_names();
    let srv_list = format!("@('{}')", info.ipv4.join("','"));

    for ad in &adapters {
        let clean_ad = ad.replace('\'', "''");
        let ps = format!("Set-DnsClientServerAddress -InterfaceAlias '{clean_ad}' -ServerAddresses {srv_list}");
        let (ok, err) = run_silent_cmd(
            "powershell",
            &["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", &ps],
        );
        if !ok {
            return Err(format!("Не удалось применить DNS к '{ad}': {err}"));
        }
    }

    for srv in info.ipv4 {
        let _ = run_silent_cmd(
            "netsh",
            &[
                "dns",
                "add",
                "encryption",
                &format!("server={srv}"),
                &format!("dohtemplate={}", info.template),
                "autoupgrade=yes",
                "udpfallback=yes",
            ],
        );
    }

    let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
    if let Ok((k, _)) = hklm.create_subkey(r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters") {
        let _ = k.set_value("EnableAutoDoh", &2u32);
    }

    let _ = run_silent_cmd("ipconfig", &["/flushdns"]);

    Ok(format!(
        "DoH ({}) успешно настроен для адаптеров: {}.",
        info.name,
        adapters.join(", ")
    ))
}

pub fn disable_doh() -> Result<String, String> {
    let is_admin = unsafe { IsUserAnAdmin().as_bool() };
    if !is_admin {
        return Err("Для сброса DoH требуются права администратора (UAC).".into());
    }

    let adapters = get_active_adapter_names();
    for ad in &adapters {
        let clean_ad = ad.replace('\'', "''");
        let ps = format!("Set-DnsClientServerAddress -InterfaceAlias '{clean_ad}' -ResetServerAddresses");
        let _ = run_silent_cmd(
            "powershell",
            &["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", &ps],
        );
    }

    let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);
    if let Ok(k) = hklm.open_subkey_with_flags(
        r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters",
        KEY_SET_VALUE,
    ) {
        let _ = k.delete_value("EnableAutoDoh");
    }

    let _ = run_silent_cmd("ipconfig", &["/flushdns"]);

    Ok(format!(
        "DoH отключен. Восстановлено получение DNS по DHCP для: {}.",
        adapters.join(", ")
    ))
}

/// Циклическое переключение DoH: Cloudflare -> Google -> Quad9 -> AdGuard -> Отключить -> Cloudflare
pub fn cycle_doh() -> Result<String, String> {
    let cur = get_doh_status();
    let next_provider = match cur.provider.as_str() {
        "cloudflare" => Some("google"),
        "google" => Some("quad9"),
        "quad9" => Some("adguard"),
        "adguard" => None, // disable
        _ => Some("cloudflare"),
    };

    if let Some(target) = next_provider {
        set_doh(target)
    } else {
        disable_doh()
    }
}
