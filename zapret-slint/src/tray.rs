use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use windows::core::{w, PCWSTR};
use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, WPARAM};
use windows::Win32::UI::Shell::{
    Shell_NotifyIconW, NIF_ICON, NIF_MESSAGE, NIF_TIP, NIM_ADD, NIM_DELETE, NOTIFYICONDATAW,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CreatePopupMenu, CreateWindowExW, DefWindowProcW, DestroyMenu, DispatchMessageW, GetCursorPos,
    GetMessageW, InsertMenuW, LoadIconW, PostMessageW, PostQuitMessage, RegisterClassExW,
    SetForegroundWindow, TrackPopupMenu, TranslateMessage, IDI_APPLICATION, MF_BYPOSITION,
    MF_SEPARATOR, MF_STRING, MSG, TPM_BOTTOMALIGN, TPM_LEFTALIGN, TPM_RIGHTBUTTON, WM_APP,
    WM_COMMAND, WM_DESTROY, WM_LBUTTONDBLCLK, WM_LBUTTONUP, WM_RBUTTONUP, WNDCLASSEXW,
};

pub const WM_TRAY_CALLBACK: u32 = WM_APP + 101;
pub const ID_TRAY_OPEN: usize = 1001;
pub const ID_TRAY_START_STOP: usize = 1002;
pub const ID_TRAY_EXIT: usize = 1003;

pub struct TrayHandle {
    hwnd_val: usize,
    stopped: Arc<AtomicBool>,
}

impl TrayHandle {
    pub fn new<FOpen, FToggle, FExit>(
        tooltip: &str,
        on_open: FOpen,
        on_toggle_service: FToggle,
        on_exit: FExit,
    ) -> Option<Self>
    where
        FOpen: Fn() + Send + Sync + 'static,
        FToggle: Fn() + Send + Sync + 'static,
        FExit: Fn() + Send + Sync + 'static,
    {
        let stopped = Arc::new(AtomicBool::new(false));
        let tooltip_string = tooltip.to_string();

        let (tx, rx) = std::sync::mpsc::channel();

        let stopped_clone = stopped.clone();
        thread::spawn(move || {
            let class_name = w!("ZapretTrayClass");
            unsafe {
                let wnd_class = WNDCLASSEXW {
                    cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                    lpfnWndProc: Some(tray_wnd_proc),
                    lpszClassName: class_name,
                    ..Default::default()
                };
                let _ = RegisterClassExW(&wnd_class);

                let hwnd = CreateWindowExW(
                    Default::default(),
                    class_name,
                    w!("zapret_tray_helper"),
                    Default::default(),
                    0,
                    0,
                    0,
                    0,
                    None,
                    None,
                    None,
                    None,
                );

                if hwnd.is_err() {
                    let _ = tx.send(None);
                    return;
                }
                let hwnd = hwnd.unwrap();

                // Setup tray icon: load custom application icon (resource ID 1) from this executable module
                let hinstance = windows::Win32::System::LibraryLoader::GetModuleHandleW(None).unwrap_or_default();
                let icon = LoadIconW(Some(hinstance.into()), PCWSTR(1 as *const u16))
                    .unwrap_or_else(|_| LoadIconW(None, IDI_APPLICATION).unwrap_or_default());
                let mut nid = NOTIFYICONDATAW {
                    cbSize: std::mem::size_of::<NOTIFYICONDATAW>() as u32,
                    hWnd: hwnd,
                    uID: 1,
                    uFlags: NIF_MESSAGE | NIF_ICON | NIF_TIP,
                    uCallbackMessage: WM_TRAY_CALLBACK,
                    hIcon: icon,
                    ..Default::default()
                };

                let tip_wchars: Vec<u16> = tooltip_string.encode_utf16().chain(std::iter::once(0)).collect();
                let len = tip_wchars.len().min(nid.szTip.len());
                nid.szTip[..len].copy_from_slice(&tip_wchars[..len]);

                let _ = Shell_NotifyIconW(NIM_ADD, &nid);

                // Store callbacks in user data
                let callbacks = Box::new(TrayCallbacks {
                    on_open: Box::new(on_open),
                    on_toggle: Box::new(on_toggle_service),
                    on_exit: Box::new(on_exit),
                });
                windows::Win32::UI::WindowsAndMessaging::SetWindowLongPtrW(
                    hwnd,
                    windows::Win32::UI::WindowsAndMessaging::GWLP_USERDATA,
                    Box::into_raw(callbacks) as isize,
                );

                let _ = tx.send(Some(hwnd.0 as usize));

                let mut msg = MSG::default();
                while !stopped_clone.load(Ordering::SeqCst) && GetMessageW(&mut msg, None, 0, 0).as_bool() {
                    let _ = TranslateMessage(&msg);
                    DispatchMessageW(&msg);
                }

                let _ = Shell_NotifyIconW(NIM_DELETE, &nid);
            }
        });

        let hwnd_val = rx.recv().ok()??;
        Some(TrayHandle { hwnd_val, stopped })
    }
}

impl Drop for TrayHandle {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::SeqCst);
        unsafe {
            let hwnd = HWND(self.hwnd_val as *mut _);
            let _ = PostMessageW(
                Some(hwnd),
                WM_DESTROY,
                WPARAM(0),
                LPARAM(0),
            );
        }
    }
}

struct TrayCallbacks {
    on_open: Box<dyn Fn() + Send + Sync>,
    on_toggle: Box<dyn Fn() + Send + Sync>,
    on_exit: Box<dyn Fn() + Send + Sync>,
}

unsafe extern "system" fn tray_wnd_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_TRAY_CALLBACK => {
            let event = (lparam.0 & 0xffff) as u32;
            unsafe {
                let ptr = windows::Win32::UI::WindowsAndMessaging::GetWindowLongPtrW(
                    hwnd,
                    windows::Win32::UI::WindowsAndMessaging::GWLP_USERDATA,
                ) as *mut TrayCallbacks;

                if !ptr.is_null() {
                    let cb = &*ptr;
                    if event == WM_LBUTTONUP || event == WM_LBUTTONDBLCLK {
                        (cb.on_open)();
                    } else if event == WM_RBUTTONUP {
                        let mut pt = POINT::default();
                        let _ = GetCursorPos(&mut pt);
                        let hmenu = CreatePopupMenu().unwrap_or_default();
                        if !hmenu.is_invalid() {
                            let _ = InsertMenuW(
                                hmenu,
                                0,
                                MF_BYPOSITION | MF_STRING,
                                ID_TRAY_OPEN,
                                w!("Открыть zapret-simple"),
                            );
                            let _ = InsertMenuW(
                                hmenu,
                                1,
                                MF_BYPOSITION | MF_STRING,
                                ID_TRAY_START_STOP,
                                w!("Запустить / Перезапустить службу"),
                            );
                            let _ = InsertMenuW(hmenu, 2, MF_BYPOSITION | MF_SEPARATOR, 0, PCWSTR::null());
                            let _ = InsertMenuW(
                                hmenu,
                                3,
                                MF_BYPOSITION | MF_STRING,
                                ID_TRAY_EXIT,
                                w!("Выход"),
                            );

                            let _ = SetForegroundWindow(hwnd);
                            let _ = TrackPopupMenu(
                                hmenu,
                                TPM_RIGHTBUTTON | TPM_LEFTALIGN | TPM_BOTTOMALIGN,
                                pt.x,
                                pt.y,
                                Some(0),
                                hwnd,
                                None,
                            );
                            let _ = DestroyMenu(hmenu);
                        }
                    }
                }
            }
            LRESULT(0)
        }
        WM_COMMAND => {
            let id = wparam.0 & 0xffff;
            unsafe {
                let ptr = windows::Win32::UI::WindowsAndMessaging::GetWindowLongPtrW(
                    hwnd,
                    windows::Win32::UI::WindowsAndMessaging::GWLP_USERDATA,
                ) as *mut TrayCallbacks;
                if !ptr.is_null() {
                    let cb = &*ptr;
                    match id {
                        ID_TRAY_OPEN => (cb.on_open)(),
                        ID_TRAY_START_STOP => (cb.on_toggle)(),
                        ID_TRAY_EXIT => (cb.on_exit)(),
                        _ => {}
                    }
                }
            }
            LRESULT(0)
        }
        WM_DESTROY => {
            unsafe {
                PostQuitMessage(0);
            }
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
