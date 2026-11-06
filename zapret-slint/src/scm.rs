use std::thread;
use std::time::Duration;
use windows::core::{w, PCWSTR};
use windows::Win32::System::Services::{
    ChangeServiceConfigW, CloseServiceHandle, ControlService, CreateServiceW, DeleteService,
    OpenSCManagerW, OpenServiceW, QueryServiceStatus, StartServiceW, SC_HANDLE, SC_MANAGER_ALL_ACCESS,
    SC_MANAGER_CONNECT, SERVICE_ALL_ACCESS, SERVICE_AUTO_START, SERVICE_CONTROL_STOP,
    SERVICE_ERROR_NORMAL, SERVICE_QUERY_STATUS, SERVICE_RUNNING, SERVICE_START, SERVICE_STATUS,
    SERVICE_STOP, SERVICE_STOPPED, SERVICE_WIN32_OWN_PROCESS,
};

pub const SERVICE_NAME: windows::core::PCWSTR = w!("zapret");
pub const SERVICE_DISPLAY: windows::core::PCWSTR = w!("zapret");

struct AutoHandle(SC_HANDLE);

impl Drop for AutoHandle {
    fn drop(&mut self) {
        if !self.0.is_invalid() {
            unsafe {
                let _ = CloseServiceHandle(self.0);
            }
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceState {
    Running,
    Stopped,
    NotInstalled,
    Other(u32),
}

impl ServiceState {
    pub fn as_str(&self) -> &'static str {
        match self {
            ServiceState::Running => "Работает",
            ServiceState::Stopped => "Остановлена",
            ServiceState::NotInstalled => "Не установлена",
            ServiceState::Other(_) => "В процессе...",
        }
    }
}

pub fn query_service_status() -> ServiceState {
    query_named_service("zapret")
}

pub fn query_named_service(name: &str) -> ServiceState {
    let wide: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
    unsafe {
        let scm = match OpenSCManagerW(None, None, SC_MANAGER_CONNECT) {
            Ok(h) => AutoHandle(h),
            Err(_) => return ServiceState::NotInstalled,
        };

        let service = match OpenServiceW(scm.0, PCWSTR(wide.as_ptr()), SERVICE_QUERY_STATUS) {
            Ok(h) => AutoHandle(h),
            Err(_) => return ServiceState::NotInstalled,
        };

        let mut status = SERVICE_STATUS::default();
        if QueryServiceStatus(service.0, &mut status).is_ok() {
            match status.dwCurrentState {
                SERVICE_RUNNING => ServiceState::Running,
                SERVICE_STOPPED => ServiceState::Stopped,
                s => ServiceState::Other(s.0),
            }
        } else {
            ServiceState::NotInstalled
        }
    }
}

pub fn is_service_running(name: &str) -> bool {
    query_named_service(name) == ServiceState::Running
}

pub fn start_service() -> Result<(), String> {
    unsafe {
        let scm = AutoHandle(
            OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
                .map_err(|e| format!("Ошибка открытия диспетчера служб: {e}"))?,
        );

        let service = AutoHandle(
            OpenServiceW(scm.0, SERVICE_NAME, SERVICE_START)
                .map_err(|e| format!("Служба zapret не найдена или нет прав: {e}"))?,
        );

        StartServiceW(service.0, None)
            .map_err(|e| format!("Не удалось запустить службу (нужны права админа): {e}"))
    }
}

/// Останавливает службу и ждёт перехода в статус SERVICE_STOPPED (до 10 секунд).
pub fn stop_service() -> Result<(), String> {
    unsafe {
        let scm = AutoHandle(
            OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
                .map_err(|e| format!("Ошибка открытия диспетчера служб: {e}"))?,
        );

        let service = AutoHandle(
            OpenServiceW(scm.0, SERVICE_NAME, SERVICE_STOP | SERVICE_QUERY_STATUS)
                .map_err(|e| format!("Служба zapret не найдена: {e}"))?,
        );

        let mut status = SERVICE_STATUS::default();
        let _ = ControlService(service.0, SERVICE_CONTROL_STOP, &mut status);

        for _ in 0..20 {
            let mut current_status = SERVICE_STATUS::default();
            if QueryServiceStatus(service.0, &mut current_status).is_ok() {
                if current_status.dwCurrentState == SERVICE_STOPPED {
                    return Ok(());
                }
            } else {
                return Ok(());
            }
            thread::sleep(Duration::from_millis(500));
        }

        Ok(())
    }
}

pub fn delete_service_named(name: &str) -> Result<(), String> {
    let wide: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
    unsafe {
        let scm = AutoHandle(
            OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
                .map_err(|e| format!("Ошибка открытия диспетчера служб: {e}"))?,
        );

        let service = AutoHandle(
            OpenServiceW(
                scm.0,
                PCWSTR(wide.as_ptr()),
                windows::Win32::System::Services::SERVICE_ALL_ACCESS,
            )
                .map_err(|e| format!("Служба {name} не найдена: {e}"))?,
        );

        let mut status = SERVICE_STATUS::default();
        let _ = ControlService(service.0, SERVICE_CONTROL_STOP, &mut status);

        DeleteService(service.0)
            .map_err(|e| format!("Не удалось удалить службу {name}: {e}"))
    }
}

/// Устанавливает или обновляет конфигурацию службы zapret с указанным binPath (exe + args).
/// Если служба уже есть — обновляет через ChangeServiceConfigW.
/// Если службы нет — создаёт через CreateServiceW со стартом SERVICE_AUTO_START.
pub fn install_or_update_service(exe_path: &str, exe_args: &str) -> Result<(), String> {
    let bin_path_full = format!("\"{exe_path}\" {exe_args}");
    let bin_path_wide: Vec<u16> = bin_path_full.encode_utf16().chain(std::iter::once(0)).collect();

    unsafe {
        let scm = AutoHandle(
            OpenSCManagerW(None, None, SC_MANAGER_ALL_ACCESS)
                .map_err(|e| format!("Не удалось открыть SCM с полным доступом (нужен запуск от Администратора): {e}"))?,
        );

        // Проверяем, существует ли уже служба
        if let Ok(svc_h) = OpenServiceW(scm.0, SERVICE_NAME, SERVICE_ALL_ACCESS) {
            let service = AutoHandle(svc_h);
            ChangeServiceConfigW(
                service.0,
                SERVICE_WIN32_OWN_PROCESS,
                SERVICE_AUTO_START,
                SERVICE_ERROR_NORMAL,
                PCWSTR(bin_path_wide.as_ptr()),
                PCWSTR::null(),
                None,
                PCWSTR::null(),
                PCWSTR::null(),
                PCWSTR::null(),
                PCWSTR::null(),
            )
            .map_err(|e| format!("Не удалось обновить параметры службы в SCM: {e}"))?;
            Ok(())
        } else {
            // Создаём новую службу
            let created = CreateServiceW(
                scm.0,
                SERVICE_NAME,
                SERVICE_DISPLAY,
                SERVICE_ALL_ACCESS,
                SERVICE_WIN32_OWN_PROCESS,
                SERVICE_AUTO_START,
                SERVICE_ERROR_NORMAL,
                PCWSTR(bin_path_wide.as_ptr()),
                PCWSTR::null(),
                None,
                PCWSTR::null(),
                PCWSTR::null(),
                PCWSTR::null(),
            );

            match created {
                Ok(h) => {
                    let _ = AutoHandle(h);
                    Ok(())
                }
                Err(e) => Err(format!("Не удалось создать службу zapret: {e}")),
            }
        }
    }
}
