# -*- coding: utf-8 -*-
"""
Render / yerel API başlatıcı.
1) HF'den DB indir
2) Gunicorn (production) veya Flask dev server (lokal)
"""
from __future__ import annotations

import os
import sys


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("[boot] HF asset kontrolü...")
    import download_hf_assets

    download_hf_assets.ensure_assets()

    port = os.environ.get("PORT", "4000")
    # Render ve benzeri ortamlar RENDER=true veya PORT set eder
    use_gunicorn = os.environ.get("USE_GUNICORN", "1").strip() not in ("0", "false", "False")
    on_render = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL"))

    if use_gunicorn and (on_render or os.environ.get("FORCE_GUNICORN") == "1"):
        print(f"[boot] Gunicorn başlıyor — port {port}")
        # embeddings indirme sonrası worker'lar import eder
        os.execvp(
            sys.executable,
            [
                sys.executable,
                "-m",
                "gunicorn",
                "server_api:app",
                "--bind",
                f"0.0.0.0:{port}",
                "--workers",
                "1",
                "--threads",
                "4",
                "--timeout",
                "180",
                "--access-logfile",
                "-",
                "--error-logfile",
                "-",
            ],
        )

    print(f"[boot] Flask dev server — port {port}")
    from server_api import app

    app.run(host="0.0.0.0", port=int(port), debug=False, threaded=True)


if __name__ == "__main__":
    main()
