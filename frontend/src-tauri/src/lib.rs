#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

pub mod intake;
pub mod node_transport;

pub fn run() {
    tauri::Builder::default()
        .manage(intake::IntakeState::default())
        .invoke_handler(tauri::generate_handler![
            node_transport::connect_node,
            node_transport::fetch_task_events,
            intake::pick_query_file,
            intake::upload_selected_query_file,
            intake::fetch_safe_preview,
            intake::download_artifact
        ])
        .run(tauri::generate_context!())
        .expect("error while running AirBench desktop application");
}
