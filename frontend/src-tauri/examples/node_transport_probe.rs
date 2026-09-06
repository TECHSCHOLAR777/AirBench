use airbench_desktop_lib::node_transport::{
    connect_node_profile, create_task_profile, fetch_task_events_profile,
    fetch_task_plan_profile, fetch_task_snapshot_profile, send_task_command_profile,
    NodeCommandEnvelope, NodeProfile,
};
use std::{env, fs};

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
        "create" => {
            let command_path = args.next().ok_or("expected a command JSON path")?;
            let command: NodeCommandEnvelope = serde_json::from_str(&fs::read_to_string(command_path)?)?;
            create_task_profile(profile, command)
                .await
                .map(|response| serde_json::to_value(response).expect("serialize create response"))
        }
        "command" => {
            let command_path = args.next().ok_or("expected a command JSON path")?;
            let command: NodeCommandEnvelope = serde_json::from_str(&fs::read_to_string(command_path)?)?;
            send_task_command_profile(profile, command)
                .await
                .map(|response| serde_json::to_value(response).expect("serialize command response"))
        }
        _ => connect_node_profile(profile)
            .await
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
