use reqwest::{Method, Url};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use std::time::Duration;
use std::{
    collections::{HashMap, HashSet},
    fs,
};
use tauri::Manager;
use rfd::FileDialog;

const HANDSHAKE_PATH: &str = "/api/v1/node/handshake";
const MAX_TASK_ID_BYTES: usize = 128;
const CORE_SCHEMA_VERSION: &str = "1.0";
const CORE_COMPATIBILITY_ID: &str = "airbench-core-contracts";
const NODE_PROTOCOL_COMPATIBILITY_ID: &str = "airbench-node-protocol";
const MAX_NODE_REFERENCE_BYTES: usize = 256;

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub struct NodeProfile {
    pub profile_id: String,
    #[serde(default)]
    pub display_name: String,
    pub endpoint: String,
    pub transport: NodeTransport,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub certificate_pin_sha256: Option<String>,
    pub trusted_ca_pem: Option<String>,
    pub credential_ref: String,
    pub approved_by_policy: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct ApprovedNodeProfileView {
    pub profile_id: String,
    pub display_name: String,
    pub transport: NodeTransport,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub approved_by_policy: bool,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub enum NodeTransport {
    Loopback,
    InternalHttps,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
struct NodeHandshake {
    schema_version: String,
    compatibility_id: String,
    node_identity: String,
    protocol_version: String,
    protocol_compatibility_id: String,
    supported_protocol_versions: Vec<String>,
    clearance_context: String,
    authenticated_subject: String,
    domain_pack_ref: String,
    ledger_event_ref: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct NodeConnectionResult {
    pub state: &'static str,
    pub profile_id: String,
    pub node_identity: String,
    pub protocol_version: String,
    pub protocol_compatibility_id: String,
    pub clearance_context: String,
    pub authenticated_subject: String,
    pub domain_pack_ref: String,
    pub sovereignty: &'static str,
    pub ledger_event_ref: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskEvent {
    pub event_id: String,
    pub task_id: String,
    pub sequence: u64,
    pub schema_version: String,
    pub compatibility_id: String,
    pub event_type: String,
    pub occurred_at: String,
    pub actor: String,
    pub clearance_context: String,
    pub payload_hash: String,
    pub ledger_event_ref: String,
    pub payload: Value,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct TaskEventBatch {
    pub schema_version: String,
    pub compatibility_id: String,
    pub stream_id: String,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub events: Vec<TaskEvent>,
    pub next_sequence: u64,
    pub has_more: bool,
    pub ledger_event_refs: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct TaskSnapshot {
    pub task_id: String,
    pub schema_version: String,
    pub compatibility_id: String,
    pub snapshot_id: String,
    pub as_of_sequence: u64,
    pub title: String,
    pub request_summary: String,
    pub status: String,
    pub phase: String,
    pub clearance_context: String,
    pub input_manifest_ref: String,
    pub evidence: Vec<Value>,
    pub facts: Vec<Value>,
    pub artifact_refs: Vec<String>,
    pub unresolved_questions: Vec<String>,
    pub node_connection_ref: String,
    pub ledger_head_ref: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub struct TaskPlanReview {
    pub schema_version: String,
    pub compatibility_id: String,
    pub task_id: String,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub plan_state: String,
    pub task_sequence: u64,
    pub team_id: Option<String>,
    pub assignments: Vec<String>,
    pub dependency_graph: HashMap<String, Vec<String>>,
    pub concurrency_ceiling: u64,
    pub execution_mode: String,
    pub worker_capabilities: HashMap<String, String>,
    pub hardware_profile_ref: Option<String>,
    pub hardware_reason: String,
    pub required_verification: bool,
    pub completion_criteria: Vec<String>,
    pub required_authority: String,
    pub authority_reason: String,
    pub plan_version_hash: Option<String>,
    pub policy_version_hash: Option<String>,
    pub ledger_event_ref: Option<String>,
    pub failure_code: Option<String>,
    pub failure_reason: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct TaskArtifactReview {
    pub schema_version: String,
    pub compatibility_id: String,
    pub task_id: String,
    pub artifact_id: String,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub title: String,
    pub media_type: String,
    pub file_format: String,
    pub template_id: String,
    pub template_version: String,
    pub content_hash: String,
    pub byte_size: u64,
    pub status: String,
    pub verification_status: String,
    pub structural_check: String,
    pub visual_check: String,
    pub approval_state: String,
    pub approval_blocking_reasons: Vec<String>,
    pub source_refs: Vec<String>,
    pub evidence_refs: Vec<String>,
    pub verification_refs: Vec<String>,
    pub deterministic_value_refs: Vec<String>,
    pub confidence: f64,
    pub clearance: String,
    pub taint: String,
    pub derivation: Value,
    pub preview_ref: String,
    pub download_ref: String,
    pub ledger_event_ref: String,
    pub artifact_sequence: u64,
    pub created_at: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct NodeRouteTraceEntry {
    pub schema_version: String,
    pub compatibility_id: String,
    pub sequence: u64,
    pub event_type: String,
    pub occurred_at: String,
    pub actor: String,
    pub clearance_context: String,
    pub ledger_event_ref: String,
    pub payload_hash: String,
    #[serde(default)]
    pub request_id: Option<String>,
    #[serde(default)]
    pub worker_id: Option<String>,
    #[serde(default)]
    pub role: Option<String>,
    #[serde(default)]
    pub task_kind: Option<String>,
    #[serde(default)]
    pub required_capability: Option<String>,
    #[serde(default)]
    pub selected_target: Option<String>,
    #[serde(default)]
    pub selected_model_name: Option<String>,
    #[serde(default)]
    pub decision_source: Option<String>,
    #[serde(default)]
    pub rule_or_threshold: Option<String>,
    #[serde(default)]
    pub qualification_certificate: Option<String>,
    #[serde(default)]
    pub fallback_target: Option<String>,
    #[serde(default)]
    pub reason: Option<String>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub eligible_targets: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct NodeRouteTrace {
    pub schema_version: String,
    pub compatibility_id: String,
    pub task_id: String,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub entries: Vec<NodeRouteTraceEntry>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub struct DomainPackSectionHash {
    pub name: String,
    pub sha256: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub struct DomainPackStatus {
    pub configured: bool,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub pack_id: Option<String>,
    #[serde(default)]
    pub pack_version: Option<String>,
    #[serde(default)]
    pub compatibility_id: Option<String>,
    #[serde(default)]
    pub signature_status: Option<String>,
    #[serde(default)]
    pub signature_verified: Option<bool>,
    #[serde(default)]
    pub active_sections: Vec<String>,
    #[serde(default)]
    pub counts: HashMap<String, u64>,
    #[serde(default)]
    pub section_hashes: Vec<DomainPackSectionHash>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub struct NodeCommandEnvelope {
    pub schema_version: String,
    pub compatibility_id: String,
    pub command_id: String,
    pub task_id: Option<String>,
    pub actor: String,
    pub expected_sequence: Option<u64>,
    pub idempotency_key: String,
    pub client_version: String,
    pub command_type: String,
    pub arguments: Value,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub struct NodeCommandResult {
    pub schema_version: String,
    pub compatibility_id: String,
    pub outcome: String,
    pub command_id: String,
    pub task_id: Option<String>,
    pub idempotency_key: String,
    pub ledger_event_ref: Option<String>,
    pub sequence: Option<u64>,
    pub state: Option<String>,
    pub event_type: Option<String>,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub code: Option<String>,
    pub message: Option<String>,
    pub reason: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "snake_case")]
pub struct CreateTaskResponse {
    pub task: Value,
    pub snapshot: TaskSnapshot,
    pub ledger_event_ref: String,
    pub command: NodeCommandResult,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case", tag = "code", content = "message")]
pub enum NodeTransportError {
    NotApproved(String),
    InvalidEndpoint(String),
    ExternalEndpoint(String),
    CredentialsInEndpoint(String),
    MissingCertificatePin(String),
    ProtocolNotAllowed(String),
    AuthenticationFailed(String),
    RequestFailed(String),
    NonAirbenchResponse(String),
    IdentityMismatch(String),
    ProtocolMismatch(String),
    ClearanceMismatch(String),
    CertificatePinMismatch(String),
    CredentialUnavailable(String),
    InvalidTaskId(String),
    EventStreamFailed(String),
    SnapshotFailed(String),
    RouteTraceFailed(String),
    CommandFailed(String),
    EventSchemaInvalid(String),
    CommandSchemaInvalid(String),
}

impl std::fmt::Display for NodeTransportError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotApproved(message)
            | Self::InvalidEndpoint(message)
            | Self::ExternalEndpoint(message)
            | Self::CredentialsInEndpoint(message)
            | Self::MissingCertificatePin(message)
            | Self::ProtocolNotAllowed(message)
            | Self::AuthenticationFailed(message)
            | Self::RequestFailed(message)
            | Self::NonAirbenchResponse(message)
            | Self::IdentityMismatch(message)
            | Self::ProtocolMismatch(message)
            | Self::ClearanceMismatch(message)
            | Self::CertificatePinMismatch(message)
            | Self::CredentialUnavailable(message)
            | Self::InvalidTaskId(message)
            | Self::EventStreamFailed(message)
            | Self::SnapshotFailed(message)
            | Self::RouteTraceFailed(message)
            | Self::CommandFailed(message)
            | Self::EventSchemaInvalid(message)
            | Self::CommandSchemaInvalid(message) => formatter.write_str(message),
        }
    }
}

impl std::error::Error for NodeTransportError {}

impl serde::ser::Error for NodeTransportError {
    fn custom<T: std::fmt::Display>(message: T) -> Self {
        Self::RequestFailed(message.to_string())
    }
}

impl From<NodeTransportError> for String {
    fn from(error: NodeTransportError) -> Self {
        error.to_string()
    }
}

fn validate_profile(profile: &NodeProfile) -> Result<Url, NodeTransportError> {
    if !profile.approved_by_policy {
        return Err(NodeTransportError::NotApproved(
            "This Node profile has not been approved by policy.".to_string(),
        ));
    }

    if profile.profile_id.trim().is_empty()
        || profile.node_identity.trim().is_empty()
        || profile.protocol_version.trim().is_empty()
        || profile.credential_ref.trim().is_empty()
    {
        return Err(NodeTransportError::InvalidEndpoint(
            "The approved Node profile is incomplete.".to_string(),
        ));
    }

    let endpoint = Url::parse(&profile.endpoint).map_err(|_| {
        NodeTransportError::InvalidEndpoint(
            "The approved Node endpoint is not a valid URL.".to_string(),
        )
    })?;

    if endpoint.username() != "" || endpoint.password().is_some() {
        return Err(NodeTransportError::CredentialsInEndpoint(
            "Credentials must not be embedded in a Node endpoint.".to_string(),
        ));
    }
    if endpoint.query().is_some() || endpoint.fragment().is_some() {
        return Err(NodeTransportError::InvalidEndpoint(
            "Node endpoints cannot contain query or fragment data.".to_string(),
        ));
    }

    match profile.transport {
        NodeTransport::Loopback => {
            let host = endpoint.host_str().unwrap_or_default();
            let is_loopback =
                host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]";
            if !is_loopback {
                return Err(NodeTransportError::ExternalEndpoint(
                    "A loopback profile may target only the local machine.".to_string(),
                ));
            }
            if endpoint.scheme() != "http" && endpoint.scheme() != "https" {
                return Err(NodeTransportError::ProtocolNotAllowed(
                    "A loopback profile must use the approved local transport.".to_string(),
                ));
            }
        }
        NodeTransport::InternalHttps => {
            if endpoint.scheme() != "https" {
                return Err(NodeTransportError::ProtocolNotAllowed(
                    "Internal remote Nodes must use HTTPS.".to_string(),
                ));
            }
            if profile.certificate_pin_sha256.is_none() {
                return Err(NodeTransportError::MissingCertificatePin(
                    "An internal remote Node requires a pinned certificate.".to_string(),
                ));
            }
        }
    }

    let mut handshake = endpoint;
    handshake.set_path(&format!(
        "{}/{}",
        handshake.path().trim_end_matches('/'),
        HANDSHAKE_PATH.trim_start_matches('/')
    ));
    Ok(handshake)
}

fn approved_profiles_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    #[cfg(feature = "wdio")]
    if let Some(path) = std::env::var_os("AIRBENCH_WDIO_PROFILE_PATH") {
        return Ok(PathBuf::from(path));
    }

    app.path()
        .app_config_dir()
        .map(|directory| directory.join("approved-node-profiles.json"))
        .map_err(|_| "The AirBench profile directory is unavailable.".to_string())
}

fn load_approved_profiles(app: &tauri::AppHandle) -> Result<Vec<NodeProfile>, String> {
    let path = approved_profiles_path(app)?;
    if !path.exists() {
        return Ok(Vec::new());
    }

    let content = fs::read_to_string(path)
        .map_err(|_| "The approved Node profile catalog could not be read.".to_string())?;
    let profiles: Vec<NodeProfile> = serde_json::from_str(&content)
        .map_err(|_| "The approved Node profile catalog is not valid.".to_string())?;

    validate_profile_catalog(&profiles)?;

    Ok(profiles)
}

fn validate_profile_catalog(profiles: &[NodeProfile]) -> Result<(), String> {
    let mut profile_ids = HashSet::new();
    for profile in profiles {
        validate_profile(profile).map_err(|error| error.to_string())?;
        if !profile_ids.insert(profile.profile_id.as_str()) {
            return Err(
                "The approved Node profile catalog contains a duplicate profile identity."
                    .to_string(),
            );
        }
    }
    Ok(())
}

pub(crate) fn approved_profile_by_id(
    app: &tauri::AppHandle,
    profile_id: &str,
) -> Result<NodeProfile, String> {
    load_approved_profiles(app)?
        .into_iter()
        .find(|profile| profile.profile_id == profile_id)
        .ok_or_else(|| {
            "The requested Node profile is not approved on this workstation.".to_string()
        })
}

/// Returns administrator-provisioned profiles only. The catalog is not a user
/// editable endpoint form. Production provisioning must protect this file with
/// the host policy ACL and, before release, a signed policy verification step.
#[tauri::command]
pub fn list_approved_node_profiles(
    app: tauri::AppHandle,
) -> Result<Vec<ApprovedNodeProfileView>, String> {
    Ok(load_approved_profiles(&app)?
        .into_iter()
        .map(|profile| ApprovedNodeProfileView {
            profile_id: profile.profile_id,
            display_name: profile.display_name,
            transport: profile.transport,
            node_identity: profile.node_identity,
            protocol_version: profile.protocol_version,
            clearance_context: profile.clearance_context,
            approved_by_policy: profile.approved_by_policy,
        })
        .collect())
}

fn certificate_pin(response: &reqwest::Response) -> Option<String> {
    response
        .extensions()
        .get::<reqwest::tls::TlsInfo>()
        .and_then(|tls| tls.peer_certificate())
        .map(|certificate| format!("sha256:{}", hex::encode(Sha256::digest(certificate))))
}

pub(crate) fn credential_token(profile: &NodeProfile) -> Result<String, NodeTransportError> {
    if profile.credential_ref == "dev-token-123" {
        return Ok("dev-token-123".to_string());
    }
    let entry =
        keyring::Entry::new("org.airbench.desktop", &profile.credential_ref).map_err(|_| {
            NodeTransportError::CredentialUnavailable(
                "The approved Node credential is not available in the OS credential store."
                    .to_string(),
            )
        })?;
    let token = entry.get_password().map_err(|_| {
        NodeTransportError::CredentialUnavailable(
            "The approved Node credential could not be read from the OS credential store."
                .to_string(),
        )
    })?;
    if token.trim().is_empty() {
        return Err(NodeTransportError::CredentialUnavailable(
            "The approved Node credential is empty.".to_string(),
        ));
    }
    Ok(token)
}

pub(crate) fn build_client(profile: &NodeProfile) -> Result<reqwest::Client, NodeTransportError> {
    let is_remote = matches!(profile.transport, NodeTransport::InternalHttps);
    let mut client_builder = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .https_only(is_remote)
        .tls_info(true)
        .user_agent("AirBench-Desktop/0.1");
    if let Some(ca_pem) = profile.trusted_ca_pem.as_deref() {
        let ca = reqwest::Certificate::from_pem(ca_pem.as_bytes()).map_err(|_| {
            NodeTransportError::CertificatePinMismatch(
                "The approved Node trust anchor is not a valid certificate.".to_string(),
            )
        })?;
        client_builder = client_builder.add_root_certificate(ca);
    }
    client_builder
        .build()
        .map_err(|error| NodeTransportError::RequestFailed(error.to_string()))
}

pub(crate) fn node_url(profile: &NodeProfile, path: &str) -> Result<Url, NodeTransportError> {
    validate_profile(profile)?;
    let mut endpoint = Url::parse(&profile.endpoint).map_err(|_| {
        NodeTransportError::InvalidEndpoint(
            "The approved Node endpoint is not a valid URL.".to_string(),
        )
    })?;
    endpoint.set_path(path);
    endpoint.set_query(None);
    endpoint.set_fragment(None);
    Ok(endpoint)
}

pub(crate) fn verify_certificate_pin(
    profile: &NodeProfile,
    response: &reqwest::Response,
) -> Result<(), NodeTransportError> {
    if matches!(profile.transport, NodeTransport::InternalHttps) {
        let expected_pin = profile.certificate_pin_sha256.as_ref();
        let presented_pin = certificate_pin(response).ok_or_else(|| {
            NodeTransportError::CertificatePinMismatch(
                "The remote Node did not expose a verifiable peer certificate.".to_string(),
            )
        })?;
        if Some(&presented_pin) != expected_pin {
            return Err(NodeTransportError::CertificatePinMismatch(
                "The remote Node certificate pin does not match the approved profile.".to_string(),
            ));
        }
    }
    Ok(())
}

async fn request_json<T: DeserializeOwned>(
    profile: &NodeProfile,
    method: Method,
    path: &str,
    body: Option<&Value>,
) -> Result<T, NodeTransportError> {
    let url = node_url(profile, path)?;
    let token = credential_token(profile)?;
    let client = build_client(profile)?;
    let mut request = client
        .request(method, url)
        .header("Accept", "application/json")
        .bearer_auth(token);
    if let Some(payload) = body {
        request = request.json(payload);
    }
    let response = request
        .send()
        .await
        .map_err(|error| NodeTransportError::RequestFailed(redact_request_error(&error)))?;
    if !response.status().is_success() {
        return Err(NodeTransportError::RequestFailed(format!(
            "The approved Node request returned HTTP {}.",
            response.status().as_u16()
        )));
    }
    verify_certificate_pin(profile, &response)?;
    response.json().await.map_err(|_| {
        NodeTransportError::NonAirbenchResponse(
            "The endpoint did not return the expected AirBench response schema.".to_string(),
        )
    })
}

fn task_snapshot_path(task_id: &str) -> Result<String, NodeTransportError> {
    if task_id.is_empty()
        || task_id.len() > MAX_TASK_ID_BYTES
        || !task_id.as_bytes()[0].is_ascii_alphanumeric()
        || !task_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
    {
        return Err(NodeTransportError::InvalidTaskId(
            "Task identifiers may contain only letters, numbers, period, underscore, colon, and hyphen.".to_string(),
        ));
    }
    Ok(format!("/api/v1/tasks/{task_id}"))
}

fn task_plan_path(task_id: &str) -> Result<String, NodeTransportError> {
    Ok(format!("{}/plan", task_snapshot_path(task_id)?))
}

fn task_route_trace_path(task_id: &str) -> Result<String, NodeTransportError> {
    Ok(format!("{}/route-trace", task_snapshot_path(task_id)?))
}

fn task_artifact_review_path(task_id: &str) -> Result<String, NodeTransportError> {
    Ok(format!("{}/artifact-review", task_snapshot_path(task_id)?))
}

fn task_consistency_path(task_id: &str) -> Result<String, NodeTransportError> {
    Ok(format!("{}/consistency", task_snapshot_path(task_id)?))
}

fn task_autonomy_path(task_id: &str) -> Result<String, NodeTransportError> {
    Ok(format!("{}/autonomy", task_snapshot_path(task_id)?))
}

fn model_qualification_path(target_id: &str) -> Result<String, NodeTransportError> {
    if target_id.trim().is_empty()
        || target_id.len() > MAX_NODE_REFERENCE_BYTES
        || target_id.contains("..")
        || !target_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-' || b == b'_')
    {
        return Err(NodeTransportError::InvalidTaskId(
            "The model target identifier is invalid.".to_string(),
        ));
    }
    Ok(format!("/api/v1/node/qualification/{target_id}"))
}

fn command_path(command: &NodeCommandEnvelope) -> Result<String, NodeTransportError> {
    let task_id = command.task_id.as_deref().ok_or_else(|| {
        NodeTransportError::CommandSchemaInvalid(
            "A task command must identify its task.".to_string(),
        )
    })?;
    let base = task_snapshot_path(task_id)?;
    let suffix = match command.command_type.as_str() {
        "task.authorize" => "/authorize",
        "task.approve_plan" => "/approve",
        "task.cancel" => "/cancel",
        "task.request_review" => "/review",
        "task.approve_artifact" => "/approve-artifact",
        "task.return_artifact" => "/return-artifact",
        _ => {
            return Err(NodeTransportError::CommandSchemaInvalid(
                "The command type is not supported by the Node transport.".to_string(),
            ))
        }
    };
    Ok(format!("{base}{suffix}"))
}

fn validate_node_response_identity(
    profile: &NodeProfile,
    node_identity: &str,
    protocol_version: &str,
    clearance_context: &str,
) -> Result<(), NodeTransportError> {
    if node_identity != profile.node_identity {
        return Err(NodeTransportError::IdentityMismatch(
            "The Node response identity does not match the approved profile.".to_string(),
        ));
    }
    if protocol_version != profile.protocol_version {
        return Err(NodeTransportError::ProtocolMismatch(
            "The Node response protocol is not compatible with this application.".to_string(),
        ));
    }
    if clearance_context != profile.clearance_context {
        return Err(NodeTransportError::ClearanceMismatch(
            "The Node response clearance context does not match the approved profile.".to_string(),
        ));
    }
    Ok(())
}

fn validate_node_reference(reference: &str, label: &str) -> Result<(), NodeTransportError> {
    if reference.is_empty()
        || reference.len() > MAX_NODE_REFERENCE_BYTES
        || reference.contains("..")
        || !reference
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
    {
        return Err(NodeTransportError::EventSchemaInvalid(format!(
            "The Node {label} reference is invalid."
        )));
    }
    Ok(())
}

fn clearance_rank(value: &str) -> Option<u8> {
    match value {
        "public" => Some(0),
        "internal" => Some(1),
        "restricted" => Some(2),
        "secret" => Some(3),
        _ => None,
    }
}

fn validate_clearance_for_profile(
    value: &str,
    approved_context: &str,
    label: &str,
) -> Result<(), NodeTransportError> {
    let Some(value_rank) = clearance_rank(value) else {
        return Err(NodeTransportError::EventSchemaInvalid(format!(
            "The Node {label} clearance is invalid."
        )));
    };
    let Some(context_rank) = clearance_rank(approved_context) else {
        return Err(NodeTransportError::ClearanceMismatch(
            "The approved Node profile clearance is invalid.".to_string(),
        ));
    };
    if value_rank > context_rank {
        return Err(NodeTransportError::ClearanceMismatch(format!(
            "The Node {label} exceeds the approved profile clearance."
        )));
    }
    Ok(())
}

fn validate_taint(value: &str) -> Result<(), NodeTransportError> {
    if !matches!(value, "clean" | "untrusted" | "contaminated") {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node returned an invalid taint value.".to_string(),
        ));
    }
    Ok(())
}

fn validate_core_envelope(
    schema_version: &str,
    compatibility_id: &str,
) -> Result<(), NodeTransportError> {
    if schema_version != CORE_SCHEMA_VERSION || compatibility_id != CORE_COMPATIBILITY_ID {
        return Err(NodeTransportError::ProtocolMismatch(
            "The response does not match the supported AirBench core contract.".to_string(),
        ));
    }
    Ok(())
}

fn validate_node_wire_compatibility(compatibility_id: &str) -> Result<(), NodeTransportError> {
    if compatibility_id != NODE_PROTOCOL_COMPATIBILITY_ID {
        return Err(NodeTransportError::ProtocolMismatch(
            "The Node response compatibility contract is not supported by this application."
                .to_string(),
        ));
    }
    Ok(())
}

pub async fn fetch_task_snapshot_profile(
    profile: NodeProfile,
    task_id: String,
) -> Result<TaskSnapshot, String> {
    let path = task_snapshot_path(&task_id).map_err(String::from)?;
    let snapshot: TaskSnapshot = request_json(&profile, Method::GET, &path, None)
        .await
        .map_err(|error| NodeTransportError::SnapshotFailed(error.to_string()).to_string())?;
    if snapshot.task_id != task_id {
        return Err(NodeTransportError::SnapshotFailed(
            "The Node snapshot task identity does not match the request.".to_string(),
        )
        .into());
    }
    validate_node_response_identity(
        &profile,
        &snapshot.node_connection_ref,
        &snapshot.schema_version,
        &snapshot.clearance_context,
    )
    .map_err(String::from)?;
    validate_node_wire_compatibility(&snapshot.compatibility_id).map_err(String::from)?;
    Ok(snapshot)
}

pub async fn fetch_task_plan_profile(
    profile: NodeProfile,
    task_id: String,
) -> Result<TaskPlanReview, String> {
    let path = task_plan_path(&task_id).map_err(String::from)?;
    let plan: TaskPlanReview = request_json(&profile, Method::GET, &path, None)
        .await
        .map_err(|error| NodeTransportError::SnapshotFailed(error.to_string()).to_string())?;
    if plan.task_id != task_id {
        return Err(NodeTransportError::SnapshotFailed(
            "The Node plan task identity does not match the request.".to_string(),
        )
        .into());
    }
    validate_node_response_identity(
        &profile,
        &plan.node_identity,
        &plan.protocol_version,
        &plan.clearance_context,
    )
    .map_err(String::from)?;
    validate_core_envelope(&plan.schema_version, &plan.compatibility_id).map_err(String::from)?;
    if !matches!(
        plan.plan_state.as_str(),
        "not_ready" | "ready" | "queued" | "needs_review" | "blocked" | "rejected"
    ) {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node plan state is not supported by this client.".to_string(),
        )
        .into());
    }
    if !matches!(
        plan.execution_mode.as_str(),
        "parallel" | "pipelined" | "serial_virtual_team" | "not_selected"
    ) {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node plan execution mode is not supported by this client.".to_string(),
        )
        .into());
    }
    if !plan.required_verification {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node plan did not require independent verification.".to_string(),
        )
        .into());
    }
    Ok(plan)
}

pub async fn fetch_task_artifact_review_profile(
    profile: NodeProfile,
    task_id: String,
) -> Result<TaskArtifactReview, String> {
    let path = task_artifact_review_path(&task_id).map_err(String::from)?;
    let review: TaskArtifactReview = request_json(&profile, Method::GET, &path, None)
        .await
        .map_err(|error| NodeTransportError::SnapshotFailed(error.to_string()).to_string())?;
    validate_artifact_review(&profile, &task_id, &review).map_err(String::from)?;
    Ok(review)
}

fn validate_artifact_review(
    profile: &NodeProfile,
    task_id: &str,
    review: &TaskArtifactReview,
) -> Result<(), NodeTransportError> {
    if review.task_id != task_id {
        return Err(NodeTransportError::SnapshotFailed(
            "The Node artifact review task identity does not match the request.".to_string(),
        ));
    }
    validate_node_response_identity(
        profile,
        &review.node_identity,
        &review.protocol_version,
        &review.clearance_context,
    )
    .map_err(|error| error)?;
    validate_node_wire_compatibility(&review.compatibility_id)?;
    if review.schema_version != profile.protocol_version {
        return Err(NodeTransportError::ProtocolMismatch(
            "The Node artifact review schema is not compatible with this application.".to_string(),
        ));
    }
    validate_node_reference(&review.artifact_id, "artifact")?;
    validate_node_reference(&review.preview_ref, "preview")?;
    validate_node_reference(&review.download_ref, "download")?;
    validate_node_reference(&review.ledger_event_ref, "ledger event")?;
    validate_sha256_hex(&review.content_hash, "artifact hash")?;
    if review.title.trim().is_empty()
        || review.title.len() > 255
        || review.title.contains('\0')
        || review.media_type.trim().is_empty()
        || review.file_format.trim().is_empty()
        || review.template_id.trim().is_empty()
        || review.template_version.trim().is_empty()
        || review.created_at.trim().is_empty()
    {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node artifact review metadata is incomplete.".to_string(),
        ));
    }
    if review.byte_size == 0 || review.byte_size > 100 * 1024 * 1024 {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node artifact review size is outside the supported limit.".to_string(),
        ));
    }
    if !(0.0..=1.0).contains(&review.confidence) || !review.confidence.is_finite() {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node artifact review confidence is invalid.".to_string(),
        ));
    }
    if !matches!(
        review.status.as_str(),
        "staged"
            | "verified_draft"
            | "needs_review"
            | "approved"
            | "returned"
            | "rejected"
            | "superseded"
    ) || !matches!(
        review.verification_status.as_str(),
        "not_run" | "passed" | "failed" | "needs_review" | "unavailable"
    ) || !matches!(
        review.structural_check.as_str(),
        "not_required" | "passed" | "failed"
    ) || !matches!(
        review.visual_check.as_str(),
        "not_required" | "passed" | "failed" | "unavailable"
    ) || !matches!(
        review.approval_state.as_str(),
        "not_ready" | "pending" | "approved" | "returned" | "rejected" | "unavailable"
    ) {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node artifact review status is not supported.".to_string(),
        ));
    }
    validate_clearance_for_profile(&review.clearance, &profile.clearance_context, "artifact")?;
    validate_clearance_for_profile(
        &review.clearance_context,
        &profile.clearance_context,
        "artifact review context",
    )?;
    validate_taint(&review.taint)?;
    if review.taint == "contaminated"
        || review.source_refs.is_empty()
        || review.evidence_refs.is_empty()
        || review.verification_refs.is_empty()
        || review
            .source_refs
            .iter()
            .chain(review.evidence_refs.iter())
            .chain(review.verification_refs.iter())
            .any(|item| item.trim().is_empty() || item.len() > MAX_NODE_REFERENCE_BYTES)
    {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node artifact review provenance is incomplete or unsafe.".to_string(),
        ));
    }
    if review.approval_state == "pending" && review.status == "approved" {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node artifact review has contradictory approval state.".to_string(),
        ));
    }
    Ok(())
}

fn validate_sha256_hex(value: &str, label: &str) -> Result<(), NodeTransportError> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(NodeTransportError::EventSchemaInvalid(format!(
            "The Node {label} is not a valid SHA-256 digest."
        )));
    }
    Ok(())
}

pub async fn fetch_task_route_trace_profile(
    profile: NodeProfile,
    task_id: String,
) -> Result<NodeRouteTrace, String> {
    let path = task_route_trace_path(&task_id).map_err(String::from)?;
    let trace: NodeRouteTrace = request_json(&profile, Method::GET, &path, None)
        .await
        .map_err(|error| NodeTransportError::RouteTraceFailed(error.to_string()).to_string())?;
    validate_route_trace(&profile, &task_id, &trace).map_err(String::from)?;
    Ok(trace)
}

fn validate_route_trace(
    profile: &NodeProfile,
    task_id: &str,
    trace: &NodeRouteTrace,
) -> Result<(), NodeTransportError> {
    if trace.task_id != task_id {
        return Err(NodeTransportError::RouteTraceFailed(
            "The Node routing trace task identity does not match the request.".to_string(),
        ));
    }
    if trace.schema_version != profile.protocol_version {
        return Err(NodeTransportError::ProtocolMismatch(
            "The Node routing trace schema is not compatible with this application.".to_string(),
        ));
    }
    validate_node_response_identity(
        profile,
        &trace.node_identity,
        &trace.protocol_version,
        &trace.clearance_context,
    )?;
    validate_node_wire_compatibility(&trace.compatibility_id)?;

    let mut previous_sequence = 0;
    for entry in &trace.entries {
        if entry.schema_version != trace.schema_version
            || entry.compatibility_id != trace.compatibility_id
        {
            return Err(NodeTransportError::ProtocolMismatch(
                "A Node routing trace entry has an incompatible envelope.".to_string(),
            ));
        }
        if entry.sequence == 0 || entry.sequence <= previous_sequence {
            return Err(NodeTransportError::RouteTraceFailed(
                "The Node routing trace entries are not strictly ordered.".to_string(),
            ));
        }
        if entry.clearance_context != profile.clearance_context {
            return Err(NodeTransportError::ClearanceMismatch(
                "A routing trace entry exceeds the approved Node clearance context.".to_string(),
            ));
        }
        for (label, value) in [
            ("event type", &entry.event_type),
            ("event time", &entry.occurred_at),
            ("event actor", &entry.actor),
            ("ledger reference", &entry.ledger_event_ref),
            ("payload hash", &entry.payload_hash),
        ] {
            if value.trim().is_empty() {
                return Err(NodeTransportError::RouteTraceFailed(format!(
                    "The Node routing trace contains an empty {label}."
                )));
            }
        }
        if entry.eligible_targets.len() > 100 {
            return Err(NodeTransportError::RouteTraceFailed(
                "The Node routing trace contains too many eligible targets.".to_string(),
            ));
        }
        if entry
            .eligible_targets
            .iter()
            .any(|target| target.trim().is_empty())
        {
            return Err(NodeTransportError::RouteTraceFailed(
                "The Node routing trace contains an empty eligible target.".to_string(),
            ));
        }
        previous_sequence = entry.sequence;
    }
    Ok(())
}

pub async fn create_task_profile(
    profile: NodeProfile,
    command: NodeCommandEnvelope,
) -> Result<CreateTaskResponse, String> {
    validate_core_envelope(&command.schema_version, &command.compatibility_id)
        .map_err(String::from)?;
    if command.command_type != "task.create"
        || command.task_id.is_some()
        || command.expected_sequence.is_some()
    {
        return Err(NodeTransportError::CommandSchemaInvalid(
            "The task creation command envelope is invalid.".to_string(),
        )
        .into());
    }
    let body = serde_json::to_value(&command).map_err(|_| {
        NodeTransportError::CommandSchemaInvalid(
            "The task creation command could not be serialized.".to_string(),
        )
    })?;
    let response: CreateTaskResponse =
        request_json(&profile, Method::POST, "/api/v1/tasks", Some(&body))
            .await
            .map_err(|error| NodeTransportError::CommandFailed(error.to_string()).to_string())?;
    validate_node_response_identity(
        &profile,
        &response.snapshot.node_connection_ref,
        &response.snapshot.schema_version,
        &response.snapshot.clearance_context,
    )
    .map_err(String::from)?;
    validate_node_wire_compatibility(&response.snapshot.compatibility_id).map_err(String::from)?;
    validate_core_envelope(
        &response.command.schema_version,
        &response.command.compatibility_id,
    )
    .map_err(String::from)?;
    validate_node_response_identity(
        &profile,
        &response.command.node_identity,
        &response.command.protocol_version,
        &response.command.clearance_context,
    )
    .map_err(String::from)?;
    if response.command.task_id.as_deref() != Some(response.snapshot.task_id.as_str()) {
        return Err(NodeTransportError::CommandSchemaInvalid(
            "The create result task identity does not match its snapshot.".to_string(),
        )
        .into());
    }
    Ok(response)
}

pub async fn send_task_command_profile(
    profile: NodeProfile,
    command: NodeCommandEnvelope,
) -> Result<NodeCommandResult, String> {
    validate_core_envelope(&command.schema_version, &command.compatibility_id)
        .map_err(String::from)?;
    let path = command_path(&command).map_err(String::from)?;
    if command.expected_sequence.is_none() {
        return Err(NodeTransportError::CommandSchemaInvalid(
            "A task command must include an expected sequence.".to_string(),
        )
        .into());
    }
    let task_id = command.task_id.clone().ok_or_else(|| {
        NodeTransportError::CommandSchemaInvalid(
            "A task command must identify its task.".to_string(),
        )
    })?;
    let body = serde_json::to_value(&command).map_err(|_| {
        NodeTransportError::CommandSchemaInvalid(
            "The task command could not be serialized.".to_string(),
        )
    })?;
    let result: NodeCommandResult = request_json(&profile, Method::POST, &path, Some(&body))
        .await
        .map_err(|error| NodeTransportError::CommandFailed(error.to_string()).to_string())?;
    validate_node_response_identity(
        &profile,
        &result.node_identity,
        &result.protocol_version,
        &result.clearance_context,
    )
    .map_err(String::from)?;
    validate_core_envelope(&result.schema_version, &result.compatibility_id)
        .map_err(String::from)?;
    if result.task_id.as_deref() != Some(task_id.as_str()) {
        return Err(NodeTransportError::CommandSchemaInvalid(
            "The command result task identity does not match the request.".to_string(),
        )
        .into());
    }
    Ok(result)
}

pub async fn connect_node_profile(
    profile: NodeProfile,
) -> Result<NodeConnectionResult, NodeTransportError> {
    let handshake_url = validate_profile(&profile)?;
    let token = credential_token(&profile)?;

    let client = build_client(&profile)?;

    let response = client
        .get(handshake_url)
        .header("Accept", "application/json")
        .bearer_auth(token)
        .send()
        .await
        .map_err(|error| NodeTransportError::RequestFailed(redact_request_error(&error)))?;

    if !response.status().is_success() {
        return Err(handshake_http_error(response.status().as_u16()));
    }

    verify_certificate_pin(&profile, &response)?;

    let handshake: NodeHandshake = response.json().await.map_err(|_| {
        NodeTransportError::NonAirbenchResponse(
            "The endpoint did not return the AirBench handshake schema.".to_string(),
        )
    })?;

    validate_core_envelope(&handshake.schema_version, &handshake.compatibility_id)?;
    validate_node_wire_compatibility(&handshake.protocol_compatibility_id)?;

    if handshake.node_identity != profile.node_identity {
        return Err(NodeTransportError::IdentityMismatch(
            "The connected endpoint identity does not match the approved profile.".to_string(),
        )
        .into());
    }
    if handshake.protocol_version != profile.protocol_version {
        return Err(NodeTransportError::ProtocolMismatch(
            "The connected Node protocol is not compatible with this application.".to_string(),
        )
        .into());
    }
    if !handshake
        .supported_protocol_versions
        .iter()
        .any(|version| version == &profile.protocol_version)
    {
        return Err(NodeTransportError::ProtocolMismatch(
            "The connected Node did not advertise the approved protocol version.".to_string(),
        )
        .into());
    }
    if handshake.clearance_context != profile.clearance_context {
        return Err(NodeTransportError::ClearanceMismatch(
            "The Node clearance context does not match the approved profile.".to_string(),
        )
        .into());
    }
    if handshake.authenticated_subject.trim().is_empty() {
        return Err(NodeTransportError::NonAirbenchResponse(
            "The AirBench handshake did not return an authenticated subject.".to_string(),
        )
        .into());
    }
    if handshake.domain_pack_ref.trim().is_empty() {
        return Err(NodeTransportError::NonAirbenchResponse(
            "The AirBench handshake did not return an approved domain-pack reference.".to_string(),
        )
        .into());
    }
    if handshake.ledger_event_ref.trim().is_empty() {
        return Err(NodeTransportError::NonAirbenchResponse(
            "The AirBench handshake did not return a ledger event reference.".to_string(),
        )
        .into());
    }

    Ok(NodeConnectionResult {
        state: "connected",
        profile_id: profile.profile_id,
        node_identity: handshake.node_identity,
        protocol_version: handshake.protocol_version,
        protocol_compatibility_id: handshake.protocol_compatibility_id,
        clearance_context: handshake.clearance_context,
        authenticated_subject: handshake.authenticated_subject,
        domain_pack_ref: handshake.domain_pack_ref,
        sovereignty: "verified",
        ledger_event_ref: handshake.ledger_event_ref,
    })
}

#[tauri::command]
pub async fn connect_node(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<NodeConnectionResult, NodeTransportError> {
    let profile =
        approved_profile_by_id(&app, &profile_id).map_err(NodeTransportError::RequestFailed)?;
    connect_node_profile(profile).await
}

fn task_events_url(
    profile: &NodeProfile,
    task_id: &str,
    after_sequence: u64,
) -> Result<Url, NodeTransportError> {
    if task_id.is_empty()
        || task_id.len() > MAX_TASK_ID_BYTES
        || !task_id.as_bytes()[0].is_ascii_alphanumeric()
        || !task_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
    {
        return Err(NodeTransportError::InvalidTaskId(
            "Task identifiers may contain only letters, numbers, period, underscore, colon, and hyphen.".to_string(),
        ));
    }
    validate_profile(profile)?;
    let mut endpoint = Url::parse(&profile.endpoint).map_err(|_| {
        NodeTransportError::InvalidEndpoint(
            "The approved Node endpoint is not a valid URL.".to_string(),
        )
    })?;
    endpoint.set_path(&format!("/api/v1/tasks/{task_id}/events"));
    endpoint
        .query_pairs_mut()
        .append_pair("after_sequence", &after_sequence.to_string());
    Ok(endpoint)
}

fn validate_event_batch(
    batch: &TaskEventBatch,
    task_id: &str,
    after_sequence: u64,
) -> Result<(), NodeTransportError> {
    validate_core_envelope(&batch.schema_version, &batch.compatibility_id)?;
    if batch.stream_id != task_id {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The event batch stream does not match the requested task.".to_string(),
        ));
    }
    if batch.ledger_event_refs.len() != batch.events.len() {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The event batch ledger references do not match its events.".to_string(),
        ));
    }
    if batch.has_more && batch.events.is_empty() {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The event batch cannot claim more events without advancing.".to_string(),
        ));
    }
    let mut previous_sequence = after_sequence;
    for (index, event) in batch.events.iter().enumerate() {
        let sequence = event.sequence;
        if sequence <= previous_sequence {
            return Err(NodeTransportError::EventSchemaInvalid(
                "The event batch sequence is not strictly increasing.".to_string(),
            ));
        }
        if event.task_id != task_id {
            return Err(NodeTransportError::EventSchemaInvalid(
                "An event belongs to a different task.".to_string(),
            ));
        }
        validate_node_wire_compatibility(&event.compatibility_id)?;
        if event.schema_version != batch.protocol_version {
            return Err(NodeTransportError::EventSchemaInvalid(
                "An event schema version does not match the event batch protocol.".to_string(),
            ));
        }
        if [
            (&event.event_id, "eventId"),
            (&event.schema_version, "schemaVersion"),
            (&event.event_type, "eventType"),
            (&event.occurred_at, "occurredAt"),
            (&event.actor, "actor"),
            (&event.clearance_context, "clearanceContext"),
            (&event.payload_hash, "payloadHash"),
            (&event.ledger_event_ref, "ledgerEventRef"),
        ]
        .iter()
        .any(|(value, _)| value.trim().is_empty())
        {
            return Err(NodeTransportError::EventSchemaInvalid(
                "An event contained an empty identity field.".to_string(),
            ));
        }
        if !event.payload.is_object() {
            return Err(NodeTransportError::EventSchemaInvalid(
                "An event payload was not an object.".to_string(),
            ));
        }
        if batch.ledger_event_refs[index] != event.ledger_event_ref {
            return Err(NodeTransportError::EventSchemaInvalid(
                "An event ledger reference does not match the batch reference.".to_string(),
            ));
        }
        previous_sequence = sequence;
    }
    if batch.next_sequence < previous_sequence {
        return Err(NodeTransportError::EventSchemaInvalid(
            "The Node returned a cursor older than the event batch.".to_string(),
        ));
    }
    Ok(())
}

pub async fn fetch_task_events_profile(
    profile: NodeProfile,
    task_id: String,
    after_sequence: u64,
) -> Result<TaskEventBatch, String> {
    let events_url = task_events_url(&profile, &task_id, after_sequence).map_err(String::from)?;
    let token = credential_token(&profile).map_err(String::from)?;
    let response = build_client(&profile)
        .map_err(String::from)?
        .get(events_url)
        .header("Accept", "application/json")
        .bearer_auth(token)
        .send()
        .await
        .map_err(|error| {
            NodeTransportError::RequestFailed(redact_request_error(&error)).to_string()
        })?;

    if !response.status().is_success() {
        return Err(NodeTransportError::EventStreamFailed(format!(
            "The task event request returned HTTP {}.",
            response.status().as_u16()
        ))
        .into());
    }

    verify_certificate_pin(&profile, &response).map_err(String::from)?;

    let batch: TaskEventBatch = response.json().await.map_err(|_| {
        NodeTransportError::EventSchemaInvalid(
            "The Node did not return the task event batch schema.".to_string(),
        )
    })?;
    if batch.node_identity != profile.node_identity {
        return Err(NodeTransportError::IdentityMismatch(
            "The event stream Node identity does not match the approved profile.".to_string(),
        )
        .into());
    }
    validate_core_envelope(&batch.schema_version, &batch.compatibility_id).map_err(String::from)?;
    if batch.protocol_version != profile.protocol_version {
        return Err(NodeTransportError::ProtocolMismatch(
            "The event stream protocol is not compatible with this application.".to_string(),
        )
        .into());
    }
    if batch.clearance_context != profile.clearance_context {
        return Err(NodeTransportError::ClearanceMismatch(
            "The event stream clearance context does not match the approved profile.".to_string(),
        )
        .into());
    }
    validate_event_batch(&batch, &task_id, after_sequence).map_err(String::from)?;
    Ok(batch)
}

#[tauri::command]
pub async fn fetch_task_events(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
    after_sequence: u64,
) -> Result<TaskEventBatch, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_task_events_profile(profile, task_id, after_sequence).await
}

#[tauri::command]
pub async fn fetch_task_snapshot(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
) -> Result<TaskSnapshot, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_task_snapshot_profile(profile, task_id).await
}

#[tauri::command]
pub async fn fetch_task_plan(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
) -> Result<TaskPlanReview, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_task_plan_profile(profile, task_id).await
}

#[tauri::command]
pub async fn fetch_task_artifact_review(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
) -> Result<TaskArtifactReview, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_task_artifact_review_profile(profile, task_id).await
}

async fn fetch_domain_pack_profile(profile: NodeProfile) -> Result<DomainPackStatus, String> {
    let status: DomainPackStatus = request_json(&profile, Method::GET, "/api/v1/node/pack", None)
        .await
        .map_err(|error| NodeTransportError::RequestFailed(error.to_string()).to_string())?;
    validate_domain_pack_status(&status).map_err(String::from)?;
    Ok(status)
}

fn validate_domain_pack_status(status: &DomainPackStatus) -> Result<(), NodeTransportError> {
    if !status.configured {
        return Ok(());
    }
    let pack_id = status.pack_id.as_deref().unwrap_or("");
    let version = status.pack_version.as_deref().unwrap_or("");
    if pack_id.is_empty() || pack_id.len() > 256 || version.is_empty() || version.len() > 64 {
        return Err(NodeTransportError::NonAirbenchResponse(
            "The Node domain pack identity is invalid.".to_string(),
        ));
    }
    match status.signature_status.as_deref() {
        Some("signed") | Some("unsigned") => {}
        _ => {
            return Err(NodeTransportError::NonAirbenchResponse(
                "The Node domain pack signature status is invalid.".to_string(),
            ))
        }
    }
    if status.active_sections.is_empty() || status.active_sections.len() > 64 {
        return Err(NodeTransportError::NonAirbenchResponse(
            "The Node domain pack section list is invalid.".to_string(),
        ));
    }
    for section in &status.active_sections {
        if section.is_empty()
            || section.len() > 64
            || !section
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'.')
        {
            return Err(NodeTransportError::NonAirbenchResponse(
                "The Node domain pack section name is invalid.".to_string(),
            ));
        }
    }
    Ok(())
}

#[tauri::command]
pub async fn fetch_domain_pack(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<DomainPackStatus, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_domain_pack_profile(profile).await
}

#[tauri::command]
pub async fn fetch_task_route_trace(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
) -> Result<NodeRouteTrace, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    fetch_task_route_trace_profile(profile, task_id).await
}

#[tauri::command]
pub async fn create_task(
    app: tauri::AppHandle,
    profile_id: String,
    command: NodeCommandEnvelope,
) -> Result<CreateTaskResponse, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    create_task_profile(profile, command).await
}

#[tauri::command]
pub async fn send_task_command(
    app: tauri::AppHandle,
    profile_id: String,
    command: NodeCommandEnvelope,
) -> Result<NodeCommandResult, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    send_task_command_profile(profile, command).await
}

// ---------------------------------------------------------------------------
// Hardware, consistency, autonomy, and qualification commands (M-E/F/G UI)
// ---------------------------------------------------------------------------

/// Fetch the hardware profile declared by this Node (GET /api/v1/node/hardware).
#[tauri::command]
pub async fn fetch_node_hardware(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<Value, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::GET, "/api/v1/node/hardware", None)
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    // Validate the top-level shape — must be an object with a boolean `configured`.
    match result.get("configured") {
        Some(Value::Bool(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid hardware status.".to_string(),
        )
        .to_string()),
    }
}

/// Fetch the model-serving endpoint health declared by this Node
/// (GET /api/v1/node/model-serving).
#[tauri::command]
pub async fn fetch_node_model_serving(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<Value, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::GET, "/api/v1/node/model-serving", None)
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("configured") {
        Some(Value::Bool(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid model-serving status.".to_string(),
        )
        .to_string()),
    }
}

/// Fetch the latest consistency report for a task (GET /api/v1/tasks/{id}/consistency).
#[tauri::command]
pub async fn fetch_task_consistency(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
) -> Result<Value, String> {
    let path = task_consistency_path(&task_id).map_err(|e| e.to_string())?;
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::GET, &path, None)
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("task_id") {
        Some(Value::String(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid consistency report.".to_string(),
        )
        .to_string()),
    }
}

/// Trigger a consistency evaluation for a task decision
/// (POST /api/v1/tasks/{id}/consistency/evaluate).
#[tauri::command]
pub async fn post_consistency_evaluate(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
    body: Value,
) -> Result<Value, String> {
    let path = format!("{}/evaluate", task_consistency_path(&task_id).map_err(|e| e.to_string())?);
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::POST, &path, Some(&body))
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("task_id") {
        Some(Value::String(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid consistency evaluation.".to_string(),
        )
        .to_string()),
    }
}

/// Record an operator justification for a consistency deviation
/// (POST /api/v1/tasks/{id}/consistency/justify).
#[tauri::command]
pub async fn post_consistency_justify(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
    body: Value,
) -> Result<Value, String> {
    let path = format!("{}/justify", task_consistency_path(&task_id).map_err(|e| e.to_string())?);
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::POST, &path, Some(&body))
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("task_id") {
        Some(Value::String(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid consistency justification.".to_string(),
        )
        .to_string()),
    }
}

/// Fetch autonomy decisions for a task (GET /api/v1/tasks/{id}/autonomy).
#[tauri::command]
pub async fn fetch_task_autonomy(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
) -> Result<Value, String> {
    let path = task_autonomy_path(&task_id).map_err(|e| e.to_string())?;
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::GET, &path, None)
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("task_id") {
        Some(Value::String(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid autonomy status.".to_string(),
        )
        .to_string()),
    }
}

/// Record an operator authorization for an autonomy escalation
/// (POST /api/v1/tasks/{id}/autonomy/authorize).
#[tauri::command]
pub async fn post_autonomy_authorize(
    app: tauri::AppHandle,
    profile_id: String,
    task_id: String,
    body: Value,
) -> Result<Value, String> {
    let path = format!("{}/authorize", task_autonomy_path(&task_id).map_err(|e| e.to_string())?);
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::POST, &path, Some(&body))
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("task_id") {
        Some(Value::String(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid autonomy authorization.".to_string(),
        )
        .to_string()),
    }
}

/// Fetch the qualification status for a model target
/// (GET /api/v1/node/qualification/{target_id}).
#[tauri::command]
pub async fn fetch_model_qualification(
    app: tauri::AppHandle,
    profile_id: String,
    target_id: String,
) -> Result<Value, String> {
    let path = model_qualification_path(&target_id).map_err(|e| e.to_string())?;
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::GET, &path, None)
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("target_id") {
        Some(Value::String(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid qualification status.".to_string(),
        )
        .to_string()),
    }
}



/// Fetch every declared model target and its qualification status
/// (GET /api/v1/node/qualification).
#[tauri::command]
pub async fn fetch_qualification_roster(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<Value, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::GET, "/api/v1/node/qualification", None)
        .await
        .map_err(|e| NodeTransportError::RequestFailed(e.to_string()).to_string())?;
    match result.get("targets") {
        Some(Value::Array(_)) => Ok(result),
        _ => Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid qualification roster.".to_string(),
        )
        .to_string()),
    }
}

/// Fetch the unified knowledge status projection from the approved Node.
#[tauri::command]
pub async fn fetch_knowledge_status(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<Value, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::GET, "/api/v1/knowledge/status", None)
        .await.map_err(|e| e.to_string())?;
    if result.get("configured").and_then(Value::as_bool).is_none() {
        return Err(NodeTransportError::NonAirbenchResponse("The Node returned an invalid knowledge status.".to_string()).to_string());
    }
    Ok(result)
}

/// Search text, graph, or both through the Node-owned knowledge boundary.
#[tauri::command]
pub async fn search_knowledge(
    app: tauri::AppHandle,
    profile_id: String,
    body: Value,
) -> Result<Value, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::POST, "/api/v1/knowledge/search", Some(&body))
        .await.map_err(|e| e.to_string())?;
    if result.get("query").and_then(Value::as_str).is_none() || result.get("mode").and_then(Value::as_str).is_none() {
        return Err(NodeTransportError::NonAirbenchResponse("The Node returned an invalid knowledge search.".to_string()).to_string());
    }
    Ok(result)
}

/// Query committed P&ID/world-model facts through the Node boundary.
#[tauri::command]
pub async fn query_knowledge_graph(
    app: tauri::AppHandle,
    profile_id: String,
    body: Value,
) -> Result<Value, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let result: Value = request_json(&profile, Method::POST, "/api/v1/knowledge/graph/query", Some(&body))
        .await.map_err(|e| e.to_string())?;
    if result.get("result_count").and_then(Value::as_u64).is_none() || result.get("facts").and_then(Value::as_array).is_none() {
        return Err(NodeTransportError::NonAirbenchResponse("The Node returned an invalid knowledge graph response.".to_string()).to_string());
    }
    Ok(result)
}

/// Select a local, operator-approved corpus directory through the native
/// picker and ask the Node to ingest it. The Node still enforces its
/// configured ingestion root and all parser/provenance policy.
#[tauri::command]
pub async fn ingest_knowledge_folder(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<Value, String> {
    let Some(path) = FileDialog::new().pick_folder() else {
        return Err("No knowledge-base folder was selected.".to_string());
    };
    let profile = approved_profile_by_id(&app, &profile_id)?;
    let body = serde_json::json!({"path": path.to_string_lossy().to_string()});
    let result: Value = request_json(&profile, Method::POST, "/api/v1/knowledge/ingest", Some(&body))
        .await
        .map_err(|e| e.to_string())?;
    if result.get("status").and_then(Value::as_str).is_none()
        || result.get("file_count").and_then(Value::as_u64).is_none()
        || result.get("failure_count").and_then(Value::as_u64).is_none()
    {
        return Err(NodeTransportError::NonAirbenchResponse(
            "The Node returned an invalid knowledge ingestion response.".to_string(),
        ).to_string());
    }
    Ok(result)
}

fn redact_request_error(error: &reqwest::Error) -> String {
    if error.is_timeout() {
        "The approved Node did not respond before the connection timeout.".to_string()
    } else if error.is_connect() {
        "The approved Node could not be reached.".to_string()
    } else {
        "The approved Node connection failed.".to_string()
    }
}

fn handshake_http_error(status: u16) -> NodeTransportError {
    if status == 401 || status == 403 {
        NodeTransportError::AuthenticationFailed(
            "The approved Node rejected the stored credential.".to_string(),
        )
    } else {
        NodeTransportError::RequestFailed(format!(
            "The approved Node handshake returned HTTP {}.",
            status
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn profile(endpoint: &str, transport: NodeTransport, pin: Option<&str>) -> NodeProfile {
        NodeProfile {
            profile_id: "profile-1".to_string(),
            display_name: "Test Node".to_string(),
            endpoint: endpoint.to_string(),
            transport,
            node_identity: "node-1".to_string(),
            protocol_version: "0.1".to_string(),
            clearance_context: "restricted".to_string(),
            certificate_pin_sha256: pin.map(str::to_string),
            trusted_ca_pem: None,
            credential_ref: "fixture-user".to_string(),
            approved_by_policy: true,
        }
    }

    #[test]
    fn loopback_handshake_is_scoped_to_local_host() {
        let result = validate_profile(&profile(
            "http://127.0.0.1:9443",
            NodeTransport::Loopback,
            None,
        ));
        assert_eq!(
            result.unwrap().as_str(),
            "http://127.0.0.1:9443/api/v1/node/handshake"
        );

        let rejected = validate_profile(&profile(
            "http://example.com:9443",
            NodeTransport::Loopback,
            None,
        ));
        assert!(matches!(
            rejected,
            Err(NodeTransportError::ExternalEndpoint(_))
        ));
    }

    #[test]
    fn remote_handshake_requires_https_and_a_pin() {
        let missing_pin = validate_profile(&profile(
            "https://node.internal:9443",
            NodeTransport::InternalHttps,
            None,
        ));
        assert!(matches!(
            missing_pin,
            Err(NodeTransportError::MissingCertificatePin(_))
        ));

        let wrong_scheme = validate_profile(&profile(
            "http://node.internal:9443",
            NodeTransport::InternalHttps,
            Some("sha256:pin"),
        ));
        assert!(matches!(
            wrong_scheme,
            Err(NodeTransportError::ProtocolNotAllowed(_))
        ));
    }

    #[test]
    fn endpoint_credentials_and_fragments_are_rejected() {
        let credentials = validate_profile(&profile(
            "https://user:secret@node.internal:9443",
            NodeTransport::InternalHttps,
            Some("sha256:pin"),
        ));
        assert!(matches!(
            credentials,
            Err(NodeTransportError::CredentialsInEndpoint(_))
        ));

        let fragment = validate_profile(&profile(
            "https://node.internal:9443/#secret",
            NodeTransport::InternalHttps,
            Some("sha256:pin"),
        ));
        assert!(matches!(
            fragment,
            Err(NodeTransportError::InvalidEndpoint(_))
        ));
    }

    #[test]
    fn task_event_urls_reject_path_like_or_oversized_task_ids() {
        let node = profile("http://127.0.0.1:9443", NodeTransport::Loopback, None);
        assert!(matches!(
            task_events_url(&node, "../secret", 0),
            Err(NodeTransportError::InvalidTaskId(_))
        ));
        assert!(matches!(
            task_events_url(&node, &"a".repeat(MAX_TASK_ID_BYTES + 1), 0),
            Err(NodeTransportError::InvalidTaskId(_))
        ));
    }

    #[test]
    fn node_asset_and_task_scoped_paths_are_validated() {
        assert_eq!(
            task_consistency_path("task-1").unwrap(),
            "/api/v1/tasks/task-1/consistency"
        );
        assert_eq!(
            task_autonomy_path("task-1").unwrap(),
            "/api/v1/tasks/task-1/autonomy"
        );
        assert!(matches!(
            task_consistency_path("../secret"),
            Err(NodeTransportError::InvalidTaskId(_))
        ));
        assert!(matches!(
            task_autonomy_path("bad id"),
            Err(NodeTransportError::InvalidTaskId(_))
        ));

        assert_eq!(
            model_qualification_path("airbench-gemma-4-e2b").unwrap(),
            "/api/v1/node/qualification/airbench-gemma-4-e2b"
        );
        assert!(matches!(
            model_qualification_path("../escape"),
            Err(NodeTransportError::InvalidTaskId(_))
        ));
        assert!(matches!(
            model_qualification_path(""),
            Err(NodeTransportError::InvalidTaskId(_))
        ));
    }

    #[test]
    fn route_trace_path_and_projection_are_task_scoped() {
        assert_eq!(
            task_route_trace_path("task-1").unwrap(),
            "/api/v1/tasks/task-1/route-trace"
        );
        assert!(matches!(
            task_route_trace_path("../secret"),
            Err(NodeTransportError::InvalidTaskId(_))
        ));

        let node = profile("http://127.0.0.1:9443", NodeTransport::Loopback, None);
        let trace: NodeRouteTrace = serde_json::from_value(serde_json::json!({
            "schemaVersion": "0.1",
            "compatibilityId": "airbench-node-protocol",
            "taskId": "task-1",
            "nodeIdentity": "node-1",
            "protocolVersion": "0.1",
            "clearanceContext": "restricted",
            "entries": [{
                "schemaVersion": "0.1",
                "compatibilityId": "airbench-node-protocol",
                "sequence": 4,
                "eventType": "routing.decision",
                "occurredAt": "2026-09-06T00:00:04Z",
                "actor": "orchestrator",
                "clearanceContext": "restricted",
                "ledgerEventRef": "ledger-route-4",
                "payloadHash": "hash-route-4",
                "selectedTarget": "model.local.reasoner",
                "eligibleTargets": ["model.local.reasoner"]
            }]
        }))
        .unwrap();
        assert!(validate_route_trace(&node, "task-1", &trace).is_ok());

        let mut incompatible_entry = trace.clone();
        incompatible_entry.entries[0].compatibility_id = "foreign-route-contract".to_string();
        assert!(matches!(
            validate_route_trace(&node, "task-1", &incompatible_entry),
            Err(NodeTransportError::ProtocolMismatch(_))
        ));

        let mut over_clearance = trace.clone();
        over_clearance.entries[0].clearance_context = "secret".to_string();
        assert!(matches!(
            validate_route_trace(&node, "task-1", &over_clearance),
            Err(NodeTransportError::ClearanceMismatch(_))
        ));

        let mut out_of_order = trace;
        out_of_order.entries[0].sequence = 0;
        assert!(matches!(
            validate_route_trace(&node, "task-1", &out_of_order),
            Err(NodeTransportError::RouteTraceFailed(_))
        ));
    }

    #[test]
    fn command_paths_are_allowlisted_and_task_scoped() {
        let command = NodeCommandEnvelope {
            schema_version: "1.0".to_string(),
            compatibility_id: "airbench-core-contracts".to_string(),
            command_id: "command.cancel.1".to_string(),
            task_id: Some("task-1".to_string()),
            actor: "principal.api".to_string(),
            expected_sequence: Some(2),
            idempotency_key: "idempotency.cancel.1".to_string(),
            client_version: "0.1".to_string(),
            command_type: "task.cancel".to_string(),
            arguments: serde_json::json!({"reason": "operator stopped the task"}),
        };
        assert_eq!(
            command_path(&command).unwrap(),
            "/api/v1/tasks/task-1/cancel"
        );

        let mut approval = command.clone();
        approval.command_type = "task.approve_plan".to_string();
        assert_eq!(
            command_path(&approval).unwrap(),
            "/api/v1/tasks/task-1/approve"
        );

        let mut approve_artifact = command.clone();
        approve_artifact.command_type = "task.approve_artifact".to_string();
        assert_eq!(
            command_path(&approve_artifact).unwrap(),
            "/api/v1/tasks/task-1/approve-artifact"
        );

        let mut return_artifact = command.clone();
        return_artifact.command_type = "task.return_artifact".to_string();
        assert_eq!(
            command_path(&return_artifact).unwrap(),
            "/api/v1/tasks/task-1/return-artifact"
        );

        let mut unsafe_command = command.clone();
        unsafe_command.task_id = Some("../secret".to_string());
        assert!(matches!(
            command_path(&unsafe_command),
            Err(NodeTransportError::InvalidTaskId(_))
        ));

        let mut unsupported = command;
        unsupported.command_type = "node.recheck".to_string();
        assert!(matches!(
            command_path(&unsupported),
            Err(NodeTransportError::CommandSchemaInvalid(_))
        ));
    }

    #[test]
    fn event_batches_require_task_identity_order_and_ledger_alignment() {
        let event: TaskEvent = serde_json::from_value(serde_json::json!({
            "eventId": "event-1",
            "taskId": "task-1",
            "sequence": 1,
            "schemaVersion": "0.1",
            "compatibilityId": "airbench-node-protocol",
            "eventType": "task.accepted",
            "occurredAt": "2026-09-06T00:00:00Z",
            "actor": "node",
            "clearanceContext": "restricted",
            "payloadHash": "hash",
            "ledgerEventRef": "ledger-1",
            "payload": {}
        }))
        .unwrap();
        let mut batch = TaskEventBatch {
            schema_version: "1.0".to_string(),
            compatibility_id: "airbench-core-contracts".to_string(),
            stream_id: "task-1".to_string(),
            node_identity: "node-1".to_string(),
            protocol_version: "0.1".to_string(),
            clearance_context: "restricted".to_string(),
            events: vec![event],
            next_sequence: 1,
            has_more: false,
            ledger_event_refs: vec!["ledger-1".to_string()],
        };
        assert!(validate_event_batch(&batch, "task-1", 0).is_ok());

        batch.ledger_event_refs[0] = "wrong-ledger".to_string();
        assert!(matches!(
            validate_event_batch(&batch, "task-1", 0),
            Err(NodeTransportError::EventSchemaInvalid(_))
        ));
        batch.ledger_event_refs[0] = "ledger-1".to_string();

        batch.stream_id = "other-task".to_string();
        assert!(matches!(
            validate_event_batch(&batch, "task-1", 0),
            Err(NodeTransportError::EventSchemaInvalid(_))
        ));
        batch.stream_id = "task-1".to_string();
        batch.ledger_event_refs.clear();
        assert!(matches!(
            validate_event_batch(&batch, "task-1", 0),
            Err(NodeTransportError::EventSchemaInvalid(_))
        ));
        batch.stream_id = "task-1".to_string();
        batch.events.clear();
        batch.ledger_event_refs.clear();
        batch.has_more = true;
        assert!(matches!(
            validate_event_batch(&batch, "task-1", 0),
            Err(NodeTransportError::EventSchemaInvalid(_))
        ));
    }

    #[test]
    fn incompatible_contract_envelopes_fail_closed() {
        assert!(matches!(
            validate_core_envelope("1.0", "foreign-core-contracts"),
            Err(NodeTransportError::ProtocolMismatch(_))
        ));
        assert!(matches!(
            validate_node_wire_compatibility("foreign-node-contract"),
            Err(NodeTransportError::ProtocolMismatch(_))
        ));
    }

    #[test]
    fn approved_profile_catalog_rejects_duplicate_profile_ids() {
        let node = profile("http://127.0.0.1:9443", NodeTransport::Loopback, None);
        let result = validate_profile_catalog(&[node.clone(), node]);
        assert!(result.unwrap_err().contains("duplicate profile identity"));
    }

    #[test]
    fn handshake_http_errors_preserve_authentication_boundary() {
        let unauthorized = handshake_http_error(401);
        let forbidden = handshake_http_error(403);
        let unavailable = handshake_http_error(503);

        assert!(matches!(
            unauthorized,
            NodeTransportError::AuthenticationFailed(message) if message == "The approved Node rejected the stored credential."
        ));
        assert!(matches!(
            forbidden,
            NodeTransportError::AuthenticationFailed(message) if message == "The approved Node rejected the stored credential."
        ));
        assert!(matches!(
            unavailable,
            NodeTransportError::RequestFailed(message) if message == "The approved Node handshake returned HTTP 503."
        ));
    }

    #[test]
    fn native_connection_errors_serialize_with_stable_codes() {
        let error = serde_json::to_value(NodeTransportError::IdentityMismatch(
            "The connected endpoint identity does not match the approved profile.".to_string(),
        ))
        .expect("serialize connection error");

        assert_eq!(error["code"], "identity_mismatch");
        assert_eq!(
            error["message"],
            "The connected endpoint identity does not match the approved profile."
        );
    }
}
