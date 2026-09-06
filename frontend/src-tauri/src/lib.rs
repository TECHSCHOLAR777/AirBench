#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod node_transport;

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![node_transport::connect_node])
        .run(tauri::generate_context!())
        .expect("error while running AirBench desktop application");
}
