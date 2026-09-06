use airbench_desktop_lib::intake::{
    download_artifact_to_path, fetch_safe_preview, upload_query_file_from_path,
};
use airbench_desktop_lib::node_transport::NodeProfile;
use std::{env, fs, path::PathBuf};

#[tokio::main]
async fn main() {
    match run().await {
        Ok(value) => println!("{}", value),
        Err(error) => {
            println!("{}", serde_json::json!({ "error": error.to_string() }));
            std::process::exit(2);
        }
    }
}

async fn run() -> Result<String, Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let profile_path = args.next().ok_or("expected profile JSON path")?;
    let input_path = PathBuf::from(args.next().ok_or("expected input path")?);
    let output_path = PathBuf::from(args.next().ok_or("expected output path")?);
    let profile: NodeProfile = serde_json::from_str(&fs::read_to_string(profile_path)?)?;
    let manifest = upload_query_file_from_path(profile.clone(), input_path).await?;
    let preview = fetch_safe_preview(profile.clone(), manifest.preview_ref.clone()).await?;
    let receipt =
        download_artifact_to_path(profile, manifest.artifact_ref.clone(), output_path).await?;
    Ok(serde_json::to_string(&serde_json::json!({
        "manifest": manifest,
        "preview": preview,
        "receipt": receipt,
    }))?)
}
