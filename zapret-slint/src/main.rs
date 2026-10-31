#![windows_subsystem = "windows"]

slint::include_modules!();

mod autostart;
mod diagnostics;
mod doh;
mod fakes;
mod paths;
mod process;
mod scm;
mod settings;
mod sound;
mod strategies;
mod updates;

use paths::ZapretPaths;
use scm::ServiceState;
use slint::{Color, Model, ModelRc, VecModel};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;
use windows::core::w;
use windows::Win32::Foundation::CloseHandle;
use windows::Win32::System::Threading::CreateMutexW;
use windows::Win32::UI::Shell::IsUserAnAdmin;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 1. Single instance mutex (Local\zapret-slint-ui)
    unsafe {
        let handle = CreateMutexW(None, false, w!("Local\\zapret-slint-ui"));
        if let Ok(h) = handle {
            if windows::Win32::Foundation::GetLastError().0 == 183 {
                // ERROR_ALREADY_EXISTS
                let _ = CloseHandle(h);
                eprintln!("zapret-simple уже запущено.");
                return Ok(());
            }
        }
    }

    let main_window = MainWindow::new()?;

    // 2. Admin rights check
    let is_admin = unsafe { IsUserAnAdmin().as_bool() };
    if is_admin {
        main_window.set_admin_status("Администратор".into());
        main_window.set_admin_color(Color::from_rgb_u8(34, 197, 94));
    } else {
        main_window.set_admin_status("Без прав админа".into());
        main_window.set_admin_color(Color::from_rgb_u8(245, 158, 11));
    }

    // 3. Paths detection
    let zapret_opt = ZapretPaths::detect();
    let version = if let Some(ref z) = zapret_opt {
        z.local_version()
    } else {
        "v(не найден)".to_string()
    };
    main_window.set_zapret_version(version.clone().into());

    // 4. Initial Settings values
    if let Some(ref z) = zapret_opt {
        let gf = settings::read_game_filter(&z.orig_dir);
        main_window.set_game_filter_text(gf.as_label().into());

        let ipset = settings::read_ipset_status(&z.orig_dir);
        main_window.set_ipset_active(ipset);
        main_window.set_ipset_text(if ipset { "Загружен".into() } else { "Отключен".into() });

        let chk = settings::read_check_updates_flag(&z.orig_dir);
        main_window.set_check_updates_text(if chk { "Включена".into() } else { "Отключена".into() });
    }

    // Sound setting
    let sound_on = sound::is_sound_enabled();
    main_window.set_sound_enabled(sound_on);

    // Initial DoH status
    let doh_stat = doh::get_doh_status();
    main_window.set_doh_active(doh_stat.enabled);
    main_window.set_doh_provider_text(doh_stat.provider_name.into());

    // Initial Autostart status
    let auto_on = autostart::is_autostart_enabled();
    main_window.set_autostart_active(auto_on);
    main_window.set_autostart_text(if auto_on { "Включена".into() } else { "Отключена".into() });

    // 5. Load strategies
    let (strats, current_strat) = if let Some(ref z) = zapret_opt {
        let list = strategies::list_strategies(&z.orig_dir);
        let cur = strategies::current_strategy().unwrap_or_else(|| {
            if list.contains(&"general".to_string()) {
                "general".to_string()
            } else {
                list.first().cloned().unwrap_or_default()
            }
        });
        (list, cur)
    } else {
        (vec![], "".to_string())
    };

    let idx = strats.iter().position(|s| s == &current_strat).unwrap_or(0);
    let slint_strats: Vec<slint::SharedString> = strats.iter().map(|s| s.into()).collect();
    main_window.set_strategies(ModelRc::new(VecModel::from(slint_strats)));
    main_window.set_selected_strategy_index(idx as i32);

    // Initial status update
    update_ui_status(&main_window);

    // Initial log message
    let init_log = if let Some(ref z) = zapret_opt {
        format!(
            "Zapret Simple (Native Rust + Slint) готов к работе.\nКаталог zapret: {}\nВерсия: {}\nПрава: {}\n----------------------------------------------------\n",
            z.orig_dir.display(),
            version,
            if is_admin { "Администратор" } else { "Пользователь (нужен UAC для служб)" }
        )
    } else {
        "ВНИМАНИЕ: Каталог zapret не найден! Поместите zapret в ./zapret/ или задайте ZAPRET_DIR.\n".to_string()
    };
    main_window.set_log_output(init_log.into());

    // ===== Callbacks =====

    // Toggle service (Start / Stop)
    let mw_weak = main_window.as_weak();
    main_window.on_toggle_service(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let running = mw.get_is_running();
        if running {
            match scm::stop_service() {
                Ok(_) => {
                    sound::play_sound("disconnect");
                    append_log(&mw, "Служба zapret успешно остановлена.\n");
                }
                Err(e) => {
                    sound::play_sound("alert");
                    append_log(&mw, &format!("Ошибка остановки службы: {e}\n"));
                }
            }
        } else {
            match scm::start_service() {
                Ok(_) => {
                    sound::play_sound("connect");
                    append_log(&mw, "Служба zapret успешно запущена.\n");
                }
                Err(e) => {
                    sound::play_sound("alert");
                    append_log(&mw, &format!("Ошибка запуска службы: {e}\n"));
                }
            }
        }
        update_ui_status(&mw);
    });

    // Remove service
    let mw_weak = main_window.as_weak();
    main_window.on_remove_service(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        match scm::delete_service_named("zapret") {
            Ok(_) => {
                sound::play_sound("disconnect");
                append_log(&mw, "[+] Служба zapret удалена из Windows SCM.\n");
            }
            Err(e) => {
                sound::play_sound("alert");
                append_log(&mw, &format!("[-] Ошибка удаления службы: {e}\n"));
            }
        }
        update_ui_status(&mw);
    });

    // Detailed service status
    let mw_weak = main_window.as_weak();
    main_window.on_service_status_details(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let svc_state = scm::query_service_status();
        let winws_running = process::is_process_running("winws.exe");
        let active_strat = strategies::current_strategy().unwrap_or_else(|| "Не выбрана".into());

        append_log(&mw, &format!(
            "\n=== СТАТУС СЛУЖБЫ ZAPRET ===\nСостояние в Windows SCM : {}\nПроцесс winws.exe       : {}\nТекущая стратегия       : {}\nИмя службы в реестре    : zapret\n============================\n\n",
            svc_state.as_str(),
            if winws_running { "Запущен (Running)" } else { "Не запущен (Stopped)" },
            active_strat
        ));
    });

    // Apply strategy
    let mw_weak = main_window.as_weak();
    main_window.on_apply_strategy(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let idx = mw.get_selected_strategy_index() as usize;
        let model = mw.get_strategies();
        if let Some(strat_name) = model.row_data(idx) {
            let _ = strategies::save_current_strategy(&strat_name);
            append_log(&mw, &format!("Стратегия сохранена: {strat_name}\nПерезапуск службы...\n"));
            let _ = scm::stop_service();
            thread::sleep(Duration::from_millis(500));
            match scm::start_service() {
                Ok(_) => {
                    sound::play_sound("connect");
                    append_log(&mw, &format!("Стратегия {strat_name} успешно применилась к службе.\n"));
                }
                Err(e) => {
                    sound::play_sound("alert");
                    append_log(&mw, &format!("Ошибка запуска службы: {e}\n"));
                }
            }
            update_ui_status(&mw);
        }
    });

    // Toggle GameFilter
    let mw_weak = main_window.as_weak();
    main_window.on_toggle_game_filter(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            match settings::cycle_game_filter(&z.orig_dir) {
                Ok(new_mode) => {
                    mw.set_game_filter_text(new_mode.as_label().into());
                    append_log(&mw, &format!("GameFilter переключен в режим: {}\n", new_mode.as_label()));
                }
                Err(e) => append_log(&mw, &format!("Ошибка переключения GameFilter: {e}\n")),
            }
        }
    });

    // Toggle IPSet
    let mw_weak = main_window.as_weak();
    main_window.on_toggle_ipset(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            match settings::toggle_ipset(&z.orig_dir) {
                Ok(active) => {
                    mw.set_ipset_active(active);
                    mw.set_ipset_text(if active { "Загружен".into() } else { "Отключен".into() });
                    append_log(&mw, &format!("IPSet фильтр: {}\n", if active { "Включен (ipset-all.txt)" } else { "Отключен" }));
                }
                Err(e) => append_log(&mw, &format!("Ошибка переключения IPSet: {e}\n")),
            }
        }
    });

    // Toggle check updates
    let mw_weak = main_window.as_weak();
    main_window.on_toggle_check_updates(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            match settings::toggle_check_updates(&z.orig_dir) {
                Ok(enabled) => {
                    mw.set_check_updates_text(if enabled { "Включена".into() } else { "Отключена".into() });
                    append_log(&mw, &format!("Автопроверка обновлений: {}\n", if enabled { "Включена" } else { "Отключена" }));
                }
                Err(e) => append_log(&mw, &format!("Ошибка переключения флага: {e}\n")),
            }
        }
    });

    // Inspect fakes
    let mw_weak = main_window.as_weak();
    main_window.on_inspect_fakes(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            let info = fakes::format_fakes_info(&z.orig_dir);
            append_log(&mw, &info);
        }
    });

    // Update IPSet from GitHub
    let mw_weak = main_window.as_weak();
    main_window.on_update_ipset(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            append_log(&mw, "Загрузка ipset-service.txt с репозитория Flowseal...\n");
            match updates::update_ipset(&z.orig_dir) {
                Ok(msg) => {
                    sound::play_sound("done");
                    append_log(&mw, &format!("[+] {msg}\n"));
                    mw.set_ipset_active(true);
                    mw.set_ipset_text("Загружен".into());
                }
                Err(e) => {
                    sound::play_sound("alert");
                    append_log(&mw, &format!("[-] {e}\n"));
                }
            }
        }
    });

    // Check hosts
    let mw_weak = main_window.as_weak();
    main_window.on_check_hosts(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let res = updates::check_hosts_file();
        append_log(&mw, &format!("Проверка hosts:\n{res}\n"));
    });

    // Check updates
    let mw_weak = main_window.as_weak();
    let ver_clone = version.clone();
    main_window.on_check_updates(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Проверка обновлений на GitHub...\n");
        match updates::check_zapret_updates(&ver_clone) {
            Ok(msg) => append_log(&mw, &format!("{msg}\n")),
            Err(e) => append_log(&mw, &format!("[-] {e}\n")),
        }
    });

    // Full 18-step diagnostics!
    let mw_weak = main_window.as_weak();
    main_window.on_run_diagnostics(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Запуск комплексной диагностики системы (18 проверок)...\n");
        if let Some(z) = ZapretPaths::detect() {
            let report = diagnostics::run_full_diagnostics(&z.orig_dir);
            append_log(&mw, &report.format_text());
            sound::play_sound("done");
        } else {
            sound::play_sound("alert");
            append_log(&mw, "[-] Каталог zapret не найден для выполнения диагностики!\n");
        }
    });

    // Toggle Sound
    let mw_weak = main_window.as_weak();
    main_window.on_toggle_sound(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let enabled = sound::toggle_sound();
        mw.set_sound_enabled(enabled);
        if enabled {
            sound::play_sound("connect");
            append_log(&mw, "Звуковые уведомления включены (🔊).\n");
        } else {
            append_log(&mw, "Звуковые уведомления отключены (🔇).\n");
        }
    });

    // Toggle DoH
    let mw_weak = main_window.as_weak();
    main_window.on_toggle_doh(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Переключение конфигурации DNS over HTTPS (DoH)...\n");
        match doh::cycle_doh() {
            Ok(msg) => {
                sound::play_sound("done");
                append_log(&mw, &format!("[+] {msg}\n"));
                let st = doh::get_doh_status();
                mw.set_doh_active(st.enabled);
                mw.set_doh_provider_text(st.provider_name.into());
            }
            Err(e) => {
                sound::play_sound("alert");
                append_log(&mw, &format!("[-] Ошибка настройки DoH: {e}\n"));
            }
        }
    });

    // Toggle Autostart with Windows
    let mw_weak = main_window.as_weak();
    main_window.on_toggle_autostart(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        match autostart::toggle_autostart() {
            Ok(enabled) => {
                sound::play_sound("done");
                mw.set_autostart_active(enabled);
                mw.set_autostart_text(if enabled { "Включена".into() } else { "Отключена".into() });
                append_log(&mw, &format!("[+] Автозагрузка с Windows: {}\n", if enabled { "Включена" } else { "Отключена" }));
            }
            Err(e) => {
                sound::play_sound("alert");
                append_log(&mw, &format!("[-] Ошибка настройки автозагрузки: {e}\n"));
            }
        }
    });

    // Select zapret folder
    let mw_weak = main_window.as_weak();
    main_window.on_select_zapret_folder(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Открытие диалога выбора папки zapret...\n");
        let script = r#"
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.FolderBrowserDialog
$f.Description = 'Выберите каталог zapret (содержащий bin/winws.exe)'
if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $f.SelectedPath
}
"#;
        let out = std::process::Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script])
            .output();
        if let Ok(res) = out {
            let path_str = String::from_utf8_lossy(&res.stdout).trim().to_string();
            if !path_str.is_empty() {
                let p = std::path::Path::new(&path_str);
                match paths::save_custom_zapret_dir(p) {
                    Ok(_) => {
                        sound::play_sound("done");
                        append_log(&mw, &format!("[+] Каталог zapret установлен: {path_str}\n"));
                    }
                    Err(e) => {
                        sound::play_sound("alert");
                        append_log(&mw, &format!("[-] Ошибка: {e}\n"));
                    }
                }
            }
        }
    });

    // Unpack zapret.zip
    let mw_weak = main_window.as_weak();
    main_window.on_unpack_zapret_zip(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Открытие диалога выбора архива zapret.zip...\n");
        let script = r#"
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Filter = 'Архивы ZIP (*.zip)|*.zip|Все файлы (*.*)|*.*'
$f.Title = 'Выберите архив zapret.zip'
if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $f.FileName
}
"#;
        let out = std::process::Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script])
            .output();
        if let Ok(res) = out {
            let zip_str = String::from_utf8_lossy(&res.stdout).trim().to_string();
            if !zip_str.is_empty() {
                append_log(&mw, &format!("Распаковка архива: {zip_str}...\n"));
                match paths::unpack_zapret_zip(std::path::Path::new(&zip_str), None) {
                    Ok(dest) => {
                        sound::play_sound("done");
                        append_log(&mw, &format!("[+] zapret успешно распакован в: {}\n", dest.display()));
                    }
                    Err(e) => {
                        sound::play_sound("alert");
                        append_log(&mw, &format!("[-] Ошибка распаковки: {e}\n"));
                    }
                }
            }
        }
    });

    // Run tests (test zapret.ps1)
    let mw_weak = main_window.as_weak();
    main_window.on_run_tests(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Запуск utils\\test zapret.ps1 в отдельном окне...\n");
        if let Some(z) = ZapretPaths::detect() {
            let ps1 = z.orig_dir.join("utils").join("test zapret.ps1");
            if ps1.is_file() {
                let _ = std::process::Command::new("powershell.exe")
                    .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1.to_str().unwrap()])
                    .current_dir(&z.orig_dir)
                    .spawn();
            } else {
                append_log(&mw, "[-] test zapret.ps1 не найден.\n");
            }
        }
    });

    // Clear discord
    let mw_weak = main_window.as_weak();
    main_window.on_clear_discord(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Очистка кэша и остановка процессов Discord...\n");
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/IM", "Discord.exe"])
            .output();
        append_log(&mw, "[+] Процессы Discord остановлены.\n");
    });

    // Remove conflicts
    let mw_weak = main_window.as_weak();
    main_window.on_remove_conflicts(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let logs = diagnostics::remove_conflicts();
        for line in logs {
            append_log(&mw, &format!("{line}\n"));
        }
    });

    // Open original service.bat
    let mw_weak = main_window.as_weak();
    main_window.on_open_original_service(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            if z.service_bat.is_file() {
                let _ = std::process::Command::new("cmd.exe")
                    .args(["/c", "start", "zapret service", "service.bat", "admin"])
                    .current_dir(&z.orig_dir)
                    .spawn();
                append_log(&mw, "Оригинальный service.bat запущен в отдельной консоли.\n");
            } else {
                append_log(&mw, "[-] service.bat не найден по пути.\n");
            }
        }
    });

    // Clear log
    let mw_weak = main_window.as_weak();
    main_window.on_clear_log(move || {
        if let Some(mw) = mw_weak.upgrade() {
            mw.set_log_output("".into());
        }
    });

    // Background status polling (every 3 seconds)
    let running_flag = Arc::new(AtomicBool::new(true));
    let flag_clone = running_flag.clone();
    let mw_weak = main_window.as_weak();

    thread::spawn(move || {
        while flag_clone.load(Ordering::Relaxed) {
            // Check shutdown flag in 150ms steps rather than blocking for 3000ms
            for _ in 0..20 {
                if !flag_clone.load(Ordering::Relaxed) {
                    return;
                }
                thread::sleep(Duration::from_millis(150));
            }
            let mw_weak_clone = mw_weak.clone();
            let res = slint::invoke_from_event_loop(move || {
                if let Some(mw) = mw_weak_clone.upgrade() {
                    update_ui_status(&mw);
                }
            });
            if res.is_err() {
                break;
            }
        }
    });

    main_window.run()?;
    running_flag.store(false, Ordering::Relaxed);
    Ok(())
}

fn update_ui_status(mw: &MainWindow) {
    let svc_state = scm::query_service_status();
    let winws_running = process::is_process_running("winws.exe");
    let is_running = svc_state == ServiceState::Running || winws_running;

    mw.set_is_running(is_running);
    if is_running {
        mw.set_service_status("Служба активна".into());
        mw.set_status_color(Color::from_rgb_u8(34, 197, 94)); // Green
    } else if svc_state == ServiceState::Stopped {
        mw.set_service_status("Служба остановлена".into());
        mw.set_status_color(Color::from_rgb_u8(245, 158, 11)); // Amber
    } else {
        mw.set_service_status("Служба не установлена".into());
        mw.set_status_color(Color::from_rgb_u8(239, 68, 68)); // Red
    }
}

const MAX_LOG_LENGTH: usize = 40_000;

fn append_log(mw: &MainWindow, msg: &str) {
    let current = mw.get_log_output();
    let mut combined = format!("{current}{msg}");
    if combined.len() > MAX_LOG_LENGTH {
        let skip = combined.len() - MAX_LOG_LENGTH;
        if let Some(pos) = combined[skip..].find('\n') {
            combined = combined[skip + pos + 1..].to_string();
        } else {
            combined = combined[skip..].to_string();
        }
    }
    mw.set_log_output(combined.into());
}
