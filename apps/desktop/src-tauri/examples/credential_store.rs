use keyring::Entry as KeyringEntry;
use keyring_core::Entry;
use std::{collections::HashMap, env, io::Read};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let operation = args.next().ok_or("expected set or delete")?;
    let username = args.next().ok_or("expected credential reference")?;
    // Validation credentials are disposable and must work on developer hosts
    // without a domain-backed Enterprise logon session. The desktop transport
    // still reads the same OS credential target through the native keyring.
    if let Err(error) = KeyringEntry::store_status() {
        return Err(error.to_string().into());
    }
    let entry = Entry::new_with_modifiers(
        "org.airbench.desktop",
        &username,
        &HashMap::from([("persistence", "Session")]),
    )?;

    match operation.as_str() {
        "set" | "set-stdin" => {
            let password = if operation == "set-stdin" {
                let mut value = String::new();
                std::io::stdin().read_to_string(&mut value)?;
                value.trim_end_matches(['\r', '\n']).to_string()
            } else {
                args.next().ok_or("expected credential value")?
            };
            entry.set_password(&password)?;
            println!("credential stored for {username}");
        }
        "delete" => {
            let _ = entry.delete_credential();
            println!("credential removed for {username}");
        }
        _ => return Err("expected set or delete".into()),
    }
    Ok(())
}
