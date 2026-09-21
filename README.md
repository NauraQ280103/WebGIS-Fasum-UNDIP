# Halo DEEPS — WebGIS Pelaporan Fasilitas UNDIP

Prototype WebGIS berbasis Python/Flask yang mengikuti rancangan UI pada PDF yang diberikan, lalu diperbaiki menjadi layout yang lebih modern dan responsif. Rancangan PDF menampilkan halaman login, peta, riwayat, dan formulir laporan; kategori yang tampak pada rancangan antara lain jalan, penerangan, sanitasi, parkir, dan transportasi. Kategori Gedung ditambahkan sesuai kebutuhan pengembangan yang diminta.

## Fitur
- Login lokal menggunakan NIM/email + password.
- Tombol SSO UNDIP sebagai titik integrasi OpenID Connect.
- Akun operator terpisah dengan kredensial dari `.env`.
- Peta Leaflet dengan marker yang dapat diklik.
- Marker publik hanya berasal dari laporan `approved`.
- Laporan terbaru dapat diklik menuju Riwayat.
- Filter kategori dan pencarian riwayat.
- Kategori: Jalan, Penerangan, Gedung, Parkir, Sanitasi, Transportasi.
- Jenis kerusakan berbeda untuk setiap kategori.
- Lokasi laporan dapat:
  1. dibaca dari EXIF GPS foto; atau
  2. dipilih langsung pada peta dan marker dapat digeser.
- Dashboard operator untuk approve/disapprove.
- Kotak alasan/catatan operator; alasan wajib ketika disapprove.
- Password disimpan sebagai hash, bukan plaintext.
- Total fasilitas/tiling dihapus dari desain dashboard peta.

## Menjalankan
1. Install Python 3.11+.
2. Buat virtual environment:
   `python -m venv .venv`
3. Aktifkan:
   Windows PowerShell: `.venv\Scripts\Activate.ps1`
4. Install:
   `pip install -r requirements.txt`
5. Salin `.env.example` menjadi `.env` dan ubah SECRET_KEY + password operator.
6. Jalankan:
   `python app.py`
7. Buka `http://127.0.0.1:5000`

Demo lokal:
- Mahasiswa: NIM `240001`, password `mahasiswa123`
- Operator: email sesuai `OPERATOR_EMAIL`, password sesuai `OPERATOR_PASSWORD`

## Catatan SSO
Kode ini sengaja tidak mengarang endpoint SSO UNDIP. Untuk produksi, minta URL issuer/metadata OpenID Connect, client ID, client secret, redirect URI, dan aturan domain/atribut dari pengelola SSO UNDIP. Setelah itu endpoint `/auth/sso` dapat diganti dengan Authlib OIDC Authorization Code Flow.

## Produksi
Untuk deployment kampus, gunakan PostgreSQL + PostGIS, HTTPS, object storage untuk foto, CSRF protection, rate limiting, audit log operator, validasi file yang lebih ketat, dan SSO resmi kampus.
