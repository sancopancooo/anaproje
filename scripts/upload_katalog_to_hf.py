# -*- coding: utf-8 -*-
"""
katalog.db (+ isteğe bağlı embeddings.db) Hugging Face dataset'e yükler.

Kullanım:
  1) https://huggingface.co/settings/tokens → Read/Write token al
  2) .env içine: HF_TOKEN=hf_...
  3) .\\venv\\Scripts\\python.exe scripts\\upload_katalog_to_hf.py

Varsayılan repo: sancopancoo/dizimibul-embeddings
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        val = v.strip().strip('"').strip("'")
        if val and k.strip() not in os.environ:
            os.environ[k.strip()] = val


def main() -> int:
    _load_env()
    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    )
    if not token:
        print("[!] HF_TOKEN yok. .env dosyasına HF_TOKEN=hf_... ekle.")
        print("    Token: https://huggingface.co/settings/tokens (write yetkisi)")
        return 2

    repo_id = os.environ.get("HF_DATASET_REPO", "sancopancoo/dizimibul-embeddings").strip()
    katalog = ROOT / "katalog.db"
    if not katalog.is_file() or katalog.stat().st_size < 1024:
        print("[!] katalog.db bulunamadı. Önce scripts/merge_catalog_dbs.py çalıştır.")
        return 2

    try:
        from huggingface_hub import HfApi, login
    except ImportError:
        print("[!] pip install huggingface_hub")
        return 2

    login(token=token, add_to_git_credential=False)
    api = HfApi(token=token)

    # Dataset yoksa oluştur
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
    except Exception:
        print(f"[+] Dataset oluşturuluyor: {repo_id}")
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)

    print(f"[+] Yükleniyor: katalog.db → {repo_id} ({katalog.stat().st_size / 1e6:.1f} MB)")
    api.upload_file(
        path_or_fileobj=str(katalog),
        path_in_repo="katalog.db",
        repo_id=repo_id,
        repo_type="dataset",
    )
    print("[+] katalog.db yüklendi.")

    # Dataset kartı
    readme = ROOT / "scripts" / "HF_DATASET_README.md"
    if readme.exists():
        api.upload_file(
            path_or_fileobj=str(readme),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
        )
        print("[+] README.md güncellendi.")

    upload_emb = "--with-embeddings" in sys.argv
    emb = ROOT / "embeddings.db"
    if upload_emb and emb.is_file():
        print(f"[+] Yükleniyor: embeddings.db ({emb.stat().st_size / 1e6:.1f} MB) — uzun sürebilir")
        api.upload_file(
            path_or_fileobj=str(emb),
            path_in_repo="embeddings.db",
            repo_id=repo_id,
            repo_type="dataset",
        )
        print("[+] embeddings.db yüklendi.")

    print(f"\nTamam → https://huggingface.co/datasets/{repo_id}")
    print("Not: Eski diziler_veritabani*.db dosyaları HF'de kalsa da API artık katalog.db tercih eder.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
