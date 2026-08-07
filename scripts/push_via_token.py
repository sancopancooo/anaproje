# -*- coding: utf-8 -*-
"""Push local git repo to GitHub using GITHUB_TOKEN (bypasses broken git libcurl)."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api(token: str, method: str, url: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "dizimibul-push",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            return r.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code}: {err}") from None


def main() -> int:
    token = load_env().get("GITHUB_TOKEN") or ""
    if not token:
        print("[!] .env icinde GITHUB_TOKEN yok.")
        return 2

    try:
        from dulwich import porcelain
        from dulwich.client import HttpGitClient
        from dulwich.repo import Repo
    except ImportError:
        print("[!] dulwich yok: pip install dulwich")
        return 2

    bad = []
    for p in ROOT.rglob("*.py"):
        if ".git" in p.parts or "venv" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if re.search(r"gs" + r"k_[A-Za-z0-9]{20,}", txt):
            bad.append(str(p.relative_to(ROOT)))
    if bad:
        print("[!] Push iptal: dosyalarda groq key kaldı:")
        for b in bad:
            print("   -", b)
        return 2

    repo = Repo(str(ROOT))
    head = repo.refs[b"refs/heads/master"]
    print(f"[+] Local master: {head.decode('ascii')[:12]}")

    _, repo_info = api(token, "GET", "https://api.github.com/repos/sancopancooo/anaproje")
    print(f"[+] Remote default: {repo_info.get('default_branch') or 'main'}")

    client = HttpGitClient(
        "https://github.com/sancopancooo/anaproje/",
        username="x-access-token",
        password=token,
    )

    def update_refs(refs):
        # Force update main to local master tip
        new_refs = dict(refs)
        new_refs[b"refs/heads/main"] = head
        return new_refs

    print("[+] send_pack master -> main (force)...")
    try:
        client.send_pack(
            "sancopancooo/anaproje",
            update_refs,
            repo.generate_pack_data,
        )
    except Exception as e:
        msg = str(e).replace(token, "***")
        # Fallback: porcelain with redacted error
        try:
            remote = (
                "https://x-access-token:"
                + quote(token, safe="")
                + "@github.com/sancopancooo/anaproje.git"
            )
            porcelain.push(
                str(ROOT),
                remote,
                refspecs=[b"+refs/heads/master:refs/heads/main"],
            )
        except Exception as e2:
            msg2 = str(e2).replace(token, "***")
            print(f"[!] Push failed: {type(e).__name__}: {msg[:300]}")
            print(f"[!] Fallback failed: {type(e2).__name__}: {msg2[:500]}")
            return 1

    _, after = api(
        token,
        "GET",
        "https://api.github.com/repos/sancopancooo/anaproje/commits/main",
    )
    print(f"[OK] GitHub main: {after['sha'][:12]}")
    print("[OK] https://github.com/sancopancooo/anaproje")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
