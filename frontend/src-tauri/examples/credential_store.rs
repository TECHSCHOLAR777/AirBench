use keyring::Entry;
use std::{env, io::Read};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let operation = args.next().ok_or("expected set or delete")?;
    let username = args.next().ok_or("expected credential reference")?;
    let entry = Entry::new("org.airbench.desktop", &username)?;

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
