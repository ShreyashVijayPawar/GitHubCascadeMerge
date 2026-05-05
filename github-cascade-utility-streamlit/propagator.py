import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from github import Github, GithubException
from nacl import encoding, public
from datetime import datetime, UTC
import os

FLAG_KEYS = ["createLabels", "createSecret", "enableAutoMerge", "createWorkflows"]
DEFAULT_FLAG_VALUE = "Y"

REQUIRED_LABELS: Dict[str, Dict[str, str]] = {
    "cascade-pr": {
        "color": "0e8a16",
        "description": "PR created by cascade workflow",
    },
    "cascade-final-pr": {
        "color": "5319e7",
        "description": "Final cascade PR into non-release branch",
    },
    "cascade-conflict": {
        "color": "b60205",
        "description": "Cascade PR has merge conflicts",
    },
    "cascade-blocked": {
        "color": "d93f0b",
        "description": "Cascade PR blocked by required checks or rules",
    },
    "cascade-unstable": {
        "color": "f9d0c4",
        "description": "Mergeability unstable after cascade polling",
    },
    "cascade-pending": {
        "color": "c2e0c6",
        "description": "Cascade PR mergeability still pending",
    },
    "cascade-manual-review": {
        "color": "fef2c0",
        "description": "Cascade PR needs manual attention",
    },
}

HELP_DOCS = {
    "labels": "Docs/manual-create-labels.md",
    "secrets": "Docs/manual-create-secret.md",
    "autoMerge": "Docs/manual-enable-auto-merge.md",
    "workflows": "Docs/manual-setup-workflows.md",
}


@dataclass
class StepResult:
    status: str
    failed: Optional[str] = None
    manualDoc: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {"status": self.status}
        if self.failed:
            data["failed"] = self.failed
        if self.manualDoc:
            data["manualDoc"] = self.manualDoc
        data.update(self.details)
        return data


def _normalize_flag(value: Optional[str]) -> str:
    if value is None:
        return DEFAULT_FLAG_VALUE
    v = value.strip().upper()
    return v if v in ("Y", "N") else DEFAULT_FLAG_VALUE


def resolve_flags(default_flags: Optional[Dict[str, str]], repo_flags: Optional[Dict[str, str]]) -> Dict[str, str]:
    default_flags = default_flags or {}
    repo_flags = repo_flags or {}
    effective: Dict[str, str] = {}
    for key in FLAG_KEYS:
        if key in repo_flags:
            effective[key] = _normalize_flag(repo_flags[key])
        elif key in default_flags:
            effective[key] = _normalize_flag(default_flags[key])
        else:
            effective[key] = DEFAULT_FLAG_VALUE
    return effective


def parse_config(raw_json: str) -> Dict[str, Any]:
    return json.loads(raw_json)


def validate_config(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []

    if not isinstance(config, dict):
        errors.append({"level": "global", "repository": None, "message": "Config must be a JSON object."})
        return errors

    repos = config.get("repositories")
    if not isinstance(repos, list) or not repos:
        errors.append({"level": "global", "repository": None, "message": "`repositories` must be a non-empty list."})
        return errors

    default_flags = config.get("defaultSetupFlags", {})

    for idx, repo_cfg in enumerate(repos):
        if not isinstance(repo_cfg, dict):
            errors.append({"level": "repository", "repository": f"index {idx}", "message": "Repository entry must be an object."})
            continue

        repo_name = repo_cfg.get("repository")
        if not isinstance(repo_name, str) or repo_name.count("/") != 1:
            errors.append({"level": "repository", "repository": repo_name, "message": "`repository` must be of form 'owner/name'."})

        pat = repo_cfg.get("patToken")
        if not isinstance(pat, str) or not pat.strip():
            errors.append({"level": "repository", "repository": repo_name, "message": "`patToken` is required and must be non-empty."})

        repo_flags = repo_cfg.get("setupFlags", {})
        if repo_flags and not isinstance(repo_flags, dict):
            errors.append({"level": "repository", "repository": repo_name, "message": "`setupFlags` must be an object if present."})
            repo_flags = {}

        effective = resolve_flags(default_flags, repo_flags)

        if effective.get("createWorkflows", "Y") == "Y":
            jira_id = repo_cfg.get("jiraId")
            if not isinstance(jira_id, str) or not jira_id.strip():
                errors.append({
                    "level": "repository",
                    "repository": repo_name,
                    "message": "`jiraId` is required and must be non-empty when createWorkflows = 'Y'.",
                })

    return errors


def ensure_labels(gh_repo) -> Dict[str, Any]:
    created: List[str] = []
    existing: List[str] = []
    missing: List[str] = []
    label_errors: Dict[str, str] = {}

    try:
        # Collect existing label names
        current = {lbl.name for lbl in gh_repo.get_labels()}

        # Try to ensure each required label
        for name, meta in REQUIRED_LABELS.items():
            if name in current:
                existing.append(name)
                continue

            try:
                gh_repo.create_label(
                    name=name,
                    color=meta["color"],
                    description=meta["description"],
                )
                created.append(name)
            except GithubException as create_exc:
                # Could not create this label; record as missing
                missing.append(name)
                msg = getattr(create_exc, "data", None) or str(create_exc)
                label_errors[name] = str(msg)

        # Decide overall status
        if missing and (created or existing):
            status = "partial"
        elif missing and not (created or existing):
            status = "failed"
        elif created and not missing:
            status = "created"
        else:
            status = "alreadyPresent"

        return StepResult(
            status=status,
            manualDoc=HELP_DOCS["labels"],
            details={
                "createdLabels": created,
                "existingLabels": existing,
                "missingLabels": missing,
                "labelErrors": label_errors,
            },
        ).to_dict()

    except Exception as exc:  # noqa: BLE001
        return StepResult(
            status="failed",
            failed=str(exc),
            manualDoc=HELP_DOCS["labels"],
        ).to_dict()


def _encrypt_secret(public_key: str, secret_value: str) -> str:
    pk = public.PublicKey(public_key, encoder=encoding.Base64Encoder)
    sealed_box = public.SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return encoding.Base64Encoder.encode(encrypted).decode("utf-8")


def ensure_cascade_secret(owner: str, repo: str, pat: str, cascade_token: str) -> Dict[str, Any]:
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    base = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets"

    try:
        r = requests.get(f"{base}/CASCADE_GITHUB_TOKEN", headers=headers, timeout=10)
        if r.status_code == 200:
            return StepResult(status="alreadyPresent", manualDoc=HELP_DOCS["secrets"]).to_dict()
        if r.status_code not in (404,):
            return StepResult(status="failed", failed=f"Unexpected status when checking secret: {r.status_code} {r.text}", manualDoc=HELP_DOCS["secrets"]).to_dict()

        r_pk = requests.get(f"{base}/public-key", headers=headers, timeout=10)
        if r_pk.status_code != 200:
            return StepResult(status="failed", failed=f"Failed to get public key: {r_pk.status_code} {r_pk.text}", manualDoc=HELP_DOCS["secrets"]).to_dict()
        data = r_pk.json()
        encrypted = _encrypt_secret(data["key"], cascade_token)
        put_body = {"encrypted_value": encrypted, "key_id": data["key_id"]}
        r_put = requests.put(f"{base}/CASCADE_GITHUB_TOKEN", headers=headers, json=put_body, timeout=10)
        if r_put.status_code not in (201, 204):
            return StepResult(status="failed", failed=f"Failed to create secret: {r_put.status_code} {r_put.text}", manualDoc=HELP_DOCS["secrets"]).to_dict()
        return StepResult(status="created", manualDoc=HELP_DOCS["secrets"]).to_dict()
    except Exception as exc:  # noqa: BLE001
        return StepResult(status="failed", failed=str(exc), manualDoc=HELP_DOCS["secrets"]).to_dict()


def ensure_auto_merge_enabled(gh_repo) -> Dict[str, Any]:
    try:
        if getattr(gh_repo, "allow_auto_merge", False):
            return StepResult(status="alreadyEnabled", manualDoc=HELP_DOCS["autoMerge"]).to_dict()
        gh_repo.edit(allow_auto_merge=True)
        return StepResult(status="enabled", manualDoc=HELP_DOCS["autoMerge"]).to_dict()
    except Exception as exc:  # noqa: BLE001
        return StepResult(status="failed", failed=str(exc), manualDoc=HELP_DOCS["autoMerge"]).to_dict()


def _make_feature_branch_name() -> str:
    ts = datetime.now(UTC).strftime("%d_%m_%Y_%H_%M_%S")
    return f"feature/cascade-workflows-{ts}"


def sync_workflows_via_feature_branch(gh_repo, jira_id: str, templates_dir: str) -> Dict[str, Any]:
    created: List[str] = []
    updated: List[str] = []

    try:
        default_branch = gh_repo.default_branch
        ref = gh_repo.get_git_ref(f"heads/{default_branch}")
        base_sha = ref.object.sha

        feature_branch = _make_feature_branch_name()
        gh_repo.create_git_ref(ref=f"refs/heads/{feature_branch}", sha=base_sha)

        commit_message = f"{jira_id} - Cascade workflow configuration"

        for filename in ("cascade-next-pr.yml", "cascade-conflict-check.yml"):
            rel_path = os.path.join(templates_dir, filename)
            with open(rel_path, "r", encoding="utf-8") as f:
                content = f.read()
            target_path = f".github/workflows/{filename}"
            try:
                existing = gh_repo.get_contents(target_path, ref=feature_branch)
                current_content = existing.decoded_content.decode("utf-8")
                if current_content != content:
                    gh_repo.update_file(path=target_path, message=commit_message, content=content, sha=existing.sha, branch=feature_branch)
                    updated.append(target_path)
            except Exception:
                gh_repo.create_file(path=target_path, message=commit_message, content=content, branch=feature_branch)
                created.append(target_path)

        if created or updated:
            pr = gh_repo.create_pull(
                title="Add/update cascade workflows",
                body="Automated setup of cascade workflows.",
                head=feature_branch,
                base=default_branch,
            )
            pr_url = pr.html_url
        else:
            pr_url = None

        if created and not updated:
            status = "created"
        elif updated and not created:
            status = "updated"
        elif created and updated:
            status = "partial"
        else:
            status = "alreadyPresent"

        return StepResult(
            status=status,
            manualDoc=HELP_DOCS["workflows"],
            details={
                "created": created,
                "updated": updated,
                "branch": feature_branch,
                "pullRequestUrl": pr_url,
            },
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        return StepResult(status="failed", failed=str(exc), manualDoc=HELP_DOCS["workflows"]).to_dict()


def process_repository(repo_cfg: Dict[str, Any], default_flags: Dict[str, str]) -> Dict[str, Any]:
    repo_name = repo_cfg["repository"]
    owner, repo = repo_name.split("/", 1)
    token = repo_cfg["patToken"].strip()
    jira_id = repo_cfg.get("jiraId")

    flags = resolve_flags(default_flags, repo_cfg.get("setupFlags"))

    gh = Github(token)
    gh_repo = gh.get_repo(f"{owner}/{repo}")

    result: Dict[str, Any] = {
        "repository": repo_name,
        "flags": flags,
        "steps": {},
    }

    if flags["createLabels"] == "Y":
        result["steps"]["labels"] = ensure_labels(gh_repo)
    else:
        result["steps"]["labels"] = StepResult(status="skippedByFlag").to_dict()

    if flags["createSecret"] == "Y":
        result["steps"]["secret"] = ensure_cascade_secret(owner, repo, token, token)
    else:
        result["steps"]["secret"] = StepResult(status="skippedByFlag").to_dict()

    if flags["enableAutoMerge"] == "Y":
        result["steps"]["enableAutoMerge"] = ensure_auto_merge_enabled(gh_repo)
    else:
        result["steps"]["enableAutoMerge"] = StepResult(status="skippedByFlag").to_dict()

    if flags["createWorkflows"] == "Y":
        if not isinstance(jira_id, str) or not jira_id.strip():
            result["steps"]["workflows"] = StepResult(
                status="failed",
                failed="`jiraId` is required and must be non-empty when createWorkflows = 'Y' for this repository.",
                manualDoc=HELP_DOCS["workflows"],
            ).to_dict()
        else:
            result["steps"]["workflows"] = sync_workflows_via_feature_branch(
                gh_repo=gh_repo,
                jira_id=jira_id.strip(),
                templates_dir="templates/workflows",
            )
    else:
        result["steps"]["workflows"] = StepResult(status="skippedByFlag").to_dict()

    return result


def run_all(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    default_flags = config.get("defaultSetupFlags", {})
    repos = config.get("repositories", [])
    results: List[Dict[str, Any]] = []
    for repo_cfg in repos:
        try:
            results.append(process_repository(repo_cfg, default_flags))
        except Exception as exc:  # noqa: BLE001
            repo_name = repo_cfg.get("repository")
            results.append({
                "repository": repo_name,
                "flags": resolve_flags(default_flags, repo_cfg.get("setupFlags")),
                "steps": {
                    "labels": StepResult(status="failed", failed=str(exc)).to_dict(),
                    "secret": StepResult(status="failed", failed=str(exc)).to_dict(),
                    "enableAutoMerge": StepResult(status="failed", failed=str(exc)).to_dict(),
                    "workflows": StepResult(status="failed", failed=str(exc)).to_dict(),
                },
            })
    return results
