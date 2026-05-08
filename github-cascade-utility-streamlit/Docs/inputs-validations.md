# Cascade Workflow Bootstrapper – Input and Validation Guide

This document explains all inputs required by the Cascade Workflow Bootstrapper and how each input is validated before any changes are made to repositories.[^2][^1]

***

## 1. Overview of inputs

The utility has two main input layers:

1. **Configuration JSON** typed or pasted into the Streamlit UI.
2. **GitHub environment** inferred from that JSON (repositories, PAT permissions).[^1][^2]

The configuration JSON drives everything. If validation fails, the utility **does not** modify any repository and instead shows a list of validation errors in the UI.[^2][^1]

***

## 2. Configuration JSON structure

The JSON at minimum must be an object with a single key, `repositories`.[^2]

### 2.1 Top‑level requirements

- **Type**: The root must be a JSON object.
    - If the root is not an object (e.g., an array or string), validation fails with a global error:
        - `Config must be a JSON object.`[^2]
- **Key `repositories`**:
    - Must exist.
    - Must be a **non‑empty array**.
    - If missing, not a list, or empty, validation fails with a global error:
        - ````repositories` must be a non-empty list.```[^2]

Example of a valid minimal structure:

```json
{
  "repositories": [
    {
      "repository": "owner/repo-name",
      "patToken": "your_personal_access_token_here"
    }
  ]
}
```


***

## 3. Per‑repository input validation

Each entry in `repositories` describes one target repository and is validated independently.[^2]

For each element `repo_cfg` in `repositories`:

### 3.1. Repository entry type

- **Requirement**: Each `repo_cfg` must be a JSON object.
- **Failure case**: If any entry is not an object (for example, a string or array), validation adds an error:
    - Level: `repository`

```
- Repository: `"index <i>"` (where `<i>` is the array index)  
```

    - Message: `Repository entry must be an object.`[^2]

The utility then skips further validation of that entry.

***

### 3.2. `repository` field

- **Field name**: `repository`
- **Type**: String
- **Required**: Yes

**Rule:**

- The value must be a non‑empty string of the form `"owner/name"` with exactly one `/` character.[^2]

**Valid examples:**

- `"ShreyashVijayPawar/FlyAway"`
- `"CitInternal/172598.onb-vm-gbl.hnw-services"`

**Invalid examples:**

- `"FlyAway"` (missing owner)
- `"owner/repo/extra"` (too many `/`)
- `""` or whitespace only
- `null` or a non‑string type

**Error on failure:**

- Level: `repository`
- Repository: the invalid value (if any)
- Message: ````repository` must be of form 'owner/name'.```[^2]

This error appears in the Streamlit UI as:

> `- **<repository or (global)>**: `repository` must be of form 'owner/name'.`[^1][^2]

***

### 3.3. `patToken` field

- **Field name**: `patToken`
- **Type**: String
- **Required**: Yes

**Rule:**

- The value must be a non‑empty string. Any surrounding whitespace is allowed but is stripped before use.[^2]
- The PAT should:
    - Have no expiration (or be long‑lived per org policy).
    - Have sufficient permissions to:
        - create labels,
        - create/update repository secrets,
        - enable auto‑merge,
        - push workflow files and open/merge PRs.[^3][^2]

**Validation check (structural):**

- If `patToken` is missing, not a string, or an empty/whitespace‑only string:
    - Level: `repository`
    - Repository: the `repository` name for that entry
    - Message: ````patToken` is required and must be non-empty.```[^2]

**Runtime behavior (permissions):**

Even if the field passes the structural check, the token may still lack permissions. In that case, later steps (labels, secrets, auto‑merge, workflows) may **fail at runtime**, and those failures will appear in the Results table as `FAILED` for that step.[^1][^2]

***

## 4. Streamlit parsing and validation behavior

Validation happens in two phases when you click **“Run setup \& propagate”**.[^1]

### 4.1. JSON parsing

1. The utility reads the text from the **Configuration JSON** textarea.
2. If the text is empty or whitespace, the app shows:
    - `Configuration JSON is required.` and stops.[^1]
3. If the text is non‑empty, it attempts to parse it as JSON.
    - If parsing fails (invalid JSON syntax), the app shows:
        - `Failed to parse JSON: <error message>` and stops.[^1]
    - Only if parsing succeeds does it move on to semantic validation.

### 4.2. Semantic validation

Once JSON is parsed, the app calls `validate_config(config)`.[^2]

- `validate_config` runs all the checks described above:
    - Root object type.
    - `repositories` array exists and is non‑empty.
    - Each repository entry is an object.
    - `repository` field structure.
    - `patToken` field presence and non‑emptiness.[^2]
- If **any** errors are returned:
    - The app shows:
        - `Configuration has validation errors:`
    - Then lists each problem per line as:

```
- `- **<repository or (global)>**: <message>`  
```

    - The run is aborted; **no** repositories are touched.[^1][^2]
- If there are **no** errors:
    - The app proceeds to actually run `run_all(config)` and apply changes to each repository.[^1][^2]

***

## 5. Runtime validations via GitHub API

After semantic validation passes, further checks effectively happen inside GitHub responses:[^2]

1. **Repository existence and token access**
    - When the app calls GitHub with `owner/repo` and the PAT, GitHub will respond with an error if:
        - The repo does not exist, or
        - The PAT does not have access.
    - In that case, each step for that repo (`labels`, `secret`, `enableAutoMerge`, `workflows`) is marked as `failed`, and the error message is captured for that repo.[^2]
2. **Secret creation**
    - If the `public-key` endpoint or secret creation endpoints fail (e.g., Actions disabled or rights missing), the `secret` step is marked as `failed`.[^2]
3. **Auto‑merge**
    - If editing repo settings to set `allow_auto_merge=True` fails (e.g., org disallows auto‑merge), the `enableAutoMerge` step is `failed`.[^2]
4. **Workflow PR**
    - If the utility cannot read templates or cannot create/update files or PRs, the `workflows` step is `failed`.
    - If mergeability never stabilizes, the PR may remain `OPEN`, which you can see from the `Workflow code` column and then investigate manually.[^2]

These runtime validations are not part of the JSON schema but are important to understand when interpreting `FAILED` statuses.

***

## 6. Example: invalid vs. valid inputs

### 6.1. Invalid example (multiple issues)

```json
{
  "repositories": [
    "ShreyashVijayPawar/FlyAway",
    {
      "repository": "FlyAway",
      "patToken": ""
    }
  ]
}
```

Validation errors:

- `index 0`: Repository entry must be an object.
- `FlyAway`: `repository` must be of form 'owner/name'.
- `FlyAway`: `patToken` is required and must be non-empty.[^2]

The app will show all three messages and will not run any setup.[^1]

### 6.2. Corrected example

```json
{
  "repositories": [
    {
      "repository": "ShreyashVijayPawar/FlyAway",
      "patToken": "ghp_xxx_your_token"
    },
    {
      "repository": "ShreyashVijayPawar/LockerProject",
      "patToken": "ghp_xxx_your_token"
    }
  ]
}
```

- Root is an object.
- `repositories` is a non‑empty array of objects.
- Each `repository` has form `owner/name`.
- Each `patToken` is non‑empty.

Structural validation passes; any later failures will be due to GitHub‑side constraints (permissions, settings).

***

This document is meant to be a quick reference for **what you must provide** to the utility and **how it checks your config before touching any repos**.

From your perspective as the author of the tool, is there any additional field you’re considering adding to the JSON (for example, per‑repo flags in the future) that should already be reserved or mentioned in this validation guide?

<div align="center">⁂</div>

[^1]: app.py

[^2]: propagator.py

[^3]: setup-guide-for-cascade-merge.md

