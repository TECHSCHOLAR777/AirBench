use base64::Engine;
use rfd::FileDialog;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::process::Command;

const MAX_CHAT_ATTACHMENT_FILE_BYTES: u64 = 20 * 1024 * 1024;

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct PickedAttachment {
    pub file_name: String,
    pub mime_type: String,
    pub base64_data: String,
}

fn guess_mime_type(path: &std::path::Path) -> String {
    match path.extension().and_then(|extension| extension.to_str()).map(str::to_lowercase).as_deref() {
        Some("pdf") => "application/pdf",
        Some("png") => "image/png",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("txt") => "text/plain",
        Some("csv") => "text/csv",
        Some("md") => "text/markdown",
        _ => "application/octet-stream",
    }
    .to_string()
}

#[tauri::command]
pub fn pick_chat_attachment() -> Result<Option<PickedAttachment>, String> {
    let Some(path) = FileDialog::new()
        .add_filter("Documents and images", &["pdf", "png", "jpg", "jpeg", "txt", "csv", "md"])
        .pick_file()
    else {
        return Ok(None);
    };

    let metadata = std::fs::metadata(&path)
        .map_err(|error| format!("Could not read the selected file: {error}"))?;
    if metadata.len() > MAX_CHAT_ATTACHMENT_FILE_BYTES {
        return Err("The selected file is larger than the 20MB chat attachment limit.".to_string());
    }

    let bytes = std::fs::read(&path).map_err(|error| format!("Could not read the selected file: {error}"))?;
    let file_name = path
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "attachment".to_string());

    Ok(Some(PickedAttachment {
        mime_type: guess_mime_type(&path),
        file_name,
        base64_data: base64::engine::general_purpose::STANDARD.encode(bytes),
    }))
}

const GEMINI_MODEL: &str = "gemini-2.5-flash";
const GEMINI_ENDPOINT: &str = "https://generativelanguage.googleapis.com/v1beta/models";
const REQUEST_TIMEOUT_SECS: u64 = 60;
const SANDBOX_TIMEOUT_SECS: u64 = 15;
const MAX_ATTACHMENT_BYTES: usize = 20 * 1024 * 1024;

const DOCUMENT_GENERATOR_SCRIPT: &str =
    include_str!("../../../../scripts/chat_document_generator.py");

const SYSTEM_INSTRUCTION: &str = "You are a helpful assistant embedded in a desktop app. \
Answer the user's questions directly and concisely using markdown. \
If, and only if, the user explicitly asks you to generate, create, produce, \
or export a Word document, Excel spreadsheet, PowerPoint presentation, or \
PDF report, reply with ONLY a single JSON object (no markdown fences, no \
other text) of this exact shape: {\"generate_document\": {\"format\": \
\"docx\"|\"xlsx\"|\"pptx\"|\"pdf\", \"title\": string, \"sections\": \
[{\"heading\": string, \"body\": string}], \"table\": {\"headers\": \
string[], \"rows\": string[][]} or null}}. Otherwise never emit that JSON \
shape.";

#[derive(Debug, Deserialize)]
pub struct ChatTurn {
    pub role: String,
    pub text: String,
}

#[derive(Debug, Deserialize)]
pub struct Attachment {
    pub mime_type: String,
    pub base64_data: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct GeminiReply {
    pub text: String,
}

fn gemini_api_key() -> Result<String, String> {
    let keys: Vec<String> = ["GEMINI_API_KEY", "GEMINI_API_KEY_2"]
        .iter()
        .filter_map(|name| std::env::var(name).ok())
        .filter(|key| !key.trim().is_empty())
        .collect();
    if keys.is_empty() {
        return Err("The worker is offline. Check your connection and try again.".to_string());
    }
    static NEXT_KEY: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let index = NEXT_KEY.fetch_add(1, std::sync::atomic::Ordering::Relaxed) % keys.len();
    Ok(keys[index].clone())
}

#[tauri::command]
pub async fn gemini_chat(
    history: Vec<ChatTurn>,
    message: String,
    attachment: Option<Attachment>,
) -> Result<GeminiReply, String> {
    let api_key = gemini_api_key()?;
    if let Some(attachment) = &attachment {
        if attachment.base64_data.len() > MAX_ATTACHMENT_BYTES {
            return Err("The attached file is too large to send to the worker.".to_string());
        }
    }

    let mut contents: Vec<Value> = history
        .iter()
        .map(|turn| {
            let role = if turn.role == "assistant" || turn.role == "model" {
                "model"
            } else {
                "user"
            };
            json!({ "role": role, "parts": [{ "text": turn.text }] })
        })
        .collect();

    let mut parts = vec![json!({ "text": message })];
    if let Some(attachment) = attachment {
        parts.push(json!({
            "inline_data": {
                "mime_type": attachment.mime_type,
                "data": attachment.base64_data,
            }
        }));
    }
    contents.push(json!({ "role": "user", "parts": parts }));

    let body = json!({
        "system_instruction": { "parts": [{ "text": SYSTEM_INSTRUCTION }] },
        "contents": contents,
    });

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(REQUEST_TIMEOUT_SECS))
        .build()
        .map_err(|error| format!("Could not reach the worker: {error}"))?;

    let url = format!("{GEMINI_ENDPOINT}/{GEMINI_MODEL}:generateContent");
    let response = client
        .post(url)
        .header("x-goog-api-key", api_key)
        .json(&body)
        .send()
        .await
        .map_err(|error| format!("The worker request failed: {error}"))?;

    let status = response.status();
    let payload: Value = response
        .json()
        .await
        .map_err(|error| format!("The worker returned a response that could not be read: {error}"))?;

    if !status.is_success() {
        let message = payload
            .get("error")
            .and_then(|error| error.get("message"))
            .and_then(Value::as_str)
            .unwrap_or("The worker rejected the request.");
        return Err(message.to_string());
    }

    let text = payload
        .get("candidates")
        .and_then(|candidates| candidates.get(0))
        .and_then(|candidate| candidate.get("content"))
        .and_then(|content| content.get("parts"))
        .and_then(|parts| parts.get(0))
        .and_then(|part| part.get("text"))
        .and_then(Value::as_str)
        .ok_or_else(|| "The worker did not return any text.".to_string())?;

    Ok(GeminiReply {
        text: text.to_string(),
    })
}

#[derive(Debug, Deserialize)]
pub struct DocumentSection {
    pub heading: String,
    pub body: String,
}

#[derive(Debug, Deserialize)]
pub struct DocumentTable {
    pub headers: Vec<String>,
    pub rows: Vec<Vec<String>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct DocumentResult {
    pub file_path: String,
    pub byte_size: u64,
    pub cancelled: bool,
}

fn extension_for(format: &str) -> Result<&'static str, String> {
    match format {
        "docx" => Ok("docx"),
        "xlsx" => Ok("xlsx"),
        "pptx" => Ok("pptx"),
        "pdf" => Ok("pdf"),
        other => Err(format!("Unsupported document format: {other}")),
    }
}

#[tauri::command]
pub async fn generate_document(
    format: String,
    title: String,
    sections: Vec<DocumentSection>,
    table: Option<DocumentTable>,
) -> Result<DocumentResult, String> {
    let extension = extension_for(&format)?;
    let default_name = format!(
        "{}.{extension}",
        title
            .to_lowercase()
            .chars()
            .map(|character| if character.is_ascii_alphanumeric() { character } else { '-' })
            .collect::<String>()
            .trim_matches('-')
    );

    let save_path = FileDialog::new()
        .set_file_name(&default_name)
        .add_filter(extension, &[extension])
        .save_file();

    let Some(save_path) = save_path else {
        return Ok(DocumentResult {
            file_path: String::new(),
            byte_size: 0,
            cancelled: true,
        });
    };

    let mut script_path: PathBuf = std::env::temp_dir();
    script_path.push(format!("airbench-docgen-{}.py", uuid::Uuid::new_v4()));
    std::fs::write(&script_path, DOCUMENT_GENERATOR_SCRIPT)
        .map_err(|error| format!("Could not stage the document generator script: {error}"))?;

    let payload = json!({
        "format": format,
        "title": title,
        "sections": sections.into_iter().map(|section| json!({ "heading": section.heading, "body": section.body })).collect::<Vec<_>>(),
        "table": table.map(|table| json!({ "headers": table.headers, "rows": table.rows })),
        "output_path": save_path.to_string_lossy(),
    });

    let mut child = Command::new("python")
        .arg(&script_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("Could not start the Python document generator: {error}"))?;

    {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or_else(|| "Could not write to the document generator's stdin.".to_string())?;
        stdin
            .write_all(payload.to_string().as_bytes())
            .await
            .map_err(|error| format!("Could not send the document payload: {error}"))?;
    }

    let output = child
        .wait_with_output()
        .await
        .map_err(|error| format!("The document generator did not finish: {error}"))?;
    let _ = std::fs::remove_file(&script_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "The document generator failed: {}",
            stderr.trim()
        ));
    }

    let byte_size = std::fs::metadata(&save_path)
        .map(|metadata| metadata.len())
        .unwrap_or(0);

    Ok(DocumentResult {
        file_path: save_path.to_string_lossy().to_string(),
        byte_size,
        cancelled: false,
    })
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct SandboxRunResult {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub timed_out: bool,
}

#[tauri::command]
pub async fn run_python_sandbox(code: String) -> Result<SandboxRunResult, String> {
    let mut temp_path = std::env::temp_dir();
    temp_path.push(format!("airbench-sandbox-{}.py", uuid::Uuid::new_v4()));
    std::fs::write(&temp_path, code)
        .map_err(|error| format!("Could not write the sandbox script: {error}"))?;

    let run = async {
        let mut child = Command::new("python")
            .arg(&temp_path)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("Could not start Python: {error}"))?;

        let mut stdout_pipe = child
            .stdout
            .take()
            .ok_or_else(|| "Could not capture sandbox stdout.".to_string())?;
        let mut stderr_pipe = child
            .stderr
            .take()
            .ok_or_else(|| "Could not capture sandbox stderr.".to_string())?;
        let stdout_task = tokio::spawn(async move {
            let mut buffer = Vec::new();
            let _ = stdout_pipe.read_to_end(&mut buffer).await;
            buffer
        });
        let stderr_task = tokio::spawn(async move {
            let mut buffer = Vec::new();
            let _ = stderr_pipe.read_to_end(&mut buffer).await;
            buffer
        });

        match tokio::time::timeout(Duration::from_secs(SANDBOX_TIMEOUT_SECS), child.wait()).await {
            Ok(status_result) => {
                let status = status_result.map_err(|error| format!("Python did not finish cleanly: {error}"))?;
                let stdout_buffer = stdout_task.await.unwrap_or_default();
                let stderr_buffer = stderr_task.await.unwrap_or_default();
                Ok(SandboxRunResult {
                    stdout: String::from_utf8_lossy(&stdout_buffer).to_string(),
                    stderr: String::from_utf8_lossy(&stderr_buffer).to_string(),
                    exit_code: status.code().unwrap_or(-1),
                    timed_out: false,
                })
            }
            Err(_) => {
                let _ = child.kill().await;
                stdout_task.abort();
                stderr_task.abort();
                Ok(SandboxRunResult {
                    stdout: String::new(),
                    stderr: format!(
                        "Execution exceeded the {SANDBOX_TIMEOUT_SECS}s sandbox timeout and was stopped."
                    ),
                    exit_code: -1,
                    timed_out: true,
                })
            }
        }
    }
    .await;

    let _ = std::fs::remove_file(&temp_path);
    run
}
