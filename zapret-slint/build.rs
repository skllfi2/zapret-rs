fn main() {
    slint_build::compile("ui/appwindow.slint").unwrap();
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut res = winres::WindowsResource::new();
        res.set_icon("assets/app.ico");
        if let Err(e) = res.compile() {
            eprintln!("Warning: Failed to compile windows resource: {e}");
        }
    }
}
