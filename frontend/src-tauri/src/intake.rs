use crate::node_transport::{
    approved_profile_by_id, build_client, credential_token, node_url, verify_certificate_pin,
    NodeProfile, NodeTransportError,
};
use rfd::FileDialog;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{path::PathBuf, sync::Mutex};
use tauri::State;
use uuid::Uuid;

const MAX_QUERY_UPLOAD_BYTES: u64 = 100 * 1024 * 1024;
const MAX_NODE_REFERENCE_BYTES: usize = 256;
const MAX_PREVIEW_TEXT_BYTES: usize = 10 * 1024 * 1024;

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

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct ArtifactPreviewBlock {
    pub kind: String,
    pub text: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct ArtifactPreview {
    pub artifact_id: String,
    pub preview_kind: String,
    pub title: String,
    pub blocks: Vec<ArtifactPreviewBlock>,
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

fn validate_sha256(value: &str, label: &str) -> Result<(), String> {
    let valid = value
        .strip_prefix("sha256:")
        .map(|digest| digest.len() == 64 && digest.bytes().all(|byte| byte.is_ascii_hexdigit()))
        == Some(true);
    if !valid {
        return Err(format!(
            "The Node {label} is not a valid SHA-256 reference."
        ));
    }
    Ok(())
}

fn validate_clearance(value: &str) -> Result<(), String> {
    if !matches!(value, "public" | "internal" | "restricted" | "secret") {
        return Err("The Node returned an invalid clearance value.".to_string());
    }
    Ok(())
}

fn validate_taint(value: &str) -> Result<(), String> {
    if !matches!(value, "clean" | "untrusted" | "contaminated") {
        return Err("The Node returned an invalid taint value.".to_string());
    }
    Ok(())
}

fn validate_status(value: &str, label: &str) -> Result<(), String> {
    if !matches!(
        value,
        "pending" | "running" | "completed" | "failed" | "not_applicable" | "unavailable"
    ) {
        return Err(format!("The Node returned an invalid {label} status."));
    }
    Ok(())
}

fn validate_intake_manifest(manifest: &IntakeManifest) -> Result<(), String> {
    validate_node_reference(&manifest.intake_id, "intake")?;
    validate_node_reference(&manifest.revision_id, "revision")?;
    validate_node_reference(&manifest.preview_ref, "preview")?;
    validate_node_reference(&manifest.artifact_ref, "artifact")?;
    validate_node_reference(&manifest.ledger_event_ref, "ledger event")?;
    if manifest.file_name.is_empty()
        || manifest.file_name.len() > 255
        || manifest.file_name.contains('/')
        || manifest.file_name.contains('\\')
        || manifest.file_name.contains('\0')
    {
        return Err("The Node returned an invalid intake file name.".to_string());
    }
    if manifest.byte_size == 0 || manifest.byte_size > MAX_QUERY_UPLOAD_BYTES {
        return Err("The Node returned an invalid intake byte size.".to_string());
    }
    if manifest.page_count == 0 {
        return Err("The Node returned an invalid intake page count.".to_string());
    }
    if manifest.media_type.trim().is_empty() || manifest.media_type.contains('\0') {
        return Err("The Node returned an invalid intake media type.".to_string());
    }
    validate_sha256(&manifest.source_hash, "source hash")?;
    validate_status(&manifest.ocr_status, "OCR")?;
    validate_status(&manifest.vision_status, "vision")?;
    validate_clearance(&manifest.clearance)?;
    validate_taint(&manifest.taint)
}

fn validate_safe_preview(preview: &SafePreview, requested_ref: &str) -> Result<(), String> {
    validate_node_reference(requested_ref, "preview")?;
    if preview.preview_ref != requested_ref {
        return Err("The Node preview reference does not match the requested preview.".to_string());
    }
    if !matches!(
        preview.preview_kind.as_str(),
        "text" | "image" | "pdf_page" | "table"
    ) {
        return Err("The Node returned an unsupported safe preview kind.".to_string());
    }
    if preview.text.as_bytes().len() > MAX_PREVIEW_TEXT_BYTES || preview.text.contains('\0') {
        return Err("The Node preview text exceeds the safe preview limit.".to_string());
    }
    validate_sha256(&preview.source_hash, "preview source hash")?;
    if preview.source_region.trim().is_empty() || preview.source_region.contains('\0') {
        return Err("The Node returned an invalid preview source region.".to_string());
    }
    if !preview.confidence.is_finite() || !(0.0..=1.0).contains(&preview.confidence) {
        return Err("The Node returned an invalid preview confidence.".to_string());
    }
    validate_clearance(&preview.clearance)?;
    validate_taint(&preview.taint)?;
    validate_node_reference(&preview.ledger_event_ref, "ledger event")
}

fn validate_artifact_preview(
    preview: &ArtifactPreview,
    requested_artifact_id: &str,
) -> Result<(), String> {
    validate_node_reference(requested_artifact_id, "artifact")?;
    if preview.artifact_id != requested_artifact_id {
        return Err("The Node artifact preview does not match the requested artifact.".to_string());
    }
    if !matches!(
        preview.preview_kind.as_str(),
        "structured_document" | "pdf" | "text"
    ) {
        return Err("The Node returned an unsupported artifact preview kind.".to_string());
    }
    if preview.title.trim().is_empty()
        || preview.title.len() > 255
        || preview.title.contains('\0')
        || preview.blocks.is_empty()
        || preview.blocks.len() > 1_024
    {
        return Err("The Node returned an invalid artifact preview.".to_string());
    }
    for block in &preview.blocks {
        if block.kind.trim().is_empty()
            || block.kind.len() > 64
            || block.kind.contains('\0')
            || block.text.len() > MAX_PREVIEW_TEXT_BYTES
            || block.text.contains('\0')
        {
            return Err("The Node returned an unsafe artifact preview block.".to_string());
        }
    }
    validate_clearance(&preview.clearance)?;
    validate_taint(&preview.taint)?;
    validate_node_reference(&preview.ledger_event_ref, "ledger event")
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
    if metadata.len() != bytes.len() as u64 {
        return Err(
            "The selected file changed while it was being prepared for intake.".to_string(),
        );
    }
    let expected_source_hash = format!("sha256:{}", hex::encode(Sha256::digest(&bytes)));
    let part = reqwest::multipart::Part::bytes(bytes)
        .file_name(file_name.clone())
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
    let manifest = response
        .json::<IntakeManifest>()
        .await
        .map_err(|_| "The Node did not return the File Intake manifest schema.".to_string())?;
    validate_intake_manifest(&manifest)?;
    if manifest.file_name != file_name || manifest.byte_size != metadata.len() {
        return Err("The Node intake manifest does not match the uploaded file.".to_string());
    }
    if manifest.source_hash != expected_source_hash {
        return Err("The Node intake source hash does not match the uploaded file.".to_string());
    }
    Ok(manifest)
}

#[tauri::command]
pub async fn upload_selected_query_file(
    app: tauri::AppHandle,
    profile_id: String,
    selection_id: String,
    state: State<'_, IntakeState>,
) -> Result<IntakeManifest, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
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

pub async fn fetch_safe_preview_from_profile(
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
    let preview = response
        .json::<SafePreview>()
        .await
        .map_err(|_| "The Node did not return a safe preview schema.".to_string())?;
    validate_safe_preview(&preview, &preview_ref)?;
    Ok(preview)
}

#[tauri::command]
pub async fn fetch_safe_preview(
    app: tauri::AppHandle,
    profile_id: String,
    preview_ref: String,
) -> Result<SafePreview, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_safe_preview_from_profile(profile, preview_ref).await
}

pub async fn fetch_artifact_preview_from_profile(
    profile: NodeProfile,
    artifact_id: String,
) -> Result<ArtifactPreview, String> {
    validate_node_reference(&artifact_id, "artifact")?;
    let token = credential_token(&profile).map_err(String::from)?;
    let response = build_client(&profile)
        .map_err(String::from)?
        .get(
            node_url(
                &profile,
                &format!("/api/v1/artifacts/{artifact_id}/preview"),
            )
            .map_err(String::from)?,
        )
        .header("Accept", "application/json")
        .bearer_auth(token)
        .send()
        .await
        .map_err(|_| "The approved Node artifact preview request failed.".to_string())?;
    verify_certificate_pin(&profile, &response).map_err(String::from)?;
    if !response.status().is_success() {
        return Err(format!(
            "The Node artifact preview request returned HTTP {}.",
            response.status().as_u16()
        ));
    }
    let preview = response
        .json::<ArtifactPreview>()
        .await
        .map_err(|_| "The Node did not return an artifact preview schema.".to_string())?;
    validate_artifact_preview(&preview, &artifact_id)?;
    Ok(preview)
}

#[tauri::command]
pub async fn fetch_artifact_preview(
    app: tauri::AppHandle,
    profile_id: String,
    artifact_id: String,
) -> Result<ArtifactPreview, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_artifact_preview_from_profile(profile, artifact_id).await
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
    validate_sha256(&expected_hash, "artifact hash")?;
    validate_node_reference(&ledger_event_ref, "ledger event")?;
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
    app: tauri::AppHandle,
    profile_id: String,
    artifact_id: String,
    suggested_name: String,
) -> Result<DownloadReceipt, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
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
    use super::{
        validate_artifact_preview, validate_intake_manifest, validate_node_reference,
        validate_safe_preview, ArtifactPreview, ArtifactPreviewBlock, IntakeManifest, SafePreview,
    };

    fn valid_manifest() -> IntakeManifest {
        IntakeManifest {
            intake_id: "intake-1".to_string(),
            file_name: "report.pdf".to_string(),
            byte_size: 1,
            source_hash: format!("sha256:{}", "a".repeat(64)),
            revision_id: "revision-1".to_string(),
            media_type: "application/pdf".to_string(),
            page_count: 1,
            ocr_status: "completed".to_string(),
            vision_status: "completed".to_string(),
            clearance: "restricted".to_string(),
            taint: "untrusted".to_string(),
            preview_ref: "preview-1".to_string(),
            artifact_ref: "artifact-1".to_string(),
            ledger_event_ref: "ledger-1".to_string(),
        }
    }

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

    #[test]
    fn intake_manifest_validation_rejects_inconsistent_or_untrusted_shapes() {
        let mut manifest = valid_manifest();
        assert!(validate_intake_manifest(&manifest).is_ok());

        manifest.source_hash = "sha256:not-a-digest".to_string();
        assert!(validate_intake_manifest(&manifest).is_err());
        manifest = valid_manifest();
        manifest.page_count = 0;
        assert!(validate_intake_manifest(&manifest).is_err());
        manifest = valid_manifest();
        manifest.file_name = "..\\secret.pdf".to_string();
        assert!(validate_intake_manifest(&manifest).is_err());
    }

    #[test]
    fn safe_preview_validation_preserves_reference_and_provenance_requirements() {
        let preview = SafePreview {
            preview_ref: "preview-1".to_string(),
            preview_kind: "text".to_string(),
            text: "untrusted preview data".to_string(),
            source_hash: format!("sha256:{}", "b".repeat(64)),
            source_region: "page:1;region:full-page".to_string(),
            confidence: 0.98,
            clearance: "restricted".to_string(),
            taint: "untrusted".to_string(),
            ledger_event_ref: "ledger-preview-1".to_string(),
        };
        assert!(validate_safe_preview(&preview, "preview-1").is_ok());
        assert!(validate_safe_preview(&preview, "preview-2").is_err());

        let mut invalid = preview;
        invalid.confidence = 1.1;
        assert!(validate_safe_preview(&invalid, "preview-1").is_err());
    }

    #[test]
    fn artifact_preview_validation_rejects_mismatched_or_unsafe_blocks() {
        let preview = ArtifactPreview {
            artifact_id: "artifact-1".to_string(),
            preview_kind: "structured_document".to_string(),
            title: "Approval note".to_string(),
            blocks: vec![ArtifactPreviewBlock {
                kind: "paragraph".to_string(),
                text: "Node-generated untrusted preview data".to_string(),
            }],
            clearance: "restricted".to_string(),
            taint: "untrusted".to_string(),
            ledger_event_ref: "ledger-artifact-1".to_string(),
        };
        assert!(validate_artifact_preview(&preview, "artifact-1").is_ok());
        assert!(validate_artifact_preview(&preview, "artifact-2").is_err());

        let mut invalid = preview;
        invalid.blocks[0].text = "bad\0preview".to_string();
        assert!(validate_artifact_preview(&invalid, "artifact-1").is_err());
    }
}
