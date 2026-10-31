use windows::core::{w, PCWSTR};
use windows::Win32::System::Services::{
    CloseServiceHandle, ControlService, DeleteService, OpenSCManagerW, OpenServiceW,
    QueryServiceStatus, StartServiceW, SC_HANDLE, SC_MANAGER_CONNECT, SERVICE_CONTROL_STOP,
    SERVICE_QUERY_STATUS, SERVICE_RUNNING, SERVICE_START, SERVICE_STATUS, SERVICE_STOP,
    SERVICE_STOPPED,
};

pub const SERVICE_NAME: windows::core::PCWSTR = w!("zapret");

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

pub fn stop_service() -> Result<(), String> {
    unsafe {
        let scm = AutoHandle(
            OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
                .map_err(|e| format!("Ошибка открытия диспетчера служб: {e}"))?,
        );

        let service = AutoHandle(
            OpenServiceW(scm.0, SERVICE_NAME, SERVICE_STOP)
                .map_err(|e| format!("Служба zapret не найдена: {e}"))?,
        );

        let mut status = SERVICE_STATUS::default();
        ControlService(service.0, SERVICE_CONTROL_STOP, &mut status)
            .map_err(|e| format!("Не удалось остановить службу: {e}"))?;
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
