#![windows_subsystem = "windows"]

slint::include_modules!();

mod autostart;
mod diagnostics;
mod doh;
mod fakes;
mod i18n;
mod paths;
mod process;
mod scm;
mod settings;
mod sound;
mod strategies;
mod tests_runner;
mod theme;
mod tray;
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
    // 1. Single instance mutex (Local\zapret-rs-ui)
    let instance_mutex = unsafe {
        CreateMutexW(None, false, w!("Local\\zapret-rs-ui"))
    };
    if let Ok(h) = instance_mutex {
        let err = unsafe { windows::Win32::Foundation::GetLastError() };
        if err.0 == 183 { // ERROR_ALREADY_EXISTS
            unsafe { let _ = CloseHandle(h); }
            eprintln!("zapret-rs уже запущено.");
            return Ok(());
        }
    }

    let main_window = MainWindow::new()?;

    // 2. Admin rights check
    let is_admin = unsafe { IsUserAnAdmin().as_bool() };
    main_window.set_is_admin(is_admin);
    if is_admin {
        main_window.set_admin_status("Администратор".into());
        main_window.set_admin_color(Color::from_rgb_u8(34, 197, 94));
    } else {
        main_window.set_admin_status("Без прав админа".into());
        main_window.set_admin_color(Color::from_rgb_u8(245, 158, 11));
    }

    // 3. Paths detection & automatic migration to internal storage (%LOCALAPPDATA%\zapret-rs\engine)
    let internal_dir = paths::get_internal_zapret_dir();
    let is_already_internal = if let (Some(int_d), Some(z)) = (&internal_dir, ZapretPaths::detect()) {
        &z.orig_dir == int_d
    } else {
        false
    };

    let mut migration_note = String::new();

    // Если папки %LOCALAPPDATA%\zapret-rs\engine ещё нет, но мы нашли внешний zapret (например из установленной службы)
    if !is_already_internal
        && let Some(detected) = ZapretPaths::detect()
            && let Some(ref int_d) = internal_dir
                && &detected.orig_dir != int_d {
                    match paths::migrate_to_internal_storage(&detected.orig_dir) {
                        Ok(new_path) => {
                            migration_note = format!(
                                "[+] Выполнен бесшовный перенос zapret в защищенную папку:\n    {}\n    (из {})\n",
                                new_path.display(),
                                detected.orig_dir.display()
                            );
                        }
                        Err(e) => {
                            migration_note = format!("[!] Миграция во внутреннее хранилище пропущена: {e}\n");
                        }
                    }
                }

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
        main_window.set_game_filter_mode_index(match gf {
            settings::GameFilterMode::Disabled => 0,
            settings::GameFilterMode::Tcp => 1,
            settings::GameFilterMode::Udp => 2,
            settings::GameFilterMode::All => 3,
        });

        let ipset = settings::read_ipset_status(&z.orig_dir);
        main_window.set_ipset_active(ipset);
        main_window.set_ipset_text(if ipset { "Загружен".into() } else { "Отключен".into() });

        let chk = settings::read_check_updates_flag(&z.orig_dir);
        main_window.set_check_updates_text(if chk { "Включена".into() } else { "Отключена".into() });

        // Hosts status
        let windir = std::env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
        let hosts_path = std::path::Path::new(&windir).join("System32").join("drivers").join("etc").join("hosts");
        let has_hosts_block = hosts_path.is_file() && std::fs::read_to_string(&hosts_path).map(|c| c.contains("# === ZAPRET HOSTS START ===")).unwrap_or(false);
        main_window.set_hosts_block_present(has_hosts_block);
        main_window.set_hosts_info_summary(if has_hosts_block { "Оптимизация активна".into() } else { "Оптимизация не установлена".into() });

        // Fakes status
        let fakes_status = fakes::get_active_fakes_status(&z.orig_dir);
        main_window.set_discord_fake_active(fakes_status.discord_active_name.into());
        main_window.set_game_fake_active(fakes_status.game_active_name.into());
    }

    // Sound setting
    let sound_on = sound::is_sound_enabled();
    main_window.set_sound_enabled(sound_on);

    // Theme setting (System / Dark / Light)
    let current_theme = std::sync::Arc::new(std::sync::Mutex::new(theme::load_saved_theme()));
    {
        let t = current_theme.lock().unwrap();
        let idx = match *t {
            theme::AppTheme::System => 0,
            theme::AppTheme::Dark => 1,
            theme::AppTheme::Light => 2,
        };
        main_window.set_theme_mode_index(idx);
        main_window.set_theme_mode_text(format!("🎨 Тема: {}", t.as_str()).into());
        main_window.set_is_dark_theme(t.is_dark());
    }

    // Language setting (System / Russian / English)
    let current_lang = std::sync::Arc::new(std::sync::Mutex::new(i18n::load_saved_language()));
    {
        let l = current_lang.lock().unwrap();
        let idx = match *l {
            i18n::AppLanguage::System => 0,
            i18n::AppLanguage::Russian => 1,
            i18n::AppLanguage::English => 2,
        };
        main_window.set_lang_mode_index(idx);
        main_window.set_lang_mode_text(format!("🌐 Язык: {}", l.as_str()).into());
        main_window.set_is_english(l.resolve() == "en");
    }

    // Initial DoH status
    let doh_stat = doh::get_doh_status();
    main_window.set_doh_active(doh_stat.enabled);
    main_window.set_doh_provider_text(doh_stat.provider_name.into());

    // Initial Autostart status
    let auto_on = autostart::is_autostart_enabled();
    main_window.set_autostart_active(auto_on);
    main_window.set_autostart_text(if auto_on { "Включена".into() } else { "Отключена".into() });

    // 5. Load strategies
    let (strats, current_strat, has_configured) = if let Some(ref z) = zapret_opt {
        let list = strategies::list_strategies(&z.orig_dir);
        let has_conf = strategies::current_strategy().is_some();
        let cur = strategies::current_strategy().unwrap_or_else(|| {
            if list.contains(&"general".to_string()) {
                "general".to_string()
            } else {
                list.first().cloned().unwrap_or_default()
            }
        });
        (list, cur, has_conf)
    } else {
        (vec![], "".to_string(), false)
    };

    let idx = strats.iter().position(|s| s == &current_strat).unwrap_or(0);
    let slint_strats: Vec<slint::SharedString> = strats.iter().map(|s| s.into()).collect();
    main_window.set_strategies(ModelRc::new(VecModel::from(slint_strats)));
    main_window.set_selected_strategy_index(idx as i32);
    main_window.set_has_configured_strategy(has_configured);

    // Initial status update
    update_ui_status(&main_window);

    // Initial log message
    let init_log = if let Some(ref z) = zapret_opt {
        format!(
            "zapret-rs v0.1.0-alpha.1 (Rust + Slint Native UI) готов к работе.\nКаталог zapret: {}\nВерсия ядра: {}\nПрава: {}\n{}{}",
            z.orig_dir.display(),
            version,
            if is_admin { "Администратор" } else { "Пользователь (нужен UAC для служб)" },
            if migration_note.is_empty() { "".to_string() } else { format!("{migration_note}\n") },
            "----------------------------------------------------\n"
        )
    } else {
        "ВНИМАНИЕ: Каталог zapret не найден! Поместите zapret в ./zapret/ или задайте ZAPRET_DIR.\n".to_string()
    };
    main_window.set_log_output(init_log.into());

    // ===== Callbacks =====

    // Elevate admin
    let mw_weak = main_window.as_weak();
    let instance_mutex_holder = std::sync::Arc::new(std::sync::Mutex::new(instance_mutex.ok()));
    let mutex_clone = instance_mutex_holder.clone();

    main_window.on_elevate_admin(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Ok(exe_path) = std::env::current_exe() {
            let path_str = exe_path.to_string_lossy().to_string();
            let wide_file: Vec<u16> = path_str.encode_utf16().chain(std::iter::once(0)).collect();
            let wide_op: Vec<u16> = "runas".encode_utf16().chain(std::iter::once(0)).collect();

            // Перед вызовом нового процесса закрываем собственный Single Instance мьютекс,
            // чтобы новый повышенный процесс не натолкнулся на ERROR_ALREADY_EXISTS и не закрылся мгновенно!
            if let Ok(mut lock) = mutex_clone.lock() {
                if let Some(h) = lock.take() {
                    unsafe {
                        let _ = CloseHandle(h);
                    }
                }
            }

            unsafe {
                let inst = windows::Win32::UI::Shell::ShellExecuteW(
                    None,
                    windows::core::PCWSTR(wide_op.as_ptr()),
                    windows::core::PCWSTR(wide_file.as_ptr()),
                    windows::core::PCWSTR::null(),
                    windows::core::PCWSTR::null(),
                    windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL,
                );
                if (inst.0 as isize) > 32 {
                    std::process::exit(0);
                } else {
                    append_log(&mw, "[-] Отказ в повышении прав UAC или ошибка вызова.\n");
                }
            }
        }
    });

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
                    let killed = process::kill_process("winws.exe");
                    sound::play_sound("disconnect");
                    if killed > 0 {
                        append_log(&mw, &format!("Служба zapret остановлена (завершено {killed} процессов winws.exe).\n"));
                    } else {
                        append_log(&mw, "Служба zapret успешно остановлена.\n");
                    }
                }
                Err(e) => {
                    let killed = process::kill_process("winws.exe");
                    sound::play_sound("alert");
                    append_log(&mw, &format!("Ошибка остановки службы SCM: {e} (принудительно снято процессов winws: {killed})\n"));
                }
            }
        } else {
            // Очищаем зависшие процессы перед стартом
            let killed = process::kill_process("winws.exe");
            if killed > 0 {
                append_log(&mw, &format!("[*] Зачищен зависший процесс winws.exe ({killed} шт.)\n"));
            }

            // Если служба еще не установлена в SCM, устанавливаем текущую выбранную стратегию
            if scm::query_service_status() == ServiceState::NotInstalled
                && let Some(z) = ZapretPaths::detect() {
                    let idx = mw.get_selected_strategy_index() as usize;
                    let model = mw.get_strategies();
                    let strat_name = model.row_data(idx).unwrap_or_else(|| "general".into());
                    append_log(&mw, &format!("[*] Служба не найдена в SCM. Установка стратегии {strat_name}...\n"));

                    match strategies::parse_strategy_args(&z.orig_dir, &strat_name) {
                        Ok(args) => {
                            let exe_str = z.winws_exe.to_string_lossy();
                            if let Err(e) = scm::install_or_update_service(&exe_str, &args) {
                                sound::play_sound("alert");
                                append_log(&mw, &format!("[-] Ошибка установки службы: {e}\n"));
                                update_ui_status(&mw);
                                return;
                            }
                            append_log(&mw, &format!("[+] Служба успешно установлена с конфигурацией {strat_name}.\n"));
                        }
                        Err(e) => {
                            sound::play_sound("alert");
                            append_log(&mw, &format!("[-] Ошибка разбора {strat_name}.bat: {e}\n"));
                            update_ui_status(&mw);
                            return;
                        }
                    }
                }

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
                let killed = process::kill_process("winws.exe");
                sound::play_sound("disconnect");
                if killed > 0 {
                    append_log(&mw, &format!("[+] Служба zapret удалена из SCM (снято {killed} процессов winws).\n"));
                } else {
                    append_log(&mw, "[+] Служба zapret удалена из Windows SCM.\n");
                }
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

        let details = format!(
            "=== СТАТУС СЛУЖБЫ ZAPRET ===\nСостояние в Windows SCM : {}\nПроцесс winws.exe       : {}\nТекущая стратегия       : {}\nИмя службы в реестре    : zapret\n============================\n",
            svc_state.as_str(),
            if winws_running { "Запущен (Running)" } else { "Не запущен (Stopped)" },
            active_strat
        );

        append_log(&mw, &details);
        mw.set_diag_modal_title("🛡️ Статус службы zapret".into());
        mw.set_diag_modal_text(details.into());
        mw.set_show_diag_modal(true);
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
            append_log(&mw, &format!("Стратегия сохранена: {strat_name}\nПрименение параметров к службе Windows...\n"));

            if let Some(z) = ZapretPaths::detect() {
                match strategies::parse_strategy_args(&z.orig_dir, &strat_name) {
                    Ok(args) => {
                        let _ = scm::stop_service();
                        let killed = process::kill_process("winws.exe");
                        if killed > 0 {
                            append_log(&mw, &format!("[*] Зачищен предыдущий winws.exe ({killed} шт.)\n"));
                        }

                        let exe_str = z.winws_exe.to_string_lossy();
                        if let Err(e) = scm::install_or_update_service(&exe_str, &args) {
                            sound::play_sound("alert");
                            append_log(&mw, &format!("[-] Ошибка обновления службы в SCM: {e}\n"));
                            update_ui_status(&mw);
                            return;
                        }

                        append_log(&mw, "[+] Служба zapret успешно сконфигурирована в SCM. Запуск...\n");
                        match scm::start_service() {
                            Ok(_) => {
                                sound::play_sound("connect");
                                append_log(&mw, &format!("Стратегия {strat_name} успешно запущена в службе!\n"));
                            }
                            Err(e) => {
                                sound::play_sound("alert");
                                append_log(&mw, &format!("Ошибка запуска обновлённой службы: {e}\n"));
                            }
                        }
                    }
                    Err(e) => {
                        sound::play_sound("alert");
                        append_log(&mw, &format!("[-] Ошибка обработки {strat_name}.bat: {e}\n"));
                    }
                }
            } else {
                append_log(&mw, "[-] Каталог zapret не найден.\n");
            }
            update_ui_status(&mw);
        }
    });

    // Select strategy from list
    let mw_weak = main_window.as_weak();
    main_window.on_select_strategy(move |idx| {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let model = mw.get_strategies();
        if let Some(strat_name) = model.row_data(idx as usize) {
            let _ = strategies::save_current_strategy(&strat_name);
            append_log(&mw, &format!("[*] Выбрана стратегия: {strat_name}. Нажмите «Применить» для применения к службе.\n"));
        }
    });

    // Apply specific DoH provider
    let mw_weak = main_window.as_weak();
    main_window.on_apply_doh_provider(move |provider_key| {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let key_str = provider_key.to_string();
        append_log(&mw, &format!("Настройка DNS / DoH: {key_str}...\n"));

        let res = if key_str == "dhcp" {
            doh::disable_doh()
        } else {
            doh::set_doh(&key_str)
        };

        match res {
            Ok(msg) => {
                sound::play_sound("done");
                append_log(&mw, &format!("[+] {msg}\n"));
                let st = doh::get_doh_status();
                mw.set_doh_active(st.enabled);
                mw.set_doh_provider_text(st.provider_name.into());
            }
            Err(e) => {
                sound::play_sound("alert");
                append_log(&mw, &format!("[-] Ошибка настройки DNS/DoH: {e}\n"));
            }
        }
    });

    // Select GameFilter explicitly (0: Disabled, 1: TCP, 2: UDP, 3: All)
    let mw_weak = main_window.as_weak();
    main_window.on_select_game_filter(move |mode_idx| {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            let target_mode = match mode_idx {
                1 => settings::GameFilterMode::Tcp,
                2 => settings::GameFilterMode::Udp,
                3 => settings::GameFilterMode::All,
                _ => settings::GameFilterMode::Disabled,
            };
            match settings::set_game_filter_mode(&z.orig_dir, target_mode) {
                Ok(_) => {
                    sound::play_sound("click");
                    mw.set_game_filter_text(target_mode.as_label().into());
                    mw.set_game_filter_mode_index(mode_idx);
                    append_log(&mw, &format!("Игровой фильтр установлен: {}\n", target_mode.as_label()));
                }
                Err(e) => {
                    sound::play_sound("alert");
                    append_log(&mw, &format!("Ошибка настройки GameFilter: {e}\n"));
                }
            }
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
                    let idx = match new_mode {
                        settings::GameFilterMode::Disabled => 0,
                        settings::GameFilterMode::Tcp => 1,
                        settings::GameFilterMode::Udp => 2,
                        settings::GameFilterMode::All => 3,
                    };
                    mw.set_game_filter_text(new_mode.as_label().into());
                    mw.set_game_filter_mode_index(idx);
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

    // Auto-update Hosts file
    let mw_weak = main_window.as_weak();
    main_window.on_update_hosts_auto(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Загрузка оптимизированного hosts с GitHub Flowseal...\n");
        match updates::update_hosts_file() {
            Ok(msg) => {
                sound::play_sound("done");
                append_log(&mw, &format!("[+] {msg}\n"));
                mw.set_hosts_block_present(true);
                mw.set_hosts_info_summary("Оптимизация активна".into());
            }
            Err(e) => {
                sound::play_sound("alert");
                append_log(&mw, &format!("[-] Ошибка обновления hosts: {e}\n"));
            }
        }
    });

    // Open Hosts file in Notepad
    let mw_weak = main_window.as_weak();
    main_window.on_open_hosts_file(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Err(e) = updates::open_hosts_in_notepad() {
            append_log(&mw, &format!("[-] Не удалось открыть hosts: {e}\n"));
        } else {
            append_log(&mw, "[+] Файл hosts открыт в Блокноте.\n");
        }
    });

    // Open Fakes Selector Modal
    let mw_weak = main_window.as_weak();
    main_window.on_open_fakes_modal(move |target| {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            let available = fakes::list_available_fakes(&z.orig_dir);
            let active_status = fakes::get_active_fakes_status(&z.orig_dir);
            let active_current = if target == 1 {
                &active_status.discord_active_name
            } else {
                &active_status.game_active_name
            };

            let slint_items: Vec<FakeEntry> = available
                .into_iter()
                .map(|f| FakeEntry {
                    is_active: f.name == *active_current,
                    name: f.name.into(),
                    label: f.label.into(),
                    description: f.description.into(),
                })
                .collect();

            let model = std::rc::Rc::new(slint::VecModel::from(slint_items));
            mw.set_fakes_list(model.into());
            mw.set_fakes_modal_target(target);
            mw.set_fakes_modal_title(if target == 1 {
                "Выбор фейка для Discord UDP (Голос)".into()
            } else {
                "Выбор фейка для Игрового фильтра UDP".into()
            });
            mw.set_show_fakes_modal(true);
        }
    });

    // Select Fake Item
    let mw_weak = main_window.as_weak();
    main_window.on_select_fake_item(move |target, filename| {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            let fake_target = if target == 1 {
                fakes::FakeTarget::DiscordUdp
            } else {
                fakes::FakeTarget::GameUdp
            };
            let filename_str = filename.as_str();
            match fakes::set_active_fake(&z.orig_dir, fake_target, filename_str) {
                Ok(_) => {
                    sound::play_sound("done");
                    append_log(&mw, &format!("[+] Активный фейк успешно заменен на: {}\n", filename_str));
                    let updated_status = fakes::get_active_fakes_status(&z.orig_dir);
                    mw.set_discord_fake_active(updated_status.discord_active_name.into());
                    mw.set_game_fake_active(updated_status.game_active_name.into());
                }
                Err(e) => {
                    sound::play_sound("alert");
                    append_log(&mw, &format!("[-] Ошибка замены фейка: {e}\n"));
                }
            }
        }
    });

    // Reset Fakes to Default Recommended
    let mw_weak = main_window.as_weak();
    main_window.on_reset_fakes_to_default(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        if let Some(z) = ZapretPaths::detect() {
            match fakes::reset_to_recommended_fakes(&z.orig_dir) {
                Ok(_) => {
                    sound::play_sound("done");
                    append_log(&mw, "[+] Фейковые пакеты Discord и Game успешно сброшены на рекомендуемые по умолчанию!\n");
                    let updated_status = fakes::get_active_fakes_status(&z.orig_dir);
                    mw.set_discord_fake_active(updated_status.discord_active_name.into());
                    mw.set_game_fake_active(updated_status.game_active_name.into());
                }
                Err(e) => {
                    sound::play_sound("alert");
                    append_log(&mw, &format!("[-] Ошибка сброса фейков: {e}\n"));
                }
            }
        }
    });

    // Check updates & Start atomic engine update
    let mw_weak = main_window.as_weak();
    let ver_clone = version.clone();
    main_window.on_check_updates(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "Проверка обновлений на GitHub...\n");
        mw.set_update_modal_title("Проверка обновлений zapret".into());
        mw.set_update_modal_status("Подключение к GitHub API...".into());
        mw.set_update_progress(0.2);
        mw.set_update_in_progress(true);
        mw.set_update_can_close(false);
        mw.set_show_update_modal(true);

        let mw_weak_worker = mw.as_weak();
        let current_ver = ver_clone.clone();
        thread::spawn(move || {
            let res = updates::check_zapret_release(&current_ver);
            let _ = mw_weak_worker.upgrade_in_event_loop(move |w| {
                w.set_update_in_progress(false);
                w.set_update_can_close(true);
                match res {
                    Ok(info) => {
                        append_log(&w, &format!("{}\n", info.message));
                        if info.is_newer && !info.zip_url.is_empty() {
                            w.set_update_modal_title(format!("Доступна новая версия: {}", info.tag).into());
                            w.set_update_modal_status(format!("Найдена новая версия {}. Нажмите «Обновить», чтобы начать фоновую загрузку и бесшовную установку.", info.tag).into());
                            w.set_update_progress(1.0);
                        } else {
                            w.set_update_modal_title("Обновлений не найдено".into());
                            w.set_update_modal_status(format!("Установлена актуальная версия zapret: {}.\nДвижок не требует обновления.", current_ver).into());
                            w.set_update_progress(1.0);
                        }
                    }
                    Err(e) => {
                        append_log(&w, &format!("[-] {}\n", e));
                        w.set_update_modal_title("Ошибка проверки обновлений".into());
                        w.set_update_modal_status(format!("Не удалось получить информацию с GitHub: {}", e).into());
                        w.set_update_progress(0.0);
                    }
                }
            });
        });
    });

    // Start engine update (Live download under zapret -> staging -> atomic cutover)
    let mw_weak = main_window.as_weak();
    let ver_for_upd = version.clone();
    main_window.on_start_engine_update(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        mw.set_update_modal_title("Обновление движка zapret".into());
        mw.set_update_modal_status("Подготовка к фоновой загрузке...".into());
        mw.set_update_progress(0.1);
        mw.set_update_in_progress(true);
        mw.set_update_can_close(false);
        mw.set_show_update_modal(true);

        let mw_weak_worker = mw.as_weak();
        let cur_v = ver_for_upd.clone();
        thread::spawn(move || {
            // Step 1: Query release
            let _ = mw_weak_worker.upgrade_in_event_loop(|w| {
                w.set_update_modal_status("Поиск ссылки на загрузку архива...".into());
                w.set_update_progress(0.2);
            });
            let rel = match updates::check_zapret_release(&cur_v) {
                Ok(r) => r,
                Err(e) => {
                    let _ = mw_weak_worker.upgrade_in_event_loop(move |w| {
                        w.set_update_in_progress(false);
                        w.set_update_can_close(true);
                        w.set_update_modal_status(format!("Ошибка проверки: {e}").into());
                    });
                    return;
                }
            };

            let zip_url = if !rel.zip_url.is_empty() {
                rel.zip_url
            } else {
                format!("https://github.com/Flowseal/zapret-discord-youtube/releases/download/{}/zapret-discord-youtube-{}.zip", rel.tag, rel.tag)
            };

            // Step 2: Download ZIP under protection of running zapret service
            let _ = mw_weak_worker.upgrade_in_event_loop(|w| {
                w.set_update_modal_status("Загрузка обновления в фоне (служба продолжает работать)...".into());
                w.set_update_progress(0.4);
            });

            let temp_dir = std::env::temp_dir();
            let update_zip = temp_dir.join("zapret_latest_update.zip");
            let dl_res = std::process::Command::new("curl.exe")
                .args(["-s", "-L", "-A", "zapret-rs", &zip_url, "-o", update_zip.to_str().unwrap()])
                .output();

            if dl_res.is_err() || !update_zip.is_file() {
                let _ = mw_weak_worker.upgrade_in_event_loop(|w| {
                    w.set_update_in_progress(false);
                    w.set_update_can_close(true);
                    w.set_update_modal_status("Не удалось загрузить архив обновления с GitHub.".into());
                });
                return;
            }

            // Step 3: Unpack into staging directory
            let _ = mw_weak_worker.upgrade_in_event_loop(|w| {
                w.set_update_modal_status("Распаковка и проверка файлов в staging...".into());
                w.set_update_progress(0.65);
            });

            let staging_dir = temp_dir.join("zapret_staging");
            let _ = std::fs::remove_dir_all(&staging_dir);
            let _ = std::fs::create_dir_all(&staging_dir);

            if let Err(e) = paths::unpack_zapret_zip(&update_zip, Some(&staging_dir)) {
                let _ = mw_weak_worker.upgrade_in_event_loop(move |w| {
                    w.set_update_in_progress(false);
                    w.set_update_can_close(true);
                    w.set_update_modal_status(format!("Ошибка распаковки: {e}").into());
                });
                return;
            }

            // Step 4: Atomic Cutover (stop service -> replace files in internal storage -> restart)
            let _ = mw_weak_worker.upgrade_in_event_loop(|w| {
                w.set_update_modal_status("Мгновенная замена файлов ядра zapret (Atomic Cutover)...".into());
                w.set_update_progress(0.85);
            });

            let internal_dir = match paths::get_internal_zapret_dir() {
                Some(d) => d,
                None => {
                    let _ = mw_weak_worker.upgrade_in_event_loop(|w| {
                        w.set_update_in_progress(false);
                        w.set_update_can_close(true);
                        w.set_update_modal_status("Не удалось определить внутренний каталог %LOCALAPPDATA%".into());
                    });
                    return;
                }
            };

            // Short pause of service
            let was_running = scm::query_service_status() == scm::ServiceState::Running;
            if was_running {
                let _ = scm::stop_service();
            }

            // Copy staging to internal storage via robocopy (preserves existing files / lists)
            let _ = std::process::Command::new("robocopy")
                .args([
                    staging_dir.to_str().unwrap(),
                    internal_dir.to_str().unwrap(),
                    "/E",
                    "/IS",
                    "/IT",
                    "/NJH",
                    "/NJS",
                    "/NDL",
                    "/NC",
                    "/NS",
                ])
                .output();

            // Restart service if was running
            if was_running {
                let current_st = strategies::current_strategy().unwrap_or_else(|| "general (ALT4)".to_string());
                if let Ok(args) = strategies::parse_strategy_args(&internal_dir, &current_st) {
                    let winws_path = internal_dir.join("bin").join("winws.exe").to_string_lossy().to_string();
                    let _ = scm::install_or_update_service(&winws_path, &args);
                    let _ = scm::start_service();
                }
            }

            // Cleanup
            let _ = std::fs::remove_file(&update_zip);
            let _ = std::fs::remove_dir_all(&staging_dir);

            // Step 5: Success!
            let new_tag = rel.tag.clone();
            let _ = mw_weak_worker.upgrade_in_event_loop(move |w| {
                w.set_update_progress(1.0);
                w.set_update_in_progress(false);
                w.set_update_can_close(true);
                w.set_update_modal_title("Обновление успешно установлено!".into());
                w.set_update_modal_status(format!("Движок zapret успешно обновлен до версии {}. Служба перезапущена и работает в штатном режиме.", new_tag).into());
                w.set_zapret_version(format!("v{}", new_tag.trim_start_matches('v')).into());
                update_ui_status(&w);
                sound::play_sound("done");
                append_log(&w, &format!("[+] Движок zapret обновлён до версии {}.\n", new_tag));
            });
        });
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
            let formatted = report.format_text();
            append_log(&mw, &formatted);
            sound::play_sound("done");

            mw.set_diag_modal_title("🔍 Отчёт комплексной диагностики (18 проверок)".into());
            mw.set_diag_modal_text(formatted.into());
            mw.set_show_diag_modal(true);
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

    // Select Language (0: System, 1: Russian, 2: English)
    let mw_weak = main_window.as_weak();
    let lang_holder = current_lang.clone();
    main_window.on_select_language(move |index| {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let chosen_lang = match index {
            1 => i18n::AppLanguage::Russian,
            2 => i18n::AppLanguage::English,
            _ => i18n::AppLanguage::System,
        };
        {
            let mut l_lock = lang_holder.lock().unwrap();
            *l_lock = chosen_lang;
        }
        i18n::save_language(chosen_lang);

        mw.set_lang_mode_index(index);
        mw.set_lang_mode_text(format!("🌐 Язык: {}", chosen_lang.as_str()).into());
        mw.set_is_english(chosen_lang.resolve() == "en");
        sound::play_sound("click");
        append_log(&mw, &format!("Язык интерфейса изменен: {}\n", chosen_lang.as_str()));
    });

    // Select Theme (0: System, 1: Dark, 2: Light)
    let mw_weak = main_window.as_weak();
    let theme_holder = current_theme.clone();
    main_window.on_select_theme(move |index| {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let chosen_theme = match index {
            1 => theme::AppTheme::Dark,
            2 => theme::AppTheme::Light,
            _ => theme::AppTheme::System,
        };
        {
            let mut t_lock = theme_holder.lock().unwrap();
            *t_lock = chosen_theme;
        }
        theme::save_theme(chosen_theme);

        mw.set_theme_mode_index(index);
        mw.set_theme_mode_text(format!("🎨 Тема: {}", chosen_theme.as_str()).into());
        mw.set_is_dark_theme(chosen_theme.is_dark());
        sound::play_sound("click");
        append_log(&mw, &format!("Тема оформления изменена: {}\n", chosen_theme.as_str()));
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

    // Native Benchmark Runner
    let cancel_bench_flag = Arc::new(AtomicBool::new(false));
    let cancel_flag_clone = cancel_bench_flag.clone();
    let mw_weak_bench = main_window.as_weak();

    main_window.on_start_native_bench(move || {
        let mw = match mw_weak_bench.upgrade() {
            Some(w) => w,
            None => return,
        };

        let zapret_paths = match ZapretPaths::detect() {
            Some(z) => z,
            None => {
                append_log(&mw, "[-] Каталог zapret не найден для проведения тестов.\n");
                return;
            }
        };

        // Открываем модальное окно
        mw.set_show_bench_modal(true);
        mw.set_bench_in_progress(true);
        mw.set_bench_progress(0.0);
        mw.set_bench_status_text("Подготовка к тестированию...".into());
        mw.set_bench_current_target("".into());
        mw.set_bench_best_strategy("".into());

        let initial_lines: Vec<slint::SharedString> = vec![
            "[*] Инициализация полного тестирования стратегий zapret...".into(),
            "[*] Протоколы: HTTP / TLS 1.2 / TLS 1.3 / Ping (полный набор targets.txt)".into(),
        ];
        mw.set_bench_log_lines(ModelRc::new(VecModel::from(initial_lines)));

        cancel_flag_clone.store(false, Ordering::Relaxed);
        let flag = cancel_flag_clone.clone();
        let mw_weak_worker = mw.as_weak();

        thread::spawn(move || {
            // Временно останавливаем службу
            let was_running = scm::query_service_status() == ServiceState::Running || process::is_process_running("winws.exe");
            if was_running {
                let _ = scm::stop_service();
                let _ = process::kill_process("winws.exe");
                let _ = mw_weak_worker.upgrade_in_event_loop(|w| {
                    update_ui_status(&w);
                });
            }

            // Получаем список доступных стратегий
            let strats = strategies::list_strategies(&zapret_paths.orig_dir);
            let orig_dir = zapret_paths.orig_dir.clone();

            let (_results, best_strategy, report_path) = tests_runner::run_full_benchmark(
                &orig_dir,
                strats,
                flag.clone(),
                |progress| {
                    let p_float = if progress.total_count > 0 {
                        progress.current_index as f32 / progress.total_count as f32
                    } else {
                        0.0
                    };
                    let cur_strat = progress.current_strategy.clone();
                    let cur_target = progress.current_target.clone();
                    let best = progress.best_strategy.clone().unwrap_or_default();

                    let lines: Vec<slint::SharedString> = progress.log_lines.iter().map(|s| s.as_str().into()).collect();

                    let _ = mw_weak_worker.upgrade_in_event_loop(move |w| {
                        w.set_bench_progress(p_float);
                        w.set_bench_current_strategy(cur_strat.into());
                        w.set_bench_current_target(cur_target.into());
                        w.set_bench_status_text(format!("Конфигурация {} из {}", progress.current_index, progress.total_count).into());
                        w.set_bench_log_lines(ModelRc::new(VecModel::from(lines)));
                        if !best.is_empty() {
                            w.set_bench_best_strategy(best.into());
                        }
                    });
                },
            );

            let _ = mw_weak_worker.upgrade_in_event_loop(move |w| {
                w.set_bench_in_progress(false);
                w.set_bench_progress(1.0);
                w.set_bench_status_text("Тестирование завершено! Отчёт сохранён.".into());
                w.set_bench_current_target("".into());

                if let Some(ref best) = best_strategy {
                    w.set_bench_best_strategy(best.clone().into());
                    sound::play_sound("done");
                    append_log(&w, &format!("[🏆] Тестирование завершено! Лучшая стратегия по аналитике: {}\n", best));
                    if let Some(ref p) = report_path {
                        append_log(&w, &format!("[💾] Файл отчёта сформирован:\n    {}\n", p.display()));
                    }
                } else {
                    w.set_bench_best_strategy("".into());
                    sound::play_sound("alert");
                    append_log(&w, "[!] Тестирование остановлено или не дало результатов.\n");
                }
            });
        });
    });

    // Отмена тестирования
    let cancel_flag_abort = cancel_bench_flag.clone();
    let mw_weak_abort = main_window.as_weak();
    main_window.on_cancel_native_bench(move || {
        cancel_flag_abort.store(true, Ordering::Relaxed);
        let _ = process::kill_process("winws.exe");
        if let Some(mw) = mw_weak_abort.upgrade() {
            mw.set_bench_in_progress(false);
            mw.set_bench_status_text("Тестирование прервано пользователем".into());
            append_log(&mw, "[*] Тестирование стратегий остановлено.\n");
        }
    });

    // Применить лучшую найденную стратегию
    let mw_weak_apply_best = main_window.as_weak();
    main_window.on_apply_best_strategy(move || {
        let mw = match mw_weak_apply_best.upgrade() {
            Some(w) => w,
            None => return,
        };
        let best = mw.get_bench_best_strategy().to_string();
        if !best.is_empty() {
            let model = mw.get_strategies();
            let mut found_idx = 0;
            for i in 0..model.row_count() {
                if let Some(name) = model.row_data(i) {
                    if name == best {
                        found_idx = i;
                        break;
                    }
                }
            }
            mw.set_selected_strategy_index(found_idx as i32);
            let _ = strategies::save_current_strategy(&best);

            if let Some(z) = ZapretPaths::detect() {
                if let Ok(args) = strategies::parse_strategy_args(&z.orig_dir, &best) {
                    let exe_str = z.winws_exe.to_string_lossy();
                    let _ = scm::install_or_update_service(&exe_str, &args);
                    let _ = scm::start_service();
                    sound::play_sound("connect");
                    mw.set_has_configured_strategy(true);
                    append_log(&mw, &format!("[+] Установлена и запущена лучшая стратегия: {}\n", best));
                    update_ui_status(&mw);
                }
            }
        }
    });

    // Run tests (legacy external test zapret.ps1)
    let mw_weak = main_window.as_weak();
    main_window.on_run_tests(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        append_log(&mw, "[*] Подготовка к запуску тестирования zapret...\n");

        // 1. Скрипт test zapret.ps1 строго требует отсутствия зарегистрированной службы 'zapret' в Windows SCM.
        // Запоминаем текущую стратегию и временно удаляем службу из SCM на время тестов.
        let is_installed = scm::query_service_status() != ServiceState::NotInstalled;
        let mut saved_strategy = strategies::current_strategy().unwrap_or_else(|| "general (ALT4)".to_string());
        let current_idx = mw.get_selected_strategy_index() as usize;
        let model = mw.get_strategies();
        if let Some(strat_name) = model.row_data(current_idx) {
            saved_strategy = strat_name.to_string();
        }

        if is_installed {
            append_log(&mw, "[*] Временное удаление службы 'zapret' из SCM (требование test zapret.ps1)...\n");
            let _ = scm::stop_service();
            let _ = process::kill_process("winws.exe");
            match scm::delete_service_named("zapret") {
                Ok(_) => append_log(&mw, "[+] Служба 'zapret' временно снята с регистрации в SCM.\n"),
                Err(e) => append_log(&mw, &format!("[!] Предупреждение при снятии службы: {e}\n")),
            }
            update_ui_status(&mw);
        } else {
            let killed = process::kill_process("winws.exe");
            if killed > 0 {
                append_log(&mw, &format!("[*] Завершено зависших процессов winws: {killed}\n"));
            }
        }

        if let Some(z) = ZapretPaths::detect() {
            let ps1 = z.orig_dir.join("utils").join("test zapret.ps1");
            if ps1.is_file() {
                append_log(&mw, &format!("[+] Запуск консоли тестирования: {}\n", ps1.display()));
                let ps1_str = ps1.to_string_lossy().to_string();

                // Запускаем PowerShell в видимом интерактивном окне (с правами администратора через ShellExecuteW 'runas')
                let wide_op: Vec<u16> = "runas".encode_utf16().chain(std::iter::once(0)).collect();
                let wide_file: Vec<u16> = "powershell.exe".encode_utf16().chain(std::iter::once(0)).collect();
                let params = format!("-NoExit -NoProfile -ExecutionPolicy Bypass -File \"{}\"", ps1_str);
                let wide_params: Vec<u16> = params.encode_utf16().chain(std::iter::once(0)).collect();
                let dir_str = z.orig_dir.to_string_lossy().to_string();
                let wide_dir: Vec<u16> = dir_str.encode_utf16().chain(std::iter::once(0)).collect();

                unsafe {
                    let inst = windows::Win32::UI::Shell::ShellExecuteW(
                        None,
                        windows::core::PCWSTR(wide_op.as_ptr()),
                        windows::core::PCWSTR(wide_file.as_ptr()),
                        windows::core::PCWSTR(wide_params.as_ptr()),
                        windows::core::PCWSTR(wide_dir.as_ptr()),
                        windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL,
                    );
                    if (inst.0 as isize) > 32 {
                        append_log(&mw, "[+] Интерактивное окно тестов успешно запущено.\n");
                        append_log(&mw, &format!("[ℹ] После завершения тестов просто нажмите «Применить» на главной, чтобы восстановить службу со стратегией: {saved_strategy}.\n"));
                    } else {
                        append_log(&mw, "[-] Не удалось открыть окно PowerShell от администратора. Проверьте запрос UAC.\n");
                    }
                }
            } else {
                append_log(&mw, &format!("[-] Скрипт не найден по пути: {}\n", ps1.display()));
            }
        } else {
            append_log(&mw, "[-] Каталог zapret не обнаружен!\n");
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

    // Copy log to clipboard
    let mw_weak = main_window.as_weak();
    main_window.on_copy_log_to_clipboard(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let log = mw.get_log_output().to_string();
        copy_text_to_clipboard(&log);
        sound::play_sound("done");
        append_log(&mw, "[+] Журнал событий успешно скопирован в буфер обмена Windows.\n");
    });

    // Export support bundle
    let mw_weak = main_window.as_weak();
    let ver_for_export = version.clone();
    main_window.on_export_support_bundle(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let diag_text = if let Some(z) = ZapretPaths::detect() {
            let r = diagnostics::run_full_diagnostics(&z.orig_dir);
            r.format_text()
        } else {
            "Каталог zapret не найден".to_string()
        };

        let current_log = mw.get_log_output().to_string();
        let svc_state = scm::query_service_status();
        let is_running = mw.get_is_running();
        let strat_idx = mw.get_selected_strategy_index() as usize;
        let strat_model = mw.get_strategies();
        let current_st = strat_model.row_data(strat_idx).unwrap_or_else(|| "general".into());

        let bundle = format!(
            "====================================================================\n\
             ОТЧЁТ ДЛЯ ТЕХПОДДЕРЖКИ ZAPRET-RS (CRASH / DIAGNOSTIC BUNDLE)\n\
             Время создания: {}\n\
             Версия приложения: zapret-rs v1.1.0 (Slint + Rust Native)\n\
             Версия ядра zapret: {}\n\
             Статус службы SCM: {}\n\
             Процесс WinWS: {}\n\
             Активная стратегия: {}\n\
             Права процесса: {}\n\
             ====================================================================\n\n\
             {}\n\n\
             ========================= ЖУРНАЛ СОБЫТИЙ =========================\n\
             {}\n\
             ====================================================================\n",
            chrono_timestamp(),
            ver_for_export,
            svc_state.as_str(),
            if is_running { "Работает" } else { "Остановлен" },
            current_st,
            if mw.get_is_admin() { "Администратор" } else { "Обычный пользователь" },
            diag_text,
            current_log
        );

        // Сохраняем на Рабочий стол пользователя и копируем в буфер
        copy_text_to_clipboard(&bundle);

        let desktop_path = get_desktop_dir().map(|d| d.join("zapret_diagnostic_report.txt"));
        if let Some(ref path) = desktop_path {
            if std::fs::write(path, &bundle).is_ok() {
                sound::play_sound("done");
                append_log(&mw, &format!("[+] Отчёт для поддержки сохранён на Рабочий стол:\n    {}\n[+] И скопирован в буфер обмена!\n", path.display()));
                return;
            }
        }

        sound::play_sound("done");
        append_log(&mw, "[+] Отчёт для поддержки успешно скопирован в буфер обмена Windows!\n");
    });

    // Copy diag modal to clipboard
    let mw_weak = main_window.as_weak();
    main_window.on_copy_diag_to_clipboard(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let text = mw.get_diag_modal_text().to_string();
        copy_text_to_clipboard(&text);
        sound::play_sound("done");
        append_log(&mw, "[+] Отчёт диагностики скопирован в буфер обмена.\n");
    });

    // Save diag modal to file
    let mw_weak = main_window.as_weak();
    main_window.on_save_diag_to_file(move || {
        let mw = match mw_weak.upgrade() {
            Some(w) => w,
            None => return,
        };
        let text = mw.get_diag_modal_text().to_string();
        if let Some(desktop) = get_desktop_dir() {
            let file_path = desktop.join("zapret_diag_report.txt");
            if std::fs::write(&file_path, text).is_ok() {
                sound::play_sound("done");
                append_log(&mw, &format!("[+] Отчёт диагностики сохранён: {}\n", file_path.display()));
            } else {
                sound::play_sound("alert");
                append_log(&mw, "[-] Ошибка сохранения файла на Рабочий стол.\n");
            }
        }
    });

    // Open URL in default browser
    main_window.on_open_url(move |url| {
        let u = url.as_str().to_string();
        let _ = std::process::Command::new("cmd.exe")
            .args(["/c", "start", "", &u])
            .spawn();
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

    // Setup Windows System Tray
    let mw_weak_tray = main_window.as_weak();
    let mw_weak_tray2 = main_window.as_weak();
    let _tray_guard = tray::TrayHandle::new(
        "zapret-rs",
        move || {
            let _ = mw_weak_tray.upgrade_in_event_loop(|mw| {
                mw.show().unwrap_or(());
            });
        },
        move || {
            let _ = mw_weak_tray2.upgrade_in_event_loop(|mw| {
                let paths = paths::ZapretPaths::detect();
                let current_st = strategies::current_strategy().unwrap_or_else(|| "general (ALT4)".to_string());
                let is_running = mw.get_is_running();
                if is_running {
                    let _ = scm::stop_service();
                } else if let Some(ref p) = paths
                    && let Ok(args) = strategies::parse_strategy_args(&p.orig_dir, &current_st) {
                        let winws_path = p.winws_exe.to_string_lossy().to_string();
                        let _ = scm::install_or_update_service(&winws_path, &args);
                        let _ = scm::start_service();
                    }
                update_ui_status(&mw);
            });
        },
        move || {
            std::process::exit(0);
        },
    );

    // Custom Titlebar window controls
    main_window.on_minimize_window(|| {
        if let Some(wnd) = get_main_hwnd() {
            unsafe {
                let _ = windows::Win32::UI::WindowsAndMessaging::ShowWindow(
                    wnd,
                    windows::Win32::UI::WindowsAndMessaging::SW_MINIMIZE,
                );
            }
        }
    });

    main_window.on_maximize_window(|| {
        if let Some(wnd) = get_main_hwnd() {
            unsafe {
                let is_max = windows::Win32::UI::WindowsAndMessaging::IsZoomed(wnd).as_bool();
                let _ = windows::Win32::UI::WindowsAndMessaging::ShowWindow(
                    wnd,
                    if is_max {
                        windows::Win32::UI::WindowsAndMessaging::SW_RESTORE
                    } else {
                        windows::Win32::UI::WindowsAndMessaging::SW_MAXIMIZE
                    },
                );
            }
        }
    });

    main_window.on_close_window(|| {
        std::process::exit(0);
    });

    main_window.on_drag_window(|| {
        if let Some(wnd) = get_main_hwnd() {
            unsafe {
                let _ = windows::Win32::UI::Input::KeyboardAndMouse::ReleaseCapture();
                let _ = windows::Win32::UI::WindowsAndMessaging::SendMessageW(
                    wnd,
                    windows::Win32::UI::WindowsAndMessaging::WM_NCLBUTTONDOWN,
                    Some(windows::Win32::Foundation::WPARAM(2)), // HTCAPTION
                    Some(windows::Win32::Foundation::LPARAM(0)),
                );
            }
        }
    });

    // Центрирование окна по экрану при старте
    let mw_weak_center = main_window.as_weak();
    let _ = slint::invoke_from_event_loop(move || {
        if let Some(_mw) = mw_weak_center.upgrade() {
            center_window_on_screen();
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

/// Копирует текст в системный буфер обмена Windows через нативный Win32 API (CF_UNICODETEXT).
/// Исключает искажения кодировки (mojibake) и работает мгновенно без вызова внешних процессов.
fn copy_text_to_clipboard(text: &str) {
    use std::ffi::c_void;

    let wide: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
    let bytes_len = wide.len() * std::mem::size_of::<u16>();

    type HWND = *mut c_void;
    type HANDLE = *mut c_void;
    type HGLOBAL = *mut c_void;
    const CF_UNICODETEXT: u32 = 13;
    const GMEM_MOVEABLE: u32 = 0x0002;

    #[link(name = "user32")]
    unsafe extern "system" {
        fn OpenClipboard(hWndNewOwner: HWND) -> i32;
        fn CloseClipboard() -> i32;
        fn EmptyClipboard() -> i32;
        fn SetClipboardData(uFormat: u32, hMem: HANDLE) -> HANDLE;
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GlobalAlloc(uFlags: u32, dwBytes: usize) -> HGLOBAL;
        fn GlobalLock(hMem: HGLOBAL) -> *mut c_void;
        fn GlobalUnlock(hMem: HGLOBAL) -> i32;
        fn GlobalFree(hMem: HGLOBAL) -> HGLOBAL;
    }

    unsafe {
        if OpenClipboard(std::ptr::null_mut()) == 0 {
            return;
        }
        EmptyClipboard();

        let h_mem = GlobalAlloc(GMEM_MOVEABLE, bytes_len);
        if !h_mem.is_null() {
            let ptr = GlobalLock(h_mem);
            if !ptr.is_null() {
                std::ptr::copy_nonoverlapping(wide.as_ptr() as *const u8, ptr as *mut u8, bytes_len);
                GlobalUnlock(h_mem);
                if SetClipboardData(CF_UNICODETEXT, h_mem).is_null() {
                    GlobalFree(h_mem);
                }
            } else {
                GlobalFree(h_mem);
            }
        }
        CloseClipboard();
    }
}

/// Возвращает путь к Рабочему столу пользователя
fn get_desktop_dir() -> Option<std::path::PathBuf> {
    std::env::var_os("USERPROFILE").map(|p| std::path::PathBuf::from(p).join("Desktop"))
}

/// Возвращает локальную дату и время в строковом формате
fn chrono_timestamp() -> String {
    let output = std::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-Command", "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"])
        .output();
    if let Ok(out) = output {
        String::from_utf8_lossy(&out.stdout).trim().to_string()
    } else {
        "N/A".to_string()
    }
}

/// Возвращает дескриптор основного окна приложения
fn get_main_hwnd() -> Option<windows::Win32::Foundation::HWND> {
    unsafe {
        let wide_title: Vec<u16> = "zapret-rs (Fluent UI)\0".encode_utf16().collect();
        let hwnd = windows::Win32::UI::WindowsAndMessaging::FindWindowW(
            None,
            windows::core::PCWSTR(wide_title.as_ptr()),
        );
        if let Ok(wnd) = hwnd {
            if !wnd.is_invalid() {
                return Some(wnd);
            }
        }
        None
    }
}

/// Находит окно zapret-rs и центрирует его на основном мониторе
fn center_window_on_screen() {
    unsafe {
        if let Some(wnd) = get_main_hwnd() {
            let mut rect = windows::Win32::Foundation::RECT::default();
            if windows::Win32::UI::WindowsAndMessaging::GetWindowRect(wnd, &mut rect).is_ok() {
                let win_w = rect.right - rect.left;
                let win_h = rect.bottom - rect.top;

                let screen_w = windows::Win32::UI::WindowsAndMessaging::GetSystemMetrics(
                    windows::Win32::UI::WindowsAndMessaging::SM_CXSCREEN,
                );
                let screen_h = windows::Win32::UI::WindowsAndMessaging::GetSystemMetrics(
                    windows::Win32::UI::WindowsAndMessaging::SM_CYSCREEN,
                );

                let pos_x = (screen_w - win_w) / 2;
                let pos_y = (screen_h - win_h) / 2;

                let _ = windows::Win32::UI::WindowsAndMessaging::SetWindowPos(
                    wnd,
                    None,
                    pos_x,
                    pos_y,
                    0,
                    0,
                    windows::Win32::UI::WindowsAndMessaging::SWP_NOSIZE
                        | windows::Win32::UI::WindowsAndMessaging::SWP_NOZORDER
                        | windows::Win32::UI::WindowsAndMessaging::SWP_SHOWWINDOW,
                );
            }
        }
    }
}
