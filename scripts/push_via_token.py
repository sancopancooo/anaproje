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
        # Never echo Authorization / tokens
        raise RuntimeError(f"HTTP {e.code}: {err}") from None


def main() -> int:
    token = load_env().get("GITHUB_TOKEN") or ""
    if not token:
        print("[!] .env icinde GITHUB_TOKEN yok.")
        return 2

    try:
        from dulwich import porcelain
        from dulwich.repo import Repo
    except ImportError:
        print("[!] dulwich yok: pip install dulwich")
        return 2

    # Quick secret scan before push
    bad = []
    for p in ROOT.rglob("*.py"):
        if ".git" in p.parts or "venv" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Scan for Groq-style keys without embedding a real secret
        if re.search(r"gs" + r"k_[A-Za-z0-9]{20,}", txt):
            bad.append(str(p.relative_to(ROOT)))
    if bad:
        print("[!] Push iptal: dosyalarda groq key kaldı:")
        for b in bad:
            print("   -", b)
        return 2

    repo = Repo(str(ROOT))
    head = repo.refs[b"refs/heads/master"].decode("ascii")
    print(f"[+] Local master: {head[:12]}")

    _, repo_info = api(token, "GET", "https://api.github.com/repos/sancopancooo/anaproje")
    default_branch = repo_info.get("default_branch") or "main"
    print(f"[+] Remote default: {default_branch}")

    # Auth via callback — token never appears in remote URL / error strings
    def get_creds(*_args, **_kwargs):
        return ("x-access-token", token)

    print("[+] dulwich push master:main (force)...")
    try:
        porcelain.push(
            str(ROOT),
            "https://github.com/sancopancooo/anaproje.git",
            refspecs=[b"+refs/heads/master:refs/heads/main"],
            get_credentials=get_creds,
        )
    except TypeError:
        # Older dulwich: username/password in URL but redact on error
        remote = (
            "https://x-access-token:"
            + quote(token, safe="")
            + "@github.com/sancopancooo/anaproje.git"
        )
        try:
            porcelain.push(
                str(ROOT),
                remote,
                refspecs=[b"+refs/heads/master:refs/heads/main"],
            )
        except Exception as e:
            msg = str(e)
            msg = msg.replace(token, "***")
            print(f"[!] Push failed: {type(e).__name__}: {msg[:500]}")
            return 1
    except Exception as e:
        msg = str(e).replace(token, "***")
        print(f"[!] Push failed: {type(e).__name__}: {msg[:500]}")
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
