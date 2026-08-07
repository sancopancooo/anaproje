# -*- coding: utf-8 -*-
"""
Hugging Face Dataset'ten büyük DB dosyalarını indirir.
Repo: HF_DATASET_REPO (varsayılan: sancopancoo/dizimibul-embeddings)
Token: HF_TOKEN veya HUGGING_FACE_HUB_TOKEN (private dataset için zorunlu)

Tercih: tek katalog.db (diziler + filmler).
Eski iki dosya varsa birleştirilir.
"""
from __future__ import annotations

import os
import shutil
import sys


REQUIRED_LOCAL_NAMES = (
    "embeddings.db",
    "katalog.db",
)

LEGACY_PAIR = (
    "diziler_veritabani.db",
    "diziler_veritabanı.db",
)


def _token():
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        or None
    )


def _repo_id():
    return os.environ.get("HF_DATASET_REPO", "sancopancoo/dizimibul-embeddings").strip()


def _file_ok(path: str, min_bytes: int = 1024) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


def _resolve_remote_name(wanted: str, available: set[str]) -> str | None:
    if wanted in available:
        return wanted
    wanted_ascii = wanted.replace("ı", "i").replace("İ", "I")
    for name in available:
        if name.replace("ı", "i").replace("İ", "I") == wanted_ascii:
            return name
    if wanted == "katalog.db":
        for alt in ("katalog.db", "catalog.db", "dizimibul_katalog.db"):
            if alt in available:
                return alt
    return None


def _try_merge_legacy() -> bool:
    """Eski iki DB varsa katalog.db üret."""
    try:
        from db_paths import merge_catalog_databases, find_legacy_series_db, find_legacy_movies_db
        if not find_legacy_series_db() or not find_legacy_movies_db():
            return False
        report = merge_catalog_databases(archive_legacy=False)
        return bool(report.get("diziler") or report.get("skipped") or _file_ok("katalog.db"))
    except Exception as e:
        print(f"[HF] Legacy birleştirme uyarısı: {e}")
        return False


def ensure_assets(target_dir: str | None = None) -> None:
    target_dir = target_dir or os.path.dirname(os.path.abspath(__file__))
    os.chdir(target_dir)

    if _file_ok("katalog.db") and _file_ok("embeddings.db"):
        print("[HF] Tüm DB dosyaları mevcut (embeddings.db + katalog.db), indirme atlandı.")
        return

    # Legacy çift varsa birleştir
    if not _file_ok("katalog.db") and _try_merge_legacy() and _file_ok("katalog.db"):
        print("[HF] Legacy dizi/film DB'leri katalog.db olarak birleştirildi.")

    missing = [name for name in REQUIRED_LOCAL_NAMES if not _file_ok(name)]
    if not missing:
        print("[HF] Tüm DB dosyaları mevcut, indirme atlandı.")
        return

    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub yüklü değil. pip install huggingface_hub"
        ) from exc

    repo_id = _repo_id()
    token = _token()
    print(f"[HF] Dataset: {repo_id}")
    print(f"[HF] Eksik: {', '.join(missing)}")

    try:
        files = set(list_repo_files(repo_id=repo_id, repo_type="dataset", token=token))
    except Exception as exc:
        raise SystemExit(
            f"[HF] Repo listelenemedi ({repo_id}). "
            f"Private ise HF_TOKEN doğru mu? Hata: {exc}"
        ) from exc

    for local_name in REQUIRED_LOCAL_NAMES:
        if _file_ok(local_name):
            print(f"[HF] OK (var): {local_name}")
            continue

        remote_name = _resolve_remote_name(local_name, files)
        if not remote_name and local_name == "katalog.db":
            # HF'de henüz tek dosya yoksa eski çifti indirip birleştir
            print("[HF] katalog.db yok — legacy çift indirilmeye çalışılacak.")
            for legacy in LEGACY_PAIR:
                if _file_ok(legacy):
                    continue
                rem = _resolve_remote_name(legacy, files)
                if not rem:
                    soft = legacy.replace("ı", "i")
                    rem = next((n for n in files if n.replace("ı", "i").replace("İ", "I") == soft), None)
                if not rem:
                    print(f"[HF] UYARI: {legacy} dataset'te yok.")
                    continue
                print(f"[HF] İndiriliyor: {rem} -> {legacy}")
                cached = hf_hub_download(
                    repo_id=repo_id, filename=rem, repo_type="dataset", token=token
                )
                if os.path.abspath(cached) != os.path.abspath(legacy):
                    shutil.copy2(cached, legacy)
            if _try_merge_legacy() and _file_ok("katalog.db"):
                print("[HF] katalog.db legacy birleştirmeden hazır.")
            continue

        if not remote_name:
            print(f"[HF] UYARI: {local_name} dataset'te bulunamadı. Mevcut: {sorted(files)}")
            continue

        print(f"[HF] İndiriliyor: {remote_name} -> {local_name}")
        cached = hf_hub_download(
            repo_id=repo_id,
            filename=remote_name,
            repo_type="dataset",
            token=token,
        )
        if os.path.abspath(cached) != os.path.abspath(local_name):
            shutil.copy2(cached, local_name)
        size_mb = os.path.getsize(local_name) / (1024 * 1024)
        print(f"[HF] Tamam: {local_name} ({size_mb:.1f} MB)")

    still_missing = [n for n in REQUIRED_LOCAL_NAMES if not _file_ok(n)]
    if "embeddings.db" in still_missing:
        raise SystemExit("[HF] embeddings.db indirilemedi — API başlatılamaz.")
    if still_missing:
        print(f"[HF] UYARI: bazı dosyalar yok, devam: {still_missing}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ensure_assets()
