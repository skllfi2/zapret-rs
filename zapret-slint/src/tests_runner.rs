use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use crate::process;
use crate::strategies;

#[allow(dead_code)]
#[derive(Clone, Debug, Default)]
pub struct TargetResult {
    pub name: String,
    pub http_tokens: Vec<String>,
    pub ping_str: String,
    pub is_url: bool,
}

#[derive(Clone, Debug, Default)]
pub struct StrategyBenchmarkResult {
    pub config_name: String,
    pub http_ok: usize,
    pub http_err: usize,
    pub http_unsup: usize,
    pub ping_ok: usize,
    pub ping_fail: usize,
    pub targets: Vec<TargetResult>,
}

pub struct BenchmarkProgress {
    pub current_index: usize,
    pub total_count: usize,
    pub current_strategy: String,
    pub current_target: String,
    pub log_lines: Vec<String>,
    pub best_strategy: Option<String>,
}

#[derive(Clone, Debug)]
pub struct TargetItem {
    pub name: String,
    pub url: Option<String>,
    pub ping_target: Option<String>,
}

/// Загружает список целей из `utils/targets.txt` или возвращает дефолтный эталонный набор
pub fn load_targets(orig_dir: &Path) -> Vec<TargetItem> {
    let targets_file = orig_dir.join("utils").join("targets.txt");
    let mut items = Vec::new();

    if targets_file.is_file() {
        if let Ok(content) = fs::read_to_string(&targets_file) {
            for line in content.lines() {
                let trimmed = line.trim();
                if trimmed.starts_with('#') || trimmed.is_empty() {
                    continue;
                }
                if let Some((k, v)) = trimmed.split_once('=') {
                    let key = k.trim().to_string();
                    let val = v.trim().trim_matches('"').trim();
                    if let Some(ip) = val.strip_prefix("PING:") {
                        items.push(TargetItem {
                            name: key,
                            url: None,
                            ping_target: Some(ip.trim().to_string()),
                        });
                    } else if val.starts_with("http://") || val.starts_with("https://") {
                        let ping_host = val
                            .trim_start_matches("https://")
                            .trim_start_matches("http://")
                            .split('/')
                            .next()
                            .unwrap_or("")
                            .to_string();
                        items.push(TargetItem {
                            name: key,
                            url: Some(val.to_string()),
                            ping_target: if ping_host.is_empty() { None } else { Some(ping_host) },
                        });
                    }
                }
            }
        }
    }

    if items.is_empty() {
        // Fallback цели
        items = vec![
            TargetItem { name: "DiscordMain".into(), url: Some("https://discord.com".into()), ping_target: Some("discord.com".into()) },
            TargetItem { name: "DiscordGateway".into(), url: Some("https://gateway.discord.gg".into()), ping_target: Some("gateway.discord.gg".into()) },
            TargetItem { name: "DiscordCDN".into(), url: Some("https://cdn.discordapp.com".into()), ping_target: Some("cdn.discordapp.com".into()) },
            TargetItem { name: "DiscordUpdates".into(), url: Some("https://updates.discord.com".into()), ping_target: Some("updates.discord.com".into()) },
            TargetItem { name: "YouTubeWeb".into(), url: Some("https://www.youtube.com".into()), ping_target: Some("www.youtube.com".into()) },
            TargetItem { name: "YouTubeShort".into(), url: Some("https://youtu.be".into()), ping_target: Some("youtu.be".into()) },
            TargetItem { name: "YouTubeImage".into(), url: Some("https://i.ytimg.com".into()), ping_target: Some("i.ytimg.com".into()) },
            TargetItem { name: "YouTubeVideoRedirect".into(), url: Some("https://redirector.googlevideo.com".into()), ping_target: Some("redirector.googlevideo.com".into()) },
            TargetItem { name: "GoogleMain".into(), url: Some("https://www.google.com".into()), ping_target: Some("www.google.com".into()) },
            TargetItem { name: "GoogleGstatic".into(), url: Some("https://www.gstatic.com".into()), ping_target: Some("www.gstatic.com".into()) },
            TargetItem { name: "CloudflareWeb".into(), url: Some("https://www.cloudflare.com".into()), ping_target: Some("www.cloudflare.com".into()) },
            TargetItem { name: "CloudflareCDN".into(), url: Some("https://cdnjs.cloudflare.com".into()), ping_target: Some("cdnjs.cloudflare.com".into()) },
            TargetItem { name: "CloudflareDNS1111".into(), url: None, ping_target: Some("1.1.1.1".into()) },
            TargetItem { name: "CloudflareDNS1001".into(), url: None, ping_target: Some("1.0.0.1".into()) },
            TargetItem { name: "GoogleDNS8888".into(), url: None, ping_target: Some("8.8.8.8".into()) },
            TargetItem { name: "GoogleDNS8844".into(), url: None, ping_target: Some("8.8.4.4".into()) },
        ];
    }

    items
}

/// Выполняет проверку HTTP/TLS через системный curl.exe в точности как в test zapret.ps1
fn check_curl_protocol(url: &str, extra_args: &[&str], timeout_sec: u32) -> String {
    let timeout_str = timeout_sec.to_string();
    let mut args = vec![
        "-I",
        "-s",
        "-m", &timeout_str,
        "--connect-timeout", "2",
        "-o", "NUL",
        "-w", "%{http_code}",
        "--show-error",
    ];
    args.extend_from_slice(extra_args);
    args.push(url);

    let output = Command::new("curl.exe")
        .args(&args)
        .creation_flags(0x08000000)
        .output();

    if let Ok(out) = output {
        let stderr = String::from_utf8_lossy(&out.stderr).to_lowercase();
        if stderr.contains("could not resolve host")
            || stderr.contains("ssl certificate problem")
            || stderr.contains("self-signed")
            || stderr.contains("certificate verify failed")
            || stderr.contains("unable to get local issuer certificate")
        {
            return "SSL".to_string();
        }
        if out.status.code() == Some(35)
            || stderr.contains("does not support")
            || stderr.contains("not supported")
            || stderr.contains("unsupported protocol")
            || stderr.contains("unrecognized option")
            || stderr.contains("unknown option")
            || stderr.contains("unsupported option")
            || stderr.contains("unsupported feature")
        {
            return "UNSUP".to_string();
        }
        if out.status.success() {
            return "OK".to_string();
        }
    }
    "ERROR".to_string()
}

/// Измеряет пинг через ping.exe
fn check_ping(host: &str) -> (bool, String) {
    let start = Instant::now();
    let status = Command::new("ping.exe")
        .args(["-n", "1", "-w", "800", host])
        .creation_flags(0x08000000)
        .output();

    if let Ok(out) = status {
        if out.status.success() {
            let elapsed = start.elapsed().as_millis();
            return (true, format!("{elapsed} ms"));
        }
    }
    (false, "Timeout".to_string())
}

struct SingleTargetReport {
    http_ok: usize,
    http_err: usize,
    http_unsup: usize,
    ping_ok: bool,
    ping_str: String,
    http_tokens: Vec<String>,
    log_entry: String,
}

/// Выполняет параллельную проверку всех протоколов (HTTP, TLS1.2, TLS1.3, Ping) для одной цели
fn test_target_protocols(target: &TargetItem) -> SingleTargetReport {
    let (h_res, tls12_res, tls13_res, ping_res) = std::thread::scope(|s| {
        let h_handle = if let Some(ref url) = target.url {
            let u = url.clone();
            Some(s.spawn(move || check_curl_protocol(&u, &["--http1.1"], 2)))
        } else {
            None
        };

        let t12_handle = if let Some(ref url) = target.url {
            let u = url.clone();
            Some(s.spawn(move || check_curl_protocol(&u, &["--tlsv1.2", "--tls-max", "1.2"], 2)))
        } else {
            None
        };

        let t13_handle = if let Some(ref url) = target.url {
            let u = url.clone();
            Some(s.spawn(move || check_curl_protocol(&u, &["--tlsv1.3", "--tls-max", "1.3"], 2)))
        } else {
            None
        };

        let ping_handle = if let Some(ref ping_host) = target.ping_target {
            let h = ping_host.clone();
            Some(s.spawn(move || check_ping(&h)))
        } else {
            None
        };

        let h = h_handle.map(|h| h.join().unwrap_or_default()).unwrap_or_default();
        let t12 = t12_handle.map(|h| h.join().unwrap_or_default()).unwrap_or_default();
        let t13 = t13_handle.map(|h| h.join().unwrap_or_default()).unwrap_or_default();
        let p = ping_handle.map(|h| h.join().unwrap_or_else(|_| (false, "Timeout".into()))).unwrap_or((false, "n/a".into()));

        (h, t12, t13, p)
    });

    let mut http_ok = 0;
    let mut http_err = 0;
    let mut http_unsup = 0;
    let mut http_tokens = Vec::new();

    if target.url.is_some() {
        for r in [&h_res, &tls12_res, &tls13_res] {
            if r == "OK" {
                http_ok += 1;
            } else if r == "UNSUP" {
                http_unsup += 1;
            } else {
                http_err += 1;
            }
        }
        http_tokens.push(format!("HTTP:{:<4}", h_res));
        http_tokens.push(format!("TLS1.2:{:<4}", tls12_res));
        http_tokens.push(format!("TLS1.3:{:<4}", tls13_res));
    }

    let log_entry = if target.url.is_some() {
        format!(
            "  {:<22} : {} | Ping: {}",
            target.name,
            http_tokens.join("    "),
            ping_res.1
        )
    } else {
        format!("  {:<22} :  | Ping: {}", target.name, ping_res.1)
    };

    SingleTargetReport {
        http_ok,
        http_err,
        http_unsup,
        ping_ok: ping_res.0,
        ping_str: ping_res.1,
        http_tokens,
        log_entry,
    }
}

/// Выполняет оригинальный 1:1 прогон тестов zapret
pub fn run_full_benchmark<F>(
    orig_dir: &Path,
    strategies_to_test: Vec<String>,
    cancel_flag: Arc<AtomicBool>,
    mut on_progress: F,
) -> (Vec<StrategyBenchmarkResult>, Option<String>, Option<PathBuf>)
where
    F: FnMut(BenchmarkProgress),
{
    let winws_exe = orig_dir.join("bin").join("winws.exe");
    let targets = load_targets(orig_dir);
    let total_configs = strategies_to_test.len();
    let mut all_results: Vec<StrategyBenchmarkResult> = Vec::new();
    let mut log_lines: Vec<String> = Vec::new();

    log_lines.push(format!("============================================================"));
    log_lines.push(format!("                 ZAPRET CONFIG TESTS (NATIVE)"));
    log_lines.push(format!("                 Total configs: {:>2}", total_configs));
    log_lines.push(format!("============================================================"));

    for (c_idx, strat) in strategies_to_test.iter().enumerate() {
        if cancel_flag.load(Ordering::Relaxed) {
            break;
        }

        let config_header = format!("Config: {strat}.bat (Type: standard)");
        log_lines.push(String::new());
        log_lines.push(config_header.clone());

        on_progress(BenchmarkProgress {
            current_index: c_idx + 1,
            total_count: total_configs,
            current_strategy: strat.clone(),
            current_target: "Запуск WinWS...".to_string(),
            log_lines: log_lines.clone(),
            best_strategy: None,
        });

        // 1. Очистка и запуск WinWS
        let _ = process::kill_process("winws.exe");
        std::thread::sleep(Duration::from_millis(150));

        let args = match strategies::parse_strategy_args(orig_dir, strat) {
            Ok(a) => a,
            Err(_) => continue,
        };

        let mut child = match Command::new(&winws_exe)
            .raw_arg(&args)
            .creation_flags(0x08000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        {
            Ok(c) => c,
            Err(_) => continue,
        };

        // Ожидание готовности winws и инициализации драйвера WinDivert (1200 мс)
        std::thread::sleep(Duration::from_millis(1200));

        let mut current_strat_res = StrategyBenchmarkResult {
            config_name: format!("{strat}.bat"),
            http_ok: 0,
            http_err: 0,
            http_unsup: 0,
            ping_ok: 0,
            ping_fail: 0,
            targets: Vec::new(),
        };

        // 2. Проверка всех целей из targets.txt (быстрый параллельный опрос протоколов)
        for target in &targets {
            if cancel_flag.load(Ordering::Relaxed) {
                break;
            }

            on_progress(BenchmarkProgress {
                current_index: c_idx + 1,
                total_count: total_configs,
                current_strategy: strat.clone(),
                current_target: format!("Проверка {}", target.name),
                log_lines: log_lines.clone(),
                best_strategy: None,
            });

            let rep = test_target_protocols(target);
            current_strat_res.http_ok += rep.http_ok;
            current_strat_res.http_err += rep.http_err;
            current_strat_res.http_unsup += rep.http_unsup;
            if rep.ping_ok {
                current_strat_res.ping_ok += 1;
            } else if target.ping_target.is_some() {
                current_strat_res.ping_fail += 1;
            }

            log_lines.push(rep.log_entry);

            current_strat_res.targets.push(TargetResult {
                name: target.name.clone(),
                http_tokens: rep.http_tokens,
                ping_str: rep.ping_str,
                is_url: target.url.is_some(),
            });
        }

        // 3. Завершаем WinWS
        let _ = child.kill();
        let _ = child.wait();
        let _ = process::kill_process("winws.exe");
        std::thread::sleep(Duration::from_millis(150));

        all_results.push(current_strat_res);
    }

    // 4. Формируем раздел ANALYTICS (в точности как в оригинале)
    log_lines.push(String::new());
    log_lines.push("=== ANALYTICS ===".to_string());

    // Сортируем: сначала больше всего HTTP OK, затем Ping OK
    all_results.sort_by(|a, b| {
        b.http_ok
            .cmp(&a.http_ok)
            .then_with(|| b.ping_ok.cmp(&a.ping_ok))
    });

    for r in &all_results {
        log_lines.push(format!(
            "{:<32} : HTTP OK: {:>3}, ERR: {:>3}, UNSUP: {:>3}, Ping OK: {:>3}, Fail: {:>3}",
            r.config_name, r.http_ok, r.http_err, r.http_unsup, r.ping_ok, r.ping_fail
        ));
    }

    let best_config = all_results.first().map(|r| r.config_name.clone());
    if let Some(ref best) = best_config {
        log_lines.push(format!("Best strategy: {}", best));
    }

    // 5. Сохраняем полный отчёт в `utils/test results/test_results_YYYY-MM-DD_HH-mm-ss.txt`
    let date_str = chrono_timestamp_filename();
    let results_dir = orig_dir.join("utils").join("test results");
    let _ = fs::create_dir_all(&results_dir);
    let report_file = results_dir.join(format!("test_results_{}.txt", date_str));

    let joined_report = log_lines.join("\r\n");
    let _ = fs::write(&report_file, &joined_report);

    // Уведомление о финале
    let clean_best_name = best_config
        .as_ref()
        .map(|s| s.strip_suffix(".bat").unwrap_or(s).to_string());

    on_progress(BenchmarkProgress {
        current_index: total_configs,
        total_count: total_configs,
        current_strategy: "Тестирование завершено".to_string(),
        current_target: format!("Отчёт сохранён: {}", report_file.file_name().unwrap_or_default().to_string_lossy()),
        log_lines: log_lines.clone(),
        best_strategy: clean_best_name.clone(),
    });

    (all_results, clean_best_name, Some(report_file))
}

fn chrono_timestamp_filename() -> String {
    let output = Command::new("powershell.exe")
        .args(["-NoProfile", "-Command", "Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'"])
        .output();
    if let Ok(out) = output {
        let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if !s.is_empty() {
            return s;
        }
    }
    "latest".to_string()
}

trait CommandExt {
    fn creation_flags(&mut self, flags: u32) -> &mut Self;
    fn raw_arg(&mut self, arg: &str) -> &mut Self;
}

impl CommandExt for Command {
    fn creation_flags(&mut self, flags: u32) -> &mut Self {
        use std::os::windows::process::CommandExt;
        CommandExt::creation_flags(self, flags)
    }

    fn raw_arg(&mut self, arg: &str) -> &mut Self {
        use std::os::windows::process::CommandExt;
        CommandExt::raw_arg(self, arg)
    }
}
