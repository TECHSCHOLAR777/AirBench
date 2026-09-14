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
            node_transport::fetch_domain_pack,
            node_transport::fetch_task_events,
            node_transport::fetch_task_snapshot,
            node_transport::fetch_task_plan,
            node_transport::fetch_task_artifact_review,
            node_transport::fetch_task_route_trace,
            node_transport::create_task,
            node_transport::send_task_command,
            node_transport::fetch_node_hardware,
            node_transport::fetch_node_model_serving,
            node_transport::fetch_task_consistency,
            node_transport::post_consistency_evaluate,
            node_transport::post_consistency_justify,
            node_transport::fetch_task_autonomy,
            node_transport::post_autonomy_authorize,
            node_transport::fetch_model_qualification,
            node_transport::fetch_qualification_roster,
            node_transport::fetch_knowledge_status,
            node_transport::search_knowledge,
            node_transport::query_knowledge_graph,
            node_transport::ingest_knowledge_folder,
            intake::pick_query_file,
            intake::upload_selected_query_file,
            intake::fetch_safe_preview,
            intake::fetch_intake_status,
            intake::fetch_artifact_preview,
            intake::download_artifact
        ])
        .run(tauri::generate_context!())
        .expect("error while running AirBench desktop application");
}
