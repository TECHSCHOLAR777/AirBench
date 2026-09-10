use airbench_desktop_lib::intake::{
    download_artifact_to_path, fetch_artifact_preview_from_profile,
};
use airbench_desktop_lib::node_transport::{
    connect_node_profile, create_task_profile, fetch_task_artifact_review_profile,
    fetch_task_events_profile, fetch_task_plan_profile, fetch_task_route_trace_profile,
    fetch_task_snapshot_profile, send_task_command_profile, NodeCommandEnvelope, NodeProfile,
};
use std::{env, fs, path::PathBuf};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let profile_path = args.next().ok_or("expected a profile JSON path")?;
    let profile: NodeProfile = serde_json::from_str(&fs::read_to_string(profile_path)?)?;
    let mode = args.next().unwrap_or_else(|| "handshake".to_string());
    let result = match mode.as_str() {
        "events" => {
            let task_id = args.next().ok_or("expected a task id")?;
            let after_sequence = args.next().unwrap_or_else(|| "0".to_string()).parse()?;
            fetch_task_events_profile(profile, task_id, after_sequence)
                .await
                .map(|batch| serde_json::to_value(batch).expect("serialize event batch"))
        }
        "snapshot" => {
            let task_id = args.next().ok_or("expected a task id")?;
            fetch_task_snapshot_profile(profile, task_id)
                .await
                .map(|snapshot| serde_json::to_value(snapshot).expect("serialize task snapshot"))
        }
        "plan" => {
            let task_id = args.next().ok_or("expected a task id")?;
            fetch_task_plan_profile(profile, task_id)
                .await
                .map(|plan| serde_json::to_value(plan).expect("serialize task plan"))
        }
        "route-trace" => {
            let task_id = args.next().ok_or("expected a task id")?;
            fetch_task_route_trace_profile(profile, task_id)
                .await
                .map(|trace| serde_json::to_value(trace).expect("serialize route trace"))
        }
        "artifact-review" => {
            let task_id = args.next().ok_or("expected a task id")?;
            fetch_task_artifact_review_profile(profile, task_id)
                .await
                .map(|review| serde_json::to_value(review).expect("serialize artifact review"))
        }
        "artifact-preview" => {
            let artifact_id = args.next().ok_or("expected an artifact id")?;
            fetch_artifact_preview_from_profile(profile, artifact_id)
                .await
                .map(|preview| serde_json::to_value(preview).expect("serialize artifact preview"))
        }
        "artifact-download" => {
            let artifact_id = args.next().ok_or("expected an artifact id")?;
            let output_path = args.next().ok_or("expected an output path")?;
            download_artifact_to_path(profile, artifact_id, PathBuf::from(output_path))
                .await
                .map(|receipt| serde_json::to_value(receipt).expect("serialize download receipt"))
        }
        "create" => {
            let command_path = args.next().ok_or("expected a command JSON path")?;
            let command: NodeCommandEnvelope =
                serde_json::from_str(&fs::read_to_string(command_path)?)?;
            create_task_profile(profile, command)
                .await
                .map(|response| serde_json::to_value(response).expect("serialize create response"))
        }
        "command" => {
            let command_path = args.next().ok_or("expected a command JSON path")?;
            let command: NodeCommandEnvelope =
                serde_json::from_str(&fs::read_to_string(command_path)?)?;
            send_task_command_profile(profile, command)
                .await
                .map(|response| serde_json::to_value(response).expect("serialize command response"))
        }
        _ => connect_node_profile(profile)
            .await
            .map_err(|error| error.to_string())
            .map(|result| serde_json::to_value(result).expect("serialize connection result")),
    };
    match result {
        Ok(result) => println!("{}", serde_json::to_string(&result)?),
        Err(error) => {
            println!("{}", serde_json::json!({ "error": error }));
            std::process::exit(2);
        }
    }
    Ok(())
}
