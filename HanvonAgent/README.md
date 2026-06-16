# HanvonAgent

Hanvon F710 parmak izi / yüz tanıma cihazlarından TCP/IP üzerinden personel giriş-çıkış verilerini çeken, yerel olarak depolayan ve harici API'ye ileten Windows masaüstü uygulaması.

**Geliştirici | Yakup T. | Versiyon:** 0.3.1 | **Platform:** Windows 10/11 | **Python:** 3.10+ 

---

## Gereksinimler

- Python 3.10+
- NSSM (servis modu için): https://nssm.cc/download

---

## Kurulum ve Başlatma

### GUI Modu

```batch
start.bat
```

İlk çalıştırmada venv oluşturur ve bağımlılıkları kurar, ardından GUI açılır.

### Windows Servisi (Opsiyonel)

GUI'de **Servis** menüsünden "Servisi Kur" seçin (Admin gerektirir).  
NSSM'in `nssm.exe` dosyası proje klasöründe veya PATH'te olmalıdır.

```batch
nssm start HanvonAgent    # başlat
nssm stop HanvonAgent     # durdur
nssm status HanvonAgent   # durum
nssm remove HanvonAgent   # kaldır
```

### EXE Paketi (Dağıtım)

```batch
build.bat
```

`dist/HanvonAgent.exe` oluşturur. Hedef makinede Python kurulu olmak zorunda değildir.

---

## Özellikler

### Dashboard

- Kayıtlı cihazları listeler, her biri için otomatik çekme zamanlaması ayarlanabilir
- Manuel "Verileri Çek" — seçili cihazlardan anlık kayıt çeker
- "G/C verisi çekilen personelin verisini cihazdan temizle" seçeneği: işaretlenirse çekme sonrası `DeleteAllRecord()` gönderir
- API'ye "Yeniden Gönder" butonu: başarısız kayıtları tekrar iletir

### Cihaz Yönetimi

- Cihaz bilgisi görüntüleme (`GetDeviceInfo`)
- PC saatini cihaza yazma (`SetDeviceInfo`)
- Personel listesi çekme ve yerel DB'ye kaydetme
- Cihazlar arası personel transferi (kaynak → hedef)

### Kayıtlar

- Tarih ve cihaz filtresiyle kayıt görüntüleme
- Push durumu takibi (pending / sent / failed)

### Ayarlar

- Cihaz ekle / düzenle / sil
- API endpoint ve Bearer token ayarı
- Otomatik çekme ve push zamanlaması (cihaz bazlı)

---

## Proje Yapısı

```
HanvonAgent/
├── main.py                  # GUI başlatıcı
├── service_runner.py        # Servis başlatıcı (UI yok)
├── __version__.py           # Versiyon
├── requirements.txt
├── start.bat                # GUI launcher
├── build.bat                # PyInstaller build
├── HanvonAgent.spec         # PyInstaller konfigürasyonu
├── nssm.exe                 # Servis yöneticisi
│
├── core/
│   ├── hanvon_client.py     # TCP bağlantı + komut gönderme
│   ├── hanvon_crypto.py     # CommKey XOR şifreleme
│   ├── record_parser.py     # Yanıt parse
│   ├── secret_store.py      # DPAPI ile CommKey şifreleme
│   └── app_paths.py         # Exe/dev ortam path çözümleme
│
├── models/
│   ├── device.py            # devices tablosu
│   ├── employee.py          # employees tablosu
│   ├── record.py            # records tablosu
│   └── setting.py           # settings tablosu (key-value)
│
├── services/
│   ├── record_service.py        # Kayıt çekme ve DB'ye yazma
│   ├── push_service.py          # API push + retry
│   ├── scheduler_service.py     # APScheduler otomatik çekme/push
│   ├── employee_sync_service.py # Personel senkronizasyonu
│   ├── device_transfer_service.py # Cihazlar arası transfer
│   ├── device_push_worker.py    # Transfer iş parçacığı
│   └── service_manager.py       # NSSM servis yönetimi
│
├── bridge_api/
│   ├── server.py            # FastAPI sunucu (ayrı thread)
│   └── routes/records.py    # GET /api/records endpoint'leri
│
├── ui/
│   ├── main_window.py       # Ana pencere + sistem tray
│   ├── tabs/
│   │   ├── dashboard_tab.py     # Cihaz listesi + veri çekme
│   │   ├── device_mgmt_tab.py   # Cihaz bilgisi + personel yönetimi
│   │   ├── records_tab.py       # Kayıt görüntüleme + push durumu
│   │   └── settings_tab.py      # Cihaz, API, zamanlama ayarları
│   └── dialogs/
│       ├── add_device_dialog.py
│       └── device_transfer_dialog.py
│
└── tests/                   # 202 unit test
```

---

## Veritabanı

SQLite (`data/hanvon_agent.db`), SQLAlchemy ORM:

| Tablo | İçerik |
|-------|--------|
| `devices` | IP, CommKey (DPAPI şifreli), etkin durum |
| `employees` | Personel bilgisi, kart numarası, cihaz ilişkisi |
| `records` | Giriş-çıkış kaydı, push durumu (pending/sent/failed) |
| `settings` | key-value ayarlar (API token, zamanlama vb.) |

---

## BridgeApi

Yalnızca **servis modunda** (`service_runner.py`) port `8765`'te FastAPI sunucu açılır. GUI modunda çalışmaz.

```
GET /api/records              # Tüm kayıtlar (?date=YYYY-MM-DD filtresi)
GET /api/records/{date}       # Belirli gün
GET /api/devices              # Cihaz listesi
GET /api/employees            # Personel listesi
GET /api/status               # Uygulama sağlık durumu
```

---

## Testler

```bash
pytest tests/
pytest tests/ -v
```

202 test pass.

---

## Protokol Notları

| Konu | Detay |
|------|-------|
| Port | 9922 (sabit) |
| Protokol | Plain-text TCP, CRLF |
| Şifreleme | XOR stream cipher (CommKey 1–8 rakam) |
| DeleteAllRecord | F710'da parametresiz — tüm G/C kayıtları silinir |
| GetRecord | `start_time` ve `end_time` zorunlu (format: `YYYY-M-D H:M:S`) |
