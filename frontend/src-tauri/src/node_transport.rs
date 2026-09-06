use reqwest::Url;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::time::Duration;

const HANDSHAKE_PATH: &str = "/api/v1/node/handshake";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct NodeProfile {
    pub profile_id: String,
    pub endpoint: String,
    pub transport: NodeTransport,
    pub node_identity: String,
    pub protocol_version: String,
    pub clearance_context: String,
    pub certificate_pin_sha256: Option<String>,
    pub approved_by_policy: bool,
}

#[derive(Debug, Deserialize)]
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
    pub sovereignty: &'static str,
    pub ledger_event_ref: String,
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
            | Self::CertificatePinMismatch(message) => formatter.write_str(message),
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

fn certificate_pin(response: &reqwest::Response) -> Option<String> {
    response
        .extensions()
        .get::<reqwest::tls::TlsInfo>()
        .and_then(|tls| tls.peer_certificate())
        .map(|certificate| format!("sha256:{}", hex::encode(Sha256::digest(certificate))))
}

#[tauri::command]
pub async fn connect_node(profile: NodeProfile) -> Result<NodeConnectionResult, String> {
    let handshake_url = validate_profile(&profile).map_err(String::from)?;
    let is_remote = matches!(profile.transport, NodeTransport::InternalHttps);
    let expected_pin = profile.certificate_pin_sha256.clone();

    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .https_only(is_remote)
        .tls_info(true)
        .user_agent("AirBench-Desktop/0.1")
        .build()
        .map_err(|error| NodeTransportError::RequestFailed(error.to_string()))?;

    let response = client
        .get(handshake_url)
        .header("Accept", "application/json")
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

    if is_remote {
        let presented_pin = certificate_pin(&response).ok_or_else(|| {
            NodeTransportError::CertificatePinMismatch(
                "The remote Node did not expose a verifiable peer certificate.".to_string(),
            )
        })?;
        if Some(presented_pin) != expected_pin {
            return Err(NodeTransportError::CertificatePinMismatch(
                "The remote Node certificate pin does not match the approved profile.".to_string(),
            )
            .into());
        }
    }

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

    Ok(NodeConnectionResult {
        state: "connected",
        profile_id: profile.profile_id,
        node_identity: handshake.node_identity,
        protocol_version: handshake.protocol_version,
        clearance_context: handshake.clearance_context,
        sovereignty: "verified",
        ledger_event_ref: handshake.ledger_event_ref,
    })
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
            endpoint: endpoint.to_string(),
            transport,
            node_identity: "node-1".to_string(),
            protocol_version: "0.1".to_string(),
            clearance_context: "restricted".to_string(),
            certificate_pin_sha256: pin.map(str::to_string),
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
}
