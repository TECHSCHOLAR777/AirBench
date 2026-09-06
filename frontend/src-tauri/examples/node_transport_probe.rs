use airbench_desktop_lib::node_transport::{
    connect_node_profile, fetch_task_events_profile, NodeProfile,
};
use std::{env, fs};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let profile_path = args.next().ok_or("expected a profile JSON path")?;
    let profile: NodeProfile = serde_json::from_str(&fs::read_to_string(profile_path)?)?;
    let mode = args.next().unwrap_or_else(|| "handshake".to_string());
    match if mode == "events" {
        let task_id = args.next().ok_or("expected a task id")?;
        let after_sequence = args.next().unwrap_or_else(|| "0".to_string()).parse()?;
        fetch_task_events_profile(profile, task_id, after_sequence)
            .await
            .map(|batch| serde_json::to_value(batch).expect("serialize event batch"))
    } else {
        connect_node_profile(profile)
            .await
            .map(|result| serde_json::to_value(result).expect("serialize connection result"))
    } {
        Ok(result) => println!("{}", serde_json::to_string(&result)?),
        Err(error) => {
            println!("{}", serde_json::json!({ "error": error }));
            std::process::exit(2);
        }
    }
    Ok(())
}
