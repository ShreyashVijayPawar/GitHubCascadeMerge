import base64
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

API_BASE = "https://api.github.com"
SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR / "templates" / "workflows"
WORKFLOW_FILES = {
    "cascade-next-pr.yml": ".github/workflows/cascade-next-pr.yml",
    "cascade-conflict-check.yml": ".github/workflows/cascade-conflict-check.yml",
}


class GitHubApiError(Exception):
    pass


class GitHubClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _request(self, method: str, url: str, expected_status=None, **kwargs):
        response = self.session.request(method, url, **kwargs)
        if expected_status and response.status_code not in expected_status:
            raise GitHubApiError(f"GitHub API error {response.status_code}: {response.text}")
        if not expected_status and response.status_code >= 400:
            raise GitHubApiError(f"GitHub API error {response.status_code}: {response.text}")
        if response.text:
            return response.json()
        return None

    def get_repository(self, owner: str, repo: str):
        return self._request("GET", f"{API_BASE}/repos/{owner}/{repo}", expected_status={200})

    def get_branch(self, owner: str, repo: str, branch: str):
        return self._request("GET", f"{API_BASE}/repos/{owner}/{repo}/branches/{branch}", expected_status={200})

    def create_branch(self, owner: str, repo: str, branch_name: str, sha: str):
        payload = {"ref": f"refs/heads/{branch_name}", "sha": sha}
        return self._request("POST", f"{API_BASE}/repos/{owner}/{repo}/git/refs", json=payload, expected_status={201})

    def get_content(self, owner: str, repo: str, path: str, branch: str):
        response = self.session.get(f"{API_BASE}/repos/{owner}/{repo}/contents/{path}", params={"ref": branch})
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise GitHubApiError(f"GitHub API error {response.status_code}: {response.text}")
        return response.json()

    def put_file(self, owner: str, repo: str, path: str, branch: str, message: str, content: str, sha=None):
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        return self._request("PUT", f"{API_BASE}/repos/{owner}/{repo}/contents/{path}", json=payload, expected_status={200, 201})

    def create_pull_request(self, owner: str, repo: str, title: str, head: str, base: str, body: str):
        payload = {"title": title, "head": head, "base": base, "body": body}
        return self._request("POST", f"{API_BASE}/repos/{owner}/{repo}/pulls", json=payload, expected_status={201})


def parse_repo_url(repository_url: str):
    cleaned = repository_url.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    parsed = urlparse(cleaned)
    path = parsed.path.strip("/")
    parts = path.split("/")

    if parsed.netloc.lower() != "github.com" or len(parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {repository_url}")

    return parts[0], parts[1]


def load_templates():
    templates = {}
    for filename in WORKFLOW_FILES:
        file_path = TEMPLATES_DIR / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Missing workflow template: {file_path}")
        templates[filename] = file_path.read_text(encoding="utf-8")
    return templates


def create_feature_branch_name(prefix: str):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{timestamp}"


def propagate_single(repo_input: dict, branch_prefix: str = "feature/add-cascade-workflows"):
    repository_url = repo_input.get("repositoryUrl", "").strip()
    pat_token = repo_input.get("patToken", "").strip()
    raise_pr = repo_input.get("raisePr", "N").strip().upper()

    if not repository_url:
        raise ValueError("repositoryUrl is required")
    if not pat_token:
        raise ValueError("patToken is required")
    if raise_pr not in {"Y", "N"}:
        raise ValueError("raisePr must be Y or N")

    owner, repo = parse_repo_url(repository_url)
    client = GitHubClient(pat_token)
    templates = load_templates()

    repo_data = client.get_repository(owner, repo)
    default_branch = repo_data["default_branch"]

    branch_data = client.get_branch(owner, repo, default_branch)
    sha = branch_data["commit"]["sha"]

    feature_branch = create_feature_branch_name(branch_prefix)
    client.create_branch(owner, repo, feature_branch, sha)

    for source_name, target_path in WORKFLOW_FILES.items():
        content = templates[source_name]
        existing = client.get_content(owner, repo, target_path, feature_branch)
        existing_sha = existing.get("sha") if existing else None
        client.put_file(
            owner=owner,
            repo=repo,
            path=target_path,
            branch=feature_branch,
            message=f"Add/update {target_path}",
            content=content,
            sha=existing_sha,
        )

    result = {
        "repositoryUrl": repository_url,
        "owner": owner,
        "repo": repo,
        "defaultBranch": default_branch,
        "featureBranch": feature_branch,
        "raisePr": raise_pr,
        "pullRequestUrl": None,
        "status": "SUCCESS",
        "message": "Feature branch created and workflow files pushed successfully.",
    }

    if raise_pr == "Y":
        pr = client.create_pull_request(
            owner=owner,
            repo=repo,
            title="Add cascade merge workflows",
            head=feature_branch,
            base=default_branch,
            body="This PR adds the cascade merge workflow files.",
        )
        result["pullRequestUrl"] = pr.get("html_url")
        result["message"] = "Feature branch created, workflow files pushed, and PR raised successfully."

    return result


def propagate_batch(payload: dict, branch_prefix: str = "feature/add-cascade-workflows"):
    repositories = payload.get("repositories", [])
    if not isinstance(repositories, list) or not repositories:
        raise ValueError("Input JSON must contain a non-empty 'repositories' array")

    results = []
    for repo_input in repositories:
        try:
            results.append(propagate_single(repo_input, branch_prefix=branch_prefix))
        except Exception as exc:
            results.append({
                "repositoryUrl": repo_input.get("repositoryUrl"),
                "owner": None,
                "repo": None,
                "defaultBranch": None,
                "featureBranch": None,
                "raisePr": repo_input.get("raisePr"),
                "pullRequestUrl": None,
                "status": "FAILED",
                "message": str(exc),
            })
    return results
