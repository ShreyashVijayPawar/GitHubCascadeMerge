Input configuration rules:

- Must be **valid JSON** with a top‑level `repositories` array.
- Each item in `repositories` must be a **JSON object**.
- Every object must have `repository: "owner/name"` (for example, `CitInternal/172598.onb-vm-gbl.hnw-services`).
- Every object must have a **non‑empty** `patToken` string, using a GitHub PAT that:
    - Has rights to manage labels, secrets, auto‑merge, and PRs, and
    - Has **no expiration**, so it can be used continuously by the cascade‑merge workflow.