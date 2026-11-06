use windows::Win32::Foundation::CloseHandle;
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS,
};
use windows::Win32::System::Threading::{
    OpenProcess, TerminateProcess, PROCESS_TERMINATE,
};

pub fn is_process_running(image_name: &str) -> bool {
    unsafe {
        let snapshot = match CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) {
            Ok(handle) => handle,
            Err(_) => return false,
        };

        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };

        let target = image_name.to_lowercase();
        let mut found = false;

        if Process32FirstW(snapshot, &mut entry).is_ok() {
            loop {
                let name = String::from_utf16_lossy(&entry.szExeFile);
                let clean_name = name.trim_matches('\0').to_lowercase();
                if clean_name == target {
                    found = true;
                    break;
                }
                if Process32NextW(snapshot, &mut entry).is_err() {
                    break;
                }
            }
        }

        let _ = CloseHandle(snapshot);
        found
    }
}

/// Принудительно завершает все процессы с указанным именем (например, "winws.exe").
/// Возвращает количество успешно завершённых процессов.
pub fn kill_process(image_name: &str) -> usize {
    let mut killed = 0;
    unsafe {
        let snapshot = match CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) {
            Ok(handle) => handle,
            Err(_) => return 0,
        };

        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };

        let target = image_name.to_lowercase();

        if Process32FirstW(snapshot, &mut entry).is_ok() {
            loop {
                let name = String::from_utf16_lossy(&entry.szExeFile);
                let clean_name = name.trim_matches('\0').to_lowercase();
                if clean_name == target {
                    let pid = entry.th32ProcessID;
                    if let Ok(process_handle) = OpenProcess(PROCESS_TERMINATE, false, pid) {
                        if TerminateProcess(process_handle, 1).is_ok() {
                            killed += 1;
                        }
                        let _ = CloseHandle(process_handle);
                    }
                }
                if Process32NextW(snapshot, &mut entry).is_err() {
                    break;
                }
            }
        }

        let _ = CloseHandle(snapshot);
    }
    killed
}

