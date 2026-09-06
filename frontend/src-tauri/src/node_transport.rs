use reqwest::Url;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{collections::HashSet, fs};
use std::path::PathBuf;
use std::time::Duration;
use tauri::Manager;

const HANDSHAKE_PATH: &str = "/api/v1/node/handshake";
const MAX_TASK_ID_BYTES: usize = 128;

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
    node_identity: String,
    protocol_version: String,
    clearance_context: String,
    authenticated_subject: String,
    ledger_event_ref: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct NodeConnectionResult {
    pub state: &'static str,
    pub profile_id: String,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub authenticated_subject: String,
    pub sovereignty: &'static str,
    pub ledger_event_ref: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct TaskEventBatch {
    pub stream_id: String,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub events: Vec<Value>,
    pub next_sequence: u64,
    pub has_more: bool,
    pub ledger_event_refs: Vec<String>,
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
    RequestFailed(String),
    NonAirbenchResponse(String),
    IdentityMismatch(String),
    ProtocolMismatch(String),
    ClearanceMismatch(String),
    CertificatePinMismatch(String),
    CredentialUnavailable(String),
    InvalidTaskId(String),
    EventStreamFailed(String),
    EventSchemaInvalid(String),
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
            | Self::RequestFailed(message)
            | Self::NonAirbenchResponse(message)
            | Self::IdentityMismatch(message)
            | Self::ProtocolMismatch(message)
            | Self::ClearanceMismatch(message)
            | Self::CertificatePinMismatch(message)
            | Self::CredentialUnavailable(message)
            | Self::InvalidTaskId(message)
            | Self::EventStreamFailed(message)
            | Self::EventSchemaInvalid(message) => formatter.write_str(message),
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
            return Err("The approved Node profile catalog contains a duplicate profile identity.".to_string());
        }
    }
    Ok(())
}

pub(crate) fn approved_profile_by_id(app: &tauri::AppHandle, profile_id: &str) -> Result<NodeProfile, String> {
    load_approved_profiles(app)?
        .into_iter()
        .find(|profile| profile.profile_id == profile_id)
        .ok_or_else(|| "The requested Node profile is not approved on this workstation.".to_string())
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

pub async fn connect_node_profile(profile: NodeProfile) -> Result<NodeConnectionResult, String> {
    let handshake_url = validate_profile(&profile).map_err(String::from)?;
    let token = credential_token(&profile).map_err(String::from)?;

    let client = build_client(&profile).map_err(String::from)?;

    let response = client
        .get(handshake_url)
        .header("Accept", "application/json")
        .bearer_auth(token)
        .send()
        .await
        .map_err(|error| NodeTransportError::RequestFailed(redact_request_error(&error)))?;

    if !response.status().is_success() {
        return Err(NodeTransportError::RequestFailed(format!(
            "The approved Node handshake returned HTTP {}.",
            response.status().as_u16()
        ))
        .into());
    }

    verify_certificate_pin(&profile, &response).map_err(String::from)?;

    let handshake: NodeHandshake = response.json().await.map_err(|_| {
        NodeTransportError::NonAirbenchResponse(
            "The endpoint did not return the AirBench handshake schema.".to_string(),
        )
    })?;

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
        clearance_context: handshake.clearance_context,
        authenticated_subject: handshake.authenticated_subject,
        sovereignty: "verified",
        ledger_event_ref: handshake.ledger_event_ref,
    })
}

#[tauri::command]
pub async fn connect_node(
    app: tauri::AppHandle,
    profile_id: String,
) -> Result<NodeConnectionResult, String> {
    let profile = approved_profile_by_id(&app, &profile_id)?;
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
        let sequence = event.get("sequence").and_then(Value::as_u64).ok_or_else(|| {
            NodeTransportError::EventSchemaInvalid(
                "An event did not contain a numeric sequence.".to_string(),
            )
        })?;
        if sequence <= previous_sequence {
            return Err(NodeTransportError::EventSchemaInvalid(
                "The event batch sequence is not strictly increasing.".to_string(),
            ));
        }
        if event.get("taskId").and_then(Value::as_str) != Some(task_id) {
            return Err(NodeTransportError::EventSchemaInvalid(
                "An event belongs to a different task.".to_string(),
            ));
        }
        for field in [
            "eventId",
            "schemaVersion",
            "eventType",
            "occurredAt",
            "actor",
            "clearanceContext",
            "payloadHash",
            "ledgerEventRef",
        ] {
            if event
                .get(field)
                .and_then(Value::as_str)
                .map(str::is_empty)
                .unwrap_or(true)
            {
                return Err(NodeTransportError::EventSchemaInvalid(format!(
                    "An event did not contain a valid {field}."
                )));
            }
        }
        if !event
            .get("payload")
            .map(Value::is_object)
            .unwrap_or(false)
        {
            return Err(NodeTransportError::EventSchemaInvalid(
                "An event payload was not an object.".to_string(),
            ));
        }
        if batch.ledger_event_refs[index]
            != event
                .get("ledgerEventRef")
                .and_then(Value::as_str)
                .unwrap_or_default()
        {
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

fn redact_request_error(error: &reqwest::Error) -> String {
    if error.is_timeout() {
        "The approved Node did not respond before the connection timeout.".to_string()
    } else if error.is_connect() {
        "The approved Node could not be reached.".to_string()
    } else {
        "The approved Node connection failed.".to_string()
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
    fn event_batches_require_task_identity_order_and_ledger_alignment() {
        let event = serde_json::json!({
            "eventId": "event-1",
            "taskId": "task-1",
            "sequence": 1,
            "schemaVersion": "0.1",
            "eventType": "task.accepted",
            "occurredAt": "2026-09-06T00:00:00Z",
            "actor": "node",
            "clearanceContext": "restricted",
            "payloadHash": "hash",
            "ledgerEventRef": "ledger-1",
            "payload": {}
        });
        let mut batch = TaskEventBatch {
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
    fn approved_profile_catalog_rejects_duplicate_profile_ids() {
        let node = profile("http://127.0.0.1:9443", NodeTransport::Loopback, None);
        let result = validate_profile_catalog(&[node.clone(), node]);
        assert!(result.unwrap_err().contains("duplicate profile identity"));
    }
}
