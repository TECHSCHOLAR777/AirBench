use crate::node_transport::{
    build_client, credential_token, node_url, verify_certificate_pin, NodeProfile,
    NodeTransportError,
};
use rfd::FileDialog;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{path::PathBuf, sync::Mutex};
use tauri::State;
use uuid::Uuid;

const MAX_QUERY_UPLOAD_BYTES: u64 = 100 * 1024 * 1024;
const MAX_NODE_REFERENCE_BYTES: usize = 256;

#[derive(Default)]
pub struct IntakeState {
    selected: Mutex<Option<SelectedPath>>,
}

struct SelectedPath {
    selection_id: String,
    path: PathBuf,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct SelectedFile {
    pub selection_id: String,
    pub file_name: String,
    pub byte_size: u64,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct IntakeManifest {
    pub intake_id: String,
    pub file_name: String,
    pub byte_size: u64,
    pub source_hash: String,
    pub revision_id: String,
    pub media_type: String,
    pub page_count: u32,
    pub ocr_status: String,
    pub vision_status: String,
    pub clearance: String,
    pub taint: String,
    pub preview_ref: String,
    pub artifact_ref: String,
    pub ledger_event_ref: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct SafePreview {
    pub preview_ref: String,
    pub preview_kind: String,
    pub text: String,
    pub source_hash: String,
    pub source_region: String,
    pub confidence: f64,
    pub clearance: String,
    pub taint: String,
    pub ledger_event_ref: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct DownloadReceipt {
    pub artifact_id: String,
    pub destination: String,
    pub content_hash: String,
    pub ledger_event_ref: String,
    pub byte_size: usize,
}

fn validate_file(path: &PathBuf) -> Result<std::fs::Metadata, String> {
    let metadata = std::fs::symlink_metadata(path)
        .map_err(|_| "The selected file is no longer available.".to_string())?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err("The selected intake path is not a regular file.".to_string());
    }
    if metadata.len() > MAX_QUERY_UPLOAD_BYTES {
        return Err("The selected file is larger than the query-upload limit.".to_string());
    }
    Ok(metadata)
}

fn validate_node_reference(reference: &str, label: &str) -> Result<(), String> {
    if reference.is_empty()
        || reference.len() > MAX_NODE_REFERENCE_BYTES
        || reference.contains("..")
        || !reference
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
    {
        return Err(format!(
            "The {label} reference is not an approved Node reference."
        ));
    }
    Ok(())
}

#[tauri::command]
pub fn pick_query_file(state: State<'_, IntakeState>) -> Result<Option<SelectedFile>, String> {
    let Some(path) = FileDialog::new()
        .add_filter(
            "Scanned documents",
            &["pdf", "png", "jpg", "jpeg", "tif", "tiff"],
        )
        .pick_file()
    else {
        return Ok(None);
    };
    let metadata = validate_file(&path)?;
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "The selected file name is not valid Unicode.".to_string())?
        .to_string();
    let selection_id = Uuid::new_v4().to_string();
    *state
        .selected
        .lock()
        .map_err(|_| "The intake selection state is unavailable.")? = Some(SelectedPath {
        selection_id: selection_id.clone(),
        path,
    });
    Ok(Some(SelectedFile {
        selection_id,
        file_name,
        byte_size: metadata.len(),
    }))
}

pub async fn upload_query_file_from_path(
    profile: NodeProfile,
    path: PathBuf,
) -> Result<IntakeManifest, String> {
    let metadata = validate_file(&path)?;
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "The selected file name is not valid Unicode.".to_string())?
        .to_string();
    let token = credential_token(&profile).map_err(String::from)?;
    let bytes = tokio::fs::read(&path)
        .await
        .map_err(|_| "The selected file could not be opened for intake.".to_string())?;
    let part = reqwest::multipart::Part::bytes(bytes)
        .file_name(file_name)
        .mime_str("application/octet-stream")
        .map_err(|_| "The intake media type could not be constructed.")?;
    let form = reqwest::multipart::Form::new()
        .text("intake_mode", "query_upload")
        .text("source_file_size", metadata.len().to_string())
        .part("document", part);
    let response = build_client(&profile)
        .map_err(String::from)?
        .post(node_url(&profile, "/api/v1/intake/query-upload").map_err(String::from)?)
        .header("Accept", "application/json")
        .bearer_auth(token)
        .multipart(form)
        .send()
        .await
        .map_err(|_| "The approved Node intake request failed.".to_string())?;
    verify_certificate_pin(&profile, &response).map_err(String::from)?;
    if !response.status().is_success() {
        return Err(format!(
            "The File Intake Layer returned HTTP {}.",
            response.status().as_u16()
        ));
    }
    response
        .json::<IntakeManifest>()
        .await
        .map_err(|_| "The Node did not return the File Intake manifest schema.".to_string())
}

#[tauri::command]
pub async fn upload_selected_query_file(
    profile: NodeProfile,
    selection_id: String,
    state: State<'_, IntakeState>,
) -> Result<IntakeManifest, String> {
    let selected = state
        .selected
        .lock()
        .map_err(|_| "The intake selection state is unavailable.")?
        .take()
        .ok_or_else(|| "No native file selection is pending.".to_string())?;
    if selected.selection_id != selection_id {
        return Err("The intake selection token does not match.".to_string());
    }
    upload_query_file_from_path(profile, selected.path).await
}

#[tauri::command]
pub async fn fetch_safe_preview(
    profile: NodeProfile,
    preview_ref: String,
) -> Result<SafePreview, String> {
    validate_node_reference(&preview_ref, "preview")?;
    let token = credential_token(&profile).map_err(String::from)?;
    let response = build_client(&profile)
        .map_err(String::from)?
        .get(
            node_url(&profile, &format!("/api/v1/intake/{preview_ref}/preview"))
                .map_err(String::from)?,
        )
        .header("Accept", "application/json")
        .bearer_auth(token)
        .send()
        .await
        .map_err(|_| "The approved Node preview request failed.".to_string())?;
    verify_certificate_pin(&profile, &response).map_err(String::from)?;
    if !response.status().is_success() {
        return Err(format!(
            "The Node preview request returned HTTP {}.",
            response.status().as_u16()
        ));
    }
    response
        .json::<SafePreview>()
        .await
        .map_err(|_| "The Node did not return a safe preview schema.".to_string())
}

pub async fn download_artifact_to_path(
    profile: NodeProfile,
    artifact_id: String,
    destination: PathBuf,
) -> Result<DownloadReceipt, String> {
    validate_node_reference(&artifact_id, "artifact")?;
    let token = credential_token(&profile).map_err(String::from)?;
    let response = build_client(&profile)
        .map_err(String::from)?
        .get(
            node_url(
                &profile,
                &format!("/api/v1/artifacts/{artifact_id}/download"),
            )
            .map_err(String::from)?,
        )
        .header("Accept", "application/octet-stream")
        .bearer_auth(token)
        .send()
        .await
        .map_err(|_| "The approved Node artifact request failed.".to_string())?;
    verify_certificate_pin(&profile, &response).map_err(String::from)?;
    if !response.status().is_success() {
        return Err(format!(
            "The Node denied artifact download with HTTP {}.",
            response.status().as_u16()
        ));
    }
    let expected_hash = response
        .headers()
        .get("x-airbench-artifact-hash")
        .and_then(|value| value.to_str().ok())
        .ok_or_else(|| "The artifact response did not contain a content hash.".to_string())?
        .to_string();
    let ledger_event_ref = response
        .headers()
        .get("x-airbench-ledger-event-ref")
        .and_then(|value| value.to_str().ok())
        .ok_or_else(|| "The artifact response did not contain a ledger reference.".to_string())?
        .to_string();
    let bytes = response
        .bytes()
        .await
        .map_err(|_| "The artifact download was interrupted.".to_string())?;
    let actual_hash = format!("sha256:{}", hex::encode(Sha256::digest(&bytes)));
    if actual_hash != expected_hash {
        return Err("The downloaded artifact hash does not match the Node receipt.".to_string());
    }
    std::fs::write(&destination, &bytes)
        .map_err(|_| "The artifact could not be saved to the selected destination.".to_string())?;
    Ok(DownloadReceipt {
        artifact_id,
        destination: destination.to_string_lossy().to_string(),
        content_hash: actual_hash,
        ledger_event_ref,
        byte_size: bytes.len(),
    })
}

#[tauri::command]
pub async fn download_artifact(
    profile: NodeProfile,
    artifact_id: String,
    suggested_name: String,
) -> Result<DownloadReceipt, String> {
    let safe_name: String = suggested_name
        .chars()
        .filter(|character| character.is_ascii_alphanumeric() || ".-_".contains(*character))
        .collect();
    let file_name = if safe_name.is_empty() {
        format!("airbench-artifact-{artifact_id}.bin")
    } else {
        safe_name
    };
    let destination = FileDialog::new()
        .set_file_name(file_name)
        .save_file()
        .ok_or_else(|| "Artifact save was cancelled.".to_string())?;
    download_artifact_to_path(profile, artifact_id, destination).await
}

#[allow(dead_code)]
fn _keep_error_type_linked(_: NodeTransportError) {}

#[cfg(test)]
mod tests {
    use super::validate_node_reference;

    #[test]
    fn accepts_opaque_node_references_without_fixture_prefixes() {
        assert!(validate_node_reference("intake-7f3c.preview:v2", "preview").is_ok());
        assert!(validate_node_reference("artifact_2026.09:abc", "artifact").is_ok());
    }

    #[test]
    fn rejects_path_traversal_and_unsafe_reference_syntax() {
        for reference in ["", "..", "../preview", "preview\\file", "preview?id=1"] {
            assert!(validate_node_reference(reference, "preview").is_err());
        }
        assert!(validate_node_reference(&"a".repeat(257), "artifact").is_err());
    }
}
