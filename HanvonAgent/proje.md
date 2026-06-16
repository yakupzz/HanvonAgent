# HanvonAgent — Proje Tasarım Belgesi

## 1. Proje Nedir?

Hanvon F710 parmak izi/yüz tanıma cihazlarından TCP/IP üzerinden personel giriş-çıkış verilerini otomatik çeken, yerel dosya sistemine kaydeden ve harici bir API'ye ileten Windows masaüstü + servis uygulaması.

**Konum:** `HanvonAgent\`

---

## 2. Tech Stack

**Karar: PySide6 + Python (CLAUDE.md Desktop Stack)**

| Layer | Seçim |
|-------|-------|
| UI | PySide6 (Qt 6.x) |
| Language | Python 3.10+ |
| DB | SQLAlchemy ORM + SQLite |
| HTTP Server | FastAPI (BridgeApi) |
| Scheduling | APScheduler |
| Cryptography | XOR (Ruby SDK port) |
| Service | NSSM wrapper |
| Deployment | PyInstaller → single .exe |

---

## 3. Proje Klasör Yapısı

```
HanvonAgent\
│
├── main.py                        ← Masaüstü uygulama başlatıcı (PySide6 UI)
├── service_runner.py              ← Windows Servis başlatıcı (UI yok, arka plan)
├── requirements.txt               ← Python bağımlılıkları
├── hanvon_agent.db                ← SQLite veritabanı (otomatik oluşur)
│
├── core/                          ← Hanvon cihaz iletişim katmanı
│   ├── hanvon_client.py           ← TCP bağlantı + komut gönderme/alma
│   ├── hanvon_crypto.py           ← CommKey XOR şifreleme (Ruby SDK port)
│   └── record_parser.py           ← GetRecord / GetEmployee yanıt parse
│
├── models/                        ← Veritabanı modelleri (SQLAlchemy ORM)
│   ├── base.py                    ← SQLAlchemy Base + engine setup
│   ├── device.py                  ← devices tablosu
│   ├── employee.py                ← employees tablosu
│   ├── record.py                  ← records tablosu (push durumu dahil)
│   └── setting.py                 ← settings tablosu (key-value)
│
├── services/                      ← İş mantığı katmanı (UI'dan bağımsız)
│   ├── device_service.py          ← Cihaz bağlantı, test, GetDeviceInfo, SetDeviceInfo
│   ├── record_service.py          ← Kayıt çekme, dosyaya yazma, duplicate kontrol
│   ├── employee_service.py        ← Personel çekme, DB'ye kayıt, cihaz klonlama
│   ├── push_service.py            ← Harici API'ye POST gönderme + retry
│   └── scheduler_service.py       ← APScheduler - otomatik çekme + push zamanlaması
│
├── bridge_api/                    ← Gömülü HTTP sunucu (FastAPI)
│   ├── server.py                  ← FastAPI app başlatma (ayrı thread)
│   └── routes/
│       ├── records.py             ← GET /api/records, GET /api/records/{date}
│       ├── devices.py             ← GET /api/devices
│       └── employees.py           ← GET /api/employees
│
├── ui/                            ← PySide6 arayüz (main.py'den başlatılır)
│   ├── main_window.py             ← Ana pencere + tab bar + sistem tray
│   ├── tabs/
│   │   ├── dashboard_tab.py       ← Genel durum, son çekme, cihaz sağlığı
│   │   ├── settings_tab.py        ← Cihaz ekle/düzenle + API ayarları + zamanlama
│   │   ├── records_tab.py         ← Kayıt tablosu, tarih filtresi, push durumu
│   │   └── device_mgmt_tab.py     ← Cihaz bilgisi, saat ayarla, personel yönetimi
│   └── dialogs/
│       ├── add_device_dialog.py   ← Yeni cihaz ekleme formu
│       └── employee_edit_dialog.py← Personel isim düzenleme
│
├── data/                          ← Yerel kayıt dosyaları (otomatik oluşur)
│   └── YYYY/
│       └── MM/
│           └── DD.json            ← Tüm cihazların o günkü verileri
│
└── tests/                         ← pytest test dosyaları
    ├── test_crypto.py             ← XOR şifreleme (Ruby spec'ten test vektörleri)
    ├── test_record_parser.py      ← GetRecord parse testi
    ├── test_device_service.py     ← Bağlantı + komut testleri
    ├── test_push_service.py       ← API push + retry testleri
    └── test_bridge_api.py         ← FastAPI endpoint testleri
```

---

## 4. Özellikler (Feature Set)

### 4.1 Ayarlar Menüsü
- **Cihaz Ekle/Düzenle/Sil**: IP adresi + CommKey (şifre)
  - Port hardcode: `9922` (gizli, kullanıcı görmez)
  - Ekledikten sonra "Bağlantıyı Test Et" butonu → `GetDeviceInfo()` ile doğrulama
- **API Ayarları**: Endpoint URL + Auth token/header
- **Otomatik Çekme**: Aktif/pasif, zaman aralığı (ör. her 30 dk)
- **Otomatik Push**: Aktif/pasif, çekme sonrası otomatik push seçeneği

### 4.2 Ana İşlev — Kayıt Çekme
- `GetRecord(start_time="2026-6-9 0:0:0" end_time="2026-6-9 23:59:59")` komutu
- Varsayılan: Bugünün tarihi
- Parse: `time=`, `id=`, `name=`, `status=`, `card_src=` alanları
- Kayıt formatı (JSON):
  ```json
  {
    "device_ip": "172.16.1.218",
    "pulled_at": "2026-06-09T14:30:00",
    "records": [
      {"time": "2026-06-09 08:30:00", "id": "8", "name": "YAKUP T.", "status": "1", "card_src": "from_door"}
    ]
  }
  ```

### 4.3 Ana İşlev — Yerel Kayıt
- Çekilen veriler `data/YYYY/MM/DD.json` formatında kaydedilir (tüm cihazlar tek dosyada, `device_ip` alanı ile ayrışır)
- Dosya mevcutsa güncelle — duplicate control: `time` + `id` + `device_ip` kombinasyonu unique
- **Bu dosyalar arşiv/yedek amaçlı** — push durumu DB'de tutulur, dosyaya yazılmaz
- **Manuel JSON Import**: "Dosya Yükle" ile dış JSON → DB'ye `source: "manual"` etiketiyle kaydedilir

### 4.4 Ana İşlev — API Push (Giden)
- DB'deki `push_status = "pending"` kayıtlar harici endpoint'e `HTTP POST`
- Push kaynağı fark etmez: cihazdan gelen veya manuel import edilmiş
- Manuel: "Şimdi Gönder" butonu
- Otomatik: Ayarlar'dan schedule
- **Push durumu takibi: SQLite `records` tablosunda** → `push_status` (pending/sent/failed) + `pushed_at`
- Başarısız push'lar → retry queue (exponential backoff)

### 4.5 BridgeApi — Gömülü HTTP Sunucu (Gelen)
- Uygulama içinde çalışan küçük FastAPI sunucusu (ayrı thread)
- Dış sistemler buradan GET ile veri çekebilir
- Port ayarlanabilir (varsayılan: `8765`)
- Endpoint'ler:
  ```
  GET /api/records              → Tüm kayıtlar (filtre: ?date=2026-06-09&device_ip=...)
  GET /api/records/{date}       → Belirli günün kayıtları
  GET /api/devices              → Kayıtlı cihazlar + son bağlantı
  GET /api/employees            → Yerel DB'deki personeller
  GET /api/status               → Uygulama sağlık durumu
  ```

### 4.6 Cihaz Yönetim Menüsü
- **Cihaz Bilgisi**: `GetDeviceInfo()` → Model, edition, IP, MAC, saat
- **Saat Ayarla**: `SetDeviceInfo(time="..." week="N")` → PC saatini cihaza yaz
- **Personel Listesi**:
  - `GetEmployeeID()` → tüm ID'ler
  - `GetEmployee(id="X")` → her biri için detay (batch, progress bar ile)
  - SQLite'a kaydet
- **Personel İsim Güncelleme**:
  - Tabloda isim düzenlenebilir
  - "Cihaza Yaz" → `SetNameTable(id="isim" ...)` komutu
- **Cihaz Klonlama** (çoklu cihaz):
  - Kaynak cihazdan tüm personel çek
  - Hedef cihaza `SetEmployee()` ile yaz

---

## 5. Veritabanı Şeması

```sql
devices      (id, name, ip, comm_key_encrypted, enabled, last_connected, created_at)
employees    (id, employee_device_id, name, card_num, check_type, authority, device_id, last_synced)
records      (id, device_id, employee_id, record_time, status, card_src, file_path, source, push_status, pushed_at, created_at)
settings     (key TEXT PK, value TEXT)
sync_log     (id, device_id, operation, status, message, created_at)
```

---

## 6. Windows Çalışma Mimarisi

### System Tray App
- Uygulama başladığında doğrudan System Tray'e gider (pencere açılmaz)
- Tray ikonu sağ tık menüsü:
  - **Aç** → Ana pencere göster
  - **Şimdi Çek** → Manuel kayıt çekme
  - **Durum** → Son çekme zamanı, cihaz durumu tooltip
  - **Çıkış** → Uygulamayı kapat
- Windows başlangıcında otomatik başlatma seçeneği (Startup registry)

### Arka Plan Süreçleri (her zaman aktif)
- APScheduler: otomatik kayıt çekme
- BridgeApi: HTTP sunucu (FastAPI, ayrı thread)
- Push Service: retry queue

### Windows Servis Modu
- NSSM ile `service_runner.py`'yi Windows Servisi olarak register et
- **Kullanıcı oturumu olmadan çalışır** — sunucu makineye kurmak için ideal
- Servis başlayınca: kayıt çekme, BridgeApi, push — tümü arka planda aktif
- UI'dan "Servisi Kur" butonu → NSSM `install` komutu (Admin gerekir)
- UI'dan "Servisi Kaldır" butonu → NSSM `remove` komutu

### EXE Paketi
- `PyInstaller --onefile --windowed` → tek `.exe`
- Python runtime dahil, hedef makinede Python kurulu olmak zorunda değil
- Tahmini boyut: ~80-100 MB (Python runtime dahil)

---

## 7. Protokol Notları (Referans: Ruby SDK)

| Konu | Detay |
|------|-------|
| Port | 9922 (sabit) |
| Protokol | Plain-text TCP, CRLF terminatör |
| Şifreleme | XOR stream cipher, CommKey 1-8 rakam |
| Wait() yanıtı | Geçiş yanıtı, gerçek cevabı bekle (120 sn) |
| GetRecord | `start_time` ve `end_time` her zaman gönderilmeli |
| SetNameTable | Birden fazla isim aynı komutla |

---

## 8. Kullanılacak Referanslar

- `referans/lib/hanvon/client.rb` — TCP protokol
- `referans/lib/hanvon/crypto.rb` — CommKey XOR algoritması
- `referans/spec/hanvon_crypto_spec.rb` — Test vektörleri
