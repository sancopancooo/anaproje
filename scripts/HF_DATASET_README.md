---
license: other
task_categories:
  - other
tags:
  - movies
  - tv-series
  - sqlite
  - embeddings
pretty_name: DizimiBul Catalog + Embeddings
---

# DizimiBul — Katalog ve Embedding Dataset

Render / API boot sırasında `download_hf_assets.py` bu dataset'ten dosyaları indirir.

## Güncel dosyalar (önerilen)

| Dosya | Açıklama |
|---|---|
| `katalog.db` | **Tek SQLite katalog** — `diziler` + `filmler` tabloları |
| `embeddings.db` | Öneri motoru vektörleri (`item_embeddings`) |

## Eski dosyalar (legacy)

`diziler_veritabani.db` / `diziler_veritabanı.db` artık kullanılmıyor.
Yeni deploy'lar `katalog.db` bekler. Eski çift hâlâ varsa indirme scripti birleştirerek `katalog.db` üretebilir.

## Tablolar (`katalog.db`)

- `diziler` — dizi meta + fragman URL'leri
- `filmler` — film meta + fragman URL'leri

Kullanıcı hesapları / kitaplık / arkadaşlık bu dataset'te **yoktur** (`kullanicilar1.db`, ayrı).
