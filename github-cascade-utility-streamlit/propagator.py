import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from github import Github, GithubException
from nacl import encoding, public
from datetime import datetime, UTC
import os

# Hardcoded JIRA ID reused for all repositories
JIRA_ID = "CWS-1234"  # keep as agreed

REQUIRED_LABELS: Dict[str, Dict[str, str]] = {
    "cascade-pr": {
        "color": "0e8a16",
        "description": "PR created by cascade workflow",
    },
    "cascade-merge-conflicts": {
        "color": "b60205",
        "description": "Cascade PR has merge conflicts",
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


def parse_config(raw_json: str) -> Dict[str, Any]:
    return json.loads(raw_json)


def validate_config(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Validate that config has the minimal required shape:

    {
      "repositories": [
        {
          "repository": "owner/name",
          "patToken": "ghp_xxx"
        },
        ...
      ]
    }
    """
    errors: List[Dict[str, Any]] = []

    if not isinstance(config, dict):
        errors.append({"level": "global", "repository": None, "message": "Config must be a JSON object."})
        return errors

    repos = config.get("repositories")
    if not isinstance(repos, list) or not repos:
        errors.append({"level": "global", "repository": None, "message": "`repositories` must be a non-empty list."})
        return errors

    for idx, repo_cfg in enumerate(repos):
        if not isinstance(repo_cfg, dict):
            errors.append(
                {"level": "repository", "repository": f"index {idx}", "message": "Repository entry must be an object."}
            )
            continue

        repo_name = repo_cfg.get("repository")
        if not isinstance(repo_name, str) or repo_name.count("/") != 1:
            errors.append(
                {"level": "repository", "repository": repo_name, "message": "`repository` must be of form 'owner/name'."}
            )

        pat = repo_cfg.get("patToken")
        if not isinstance(pat, str) or not pat.strip():
            errors.append(
                {
                    "level": "repository",
                    "repository": repo_name,
                    "message": "`patToken` is required and must be non-empty.",
                }
            )

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
            return StepResult(
                status="failed",
                failed=f"Unexpected status when checking secret: {r.status_code} {r.text}",
                manualDoc=HELP_DOCS["secrets"],
            ).to_dict()

        r_pk = requests.get(f"{base}/public-key", headers=headers, timeout=10)
        if r_pk.status_code != 200:
            return StepResult(
                status="failed",
                failed=f"Failed to get public key: {r_pk.status_code} {r_pk.text}",
                manualDoc=HELP_DOCS["secrets"],
            ).to_dict()
        data = r_pk.json()
        encrypted = _encrypt_secret(data["key"], cascade_token)
        put_body = {"encrypted_value": encrypted, "key_id": data["key_id"]}
        r_put = requests.put(f"{base}/CASCADE_GITHUB_TOKEN", headers=headers, json=put_body, timeout=10)
        if r_put.status_code not in (201, 204):
            return StepResult(
                status="failed",
                failed=f"Failed to create secret: {r_put.status_code} {r_put.text}",
                manualDoc=HELP_DOCS["secrets"],
            ).to_dict()
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
                    gh_repo.update_file(
                        path=target_path,
                        message=commit_message,
                        content=content,
                        sha=existing.sha,
                        branch=feature_branch,
                    )
                    updated.append(target_path)
            except Exception:
                gh_repo.create_file(
                    path=target_path,
                    message=commit_message,
                    content=content,
                    branch=feature_branch,
                )
                created.append(target_path)

        pr = None
        pr_url: Optional[str] = None
        pr_state: Optional[str] = None  # "OPEN" or "CLOSED"

        if created or updated:
            # Create PR from feature branch into default branch
            pr = gh_repo.create_pull(
                title="Add/update cascade workflows",
                body="Automated setup of cascade workflows.",
                head=feature_branch,
                base=default_branch,
            )
            pr_url = pr.html_url
            pr_state = "OPEN"

            # Poll up to 5 times (2s interval) for mergeability to settle
            import time

            max_attempts = 5
            delay_seconds = 2

            for attempt in range(1, max_attempts + 1):
                pr = gh_repo.get_pull(pr.number)  # refresh
                if pr.mergeable is not None and pr.mergeable_state != "unknown":
                    break
                if attempt < max_attempts:
                    time.sleep(delay_seconds)

            # Try to auto-merge the PR if it's cleanly mergeable
            try:
                if pr.mergeable and pr.mergeable_state == "clean":
                    merge_result = pr.merge(merge_method="merge")
                    # PyGithub merge returns a dict-like object
                    merged_flag = False
                    if isinstance(merge_result, dict):
                        merged_flag = merge_result.get("merged", False)
                    else:
                        merged_flag = getattr(merge_result, "merged", False)
                    pr_state = "CLOSED" if merged_flag else "OPEN"
                else:
                    pr_state = "OPEN"
            except Exception as merge_exc:  # noqa: BLE001
                # Auto-merge is best-effort; record the error but don't fail the whole step
                return StepResult(
                    status="partial",
                    manualDoc=HELP_DOCS["workflows"],
                    failed=f"PR created but auto-merge failed: {merge_exc}",
                    details={
                        "created": created,
                        "updated": updated,
                        "branch": feature_branch,
                        "pullRequestUrl": pr_url,
                        "pullRequestState": pr_state or "OPEN",
                    },
                ).to_dict()
        else:
            # Nothing changed, no PR needed
            pr_url = None
            pr_state = None

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
                "pullRequestState": pr_state,
            },
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        return StepResult(status="failed", failed=str(exc), manualDoc=HELP_DOCS["workflows"]).to_dict()


def process_repository(repo_cfg: Dict[str, Any]) -> Dict[str, Any]:
    repo_name = repo_cfg["repository"]
    owner, repo = repo_name.split("/", 1)
    token = repo_cfg["patToken"].strip()

    gh = Github(token)
    gh_repo = gh.get_repo(f"{owner}/{repo}")

    result: Dict[str, Any] = {
        "repository": repo_name,
        "steps": {},
    }

    # Always ensure labels
    result["steps"]["labels"] = ensure_labels(gh_repo)

    # Always ensure CASCADE_GITHUB_TOKEN secret using the same PAT
    result["steps"]["secret"] = ensure_cascade_secret(owner, repo, token, token)

    # Always enable auto-merge
    result["steps"]["enableAutoMerge"] = ensure_auto_merge_enabled(gh_repo)

    # Always sync workflows using hardcoded JIRA_ID
    result["steps"]["workflows"] = sync_workflows_via_feature_branch(
        gh_repo=gh_repo,
        jira_id=JIRA_ID,
        templates_dir="templates/workflows",
    )

    return result


def run_all(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    repos = config.get("repositories", [])
    results: List[Dict[str, Any]] = []
    for repo_cfg in repos:
        try:
            results.append(process_repository(repo_cfg))
        except Exception as exc:  # noqa: BLE001
            repo_name = repo_cfg.get("repository")
            results.append(
                {
                    "repository": repo_name,
                    "steps": {
                        "labels": StepResult(status="failed", failed=str(exc)).to_dict(),
                        "secret": StepResult(status="failed", failed=str(exc)).to_dict(),
                        "enableAutoMerge": StepResult(status="failed", failed=str(exc)).to_dict(),
                        "workflows": StepResult(status="failed", failed=str(exc)).to_dict(),
                    },
                }
            )
    return results