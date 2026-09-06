#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

pub mod intake;
pub mod node_transport;

pub fn run() {
    let builder = tauri::Builder::default();

    #[cfg(feature = "wdio")]
    let builder = builder
        .plugin(tauri_plugin_wdio::init())
        .plugin(tauri_plugin_wdio_webdriver::init());

    builder
        .manage(intake::IntakeState::default())
        .invoke_handler(tauri::generate_handler![
            node_transport::list_approved_node_profiles,
            node_transport::connect_node,
            node_transport::fetch_task_events,
            intake::pick_query_file,
            intake::upload_selected_query_file,
            intake::fetch_safe_preview,
            intake::fetch_artifact_preview,
            intake::download_artifact
        ])
        .run(tauri::generate_context!())
        .expect("error while running AirBench desktop application");
}
