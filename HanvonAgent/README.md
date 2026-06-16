# HanvonAgent — Hanvon F710 Yönetim Uygulaması

Hanvon F710 parmak izi/yüz tanıma cihazlarından TCP/IP üzerinden personel giriş-çıkış verilerini çeken, yerel olarak depolayan ve harici API'ye iten Windows masaüstü + servis uygulaması.

## 🚀 Hızlı Başlangıç

### 1. GUI Uygulamasını Başlat

```bash
start.bat
```

**Otomatik olarak:**
- Python 3.10+ kontrol eder
- Virtual environment oluşturur
- Bağımlılıkları kurar (`pip install -r requirements.txt`)
- GUI açılır (4 sekmeli)

### 2. Windows Servisi Kur (Opsiyonel)

```batch
INSTALL_SERVICE.bat
```

**Gerekli:** NSSM (Non-Sucking Service Manager)
- İndir: https://nssm.cc/download
- PATH'e ekle veya venv/Scripts'e koy

**Kurulum sonrası:**
```batch
nssm start HanvonAgent      # Servisi başlat
nssm stop HanvonAgent       # Servisi durdur
nssm status HanvonAgent     # Durumu göster
nssm remove HanvonAgent     # Kaldır (confirm gerekir)
```

---

## 📋 Özellikler

### GUI Mode (Desktop)
- **4 Tab:** Panolar, Ayarlar, Kayıtlar, Cihaz Yönetimi
- **Cihaz Yönetimi:** Ekle, test, bağlan
- **Kayıt Çekme:** Cihazdan manuel veri çek
- **API Push:** Verileri harici API'ye gönder
- **System Tray:** Arka planda çalışma
- **Real-time Dashboard:** İstatistikler, sağlık durumu

### Service Mode (Background)
- **Otomatik Polling:** Belirli aralıkla cihazlardan kayıt çek
- **Otomatik Push:** Belirli aralıkla verileri API'ye gönder
- **BridgeApi:** GET endpoint'leri (dış sistem entegrasyonu)
- **Logging:** Detaylı log dosyaları (logs/hanvon_service.log)
- **No GUI:** Arka planda sessizce çalışır

---

## 🎯 Kullanım Senaryoları

### Senaryo 1: Cihazdan Manuel Veri Çek
1. `start.bat` çalıştır
2. **Ayarlar** tab'ında cihaz ekle (IP + CommKey)
3. "Cihaz Ekle" → "Bağlantıyı Test Et"
4. **Panolar** tab'ında "Şimdi Çek" butonu
5. Veriler `data/YYYY/MM/DD.json` altında kaydedilir

### Senaryo 2: Otomatik Arka Plan Çalışması
1. `INSTALL_SERVICE.bat` çalıştır (Admin)
2. Ayarlar'dan poll_enabled ve push_enabled aç
3. `nssm start HanvonAgent`
4. Servis otomatik olarak belirli aralıkla:
   - Cihazlardan kayıt çeker
   - Yerel DB'ye kaydeder
   - API'ye gönderir (eğer endpoint varsa)

### Senaryo 3: Dış Sistem Entegrasyonu
1. Servis başlatıldığında BridgeApi (port 8765) açılır
2. Dış sistemler GET istekleri gönderebilir:

```bash
# Günlük kayıtları al
curl http://localhost:8765/api/records?date=2026-06-09

# Cihaz listesi
curl http://localhost:8765/api/devices

# Personel listesi
curl http://localhost:8765/api/employees

# Uygulama durumu
curl http://localhost:8765/api/status
```

---

## 📁 Proje Yapısı

```
HanvonAgent/
├── core/              # TCP client + XOR crypto
├── models/            # SQLAlchemy ORM (Device, Employee, Record, Setting)
├── services/          # RecordService, PushService, SchedulerService
├── bridge_api/        # FastAPI HTTP sunucu
├── ui/                # PySide6 GUI (4 sekmeli)
├── tests/             # 65 unit test
├── main.py            # GUI entry point
├── service_runner.py  # Windows Service entry point
├── start.bat          # GUI launcher
├── INSTALL_SERVICE.bat # Service installer
├── requirements.txt   # Python dependencies
├── hanvon_agent.db    # SQLite database (otomatik oluşur)
└── data/              # Yerel kayıt dosyaları (YYYY/MM/DD.json)
```

---

## ⚙️ Ayarlar (Settings)

Database'de key-value şeklinde kaydedilir:

| Key | Değer | Varsayılan |
|-----|-------|-----------|
| `poll_enabled` | true/false | false |
| `poll_interval` | saniye | 1800 (30 dk) |
| `push_enabled` | true/false | false |
| `push_interval` | saniye | 3600 (1 saat) |
| `api_endpoint` | URL | — |
| `api_token` | Bearer token | — |

**GUI'den değiştir:** Ayarlar → Poll/Push sections → Kaydet

---

## 🔌 API Endpoints (BridgeApi)

**Host:** http://localhost:8765

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/api/status` | Uygulama durumu, istatistikler |
| `GET` | `/api/devices` | Cihaz listesi |
| `GET` | `/api/records` | Tüm kayıtlar (filter: date, device_ip, push_status) |
| `GET` | `/api/records/{date}` | Belirli tarih (YYYY-MM-DD) |
| `GET` | `/api/employees` | Personel listesi |

---

## 📊 Database Schema

```sql
devices      -- Hanvon cihazları
├── id, name, ip, comm_key_encrypted, enabled, last_connected, created_at

employees    -- Personel kayıtları
├── id, employee_device_id, name, card_num, check_type, device_id, last_synced

records      -- Giriş-çıkış kayıtları
├── id, device_id, employee_id, record_time, status, card_src, 
│   source (device|manual), push_status (pending|sent|failed), pushed_at

settings     -- Ayarlar (key-value)
├── key (PK), value, updated_at
```

---

## 🧪 Testler

```bash
pytest tests/              # Tüm testler
pytest tests/test_crypto.py   # Crypto testleri
pytest tests/test_models.py   # Model testleri
pytest -v                     # Verbose
```

**65/65 testler pass ✅**

---

## 🔧 Troubleshooting

### "Python bulunamadı"
- Python 3.10+ kur: https://www.python.org/downloads/
- PATH'e ekle

### "PySide6 kurulumunda hata"
- requirements.txt güncellenmiş, venv temizle:
  ```batch
  rmdir /s /q venv
  start.bat  # Yeniden çalıştır
  ```

### "Service kurulumunda hata"
- NSSM indir: https://nssm.cc/download
- Çıkan nssm.exe'yi venv/Scripts/ veya PATH'e koy
- INSTALL_SERVICE.bat'i Admin olarak çalıştır

### "Cihaza bağlanamıyor"
- IP adresi doğru mu? (172.16.1.218 vb.)
- CommKey (şifre) doğru mu?
- Ağda bağlantı var mı?
- Firewall 9922 portunu engellemiyor mu?

### "Log dosyaları nerede?"
- GUI: Konsol çıkışı
- Service: `logs/hanvon_service.log`

---

## 📝 Lisans & Bilgiler

**Proje:** HanvonAgent (Hanvon F710 Manager)  
**Durum:** Production Ready (Beta)  
**Geliştirici:** Claude Code (AI)  
**Tarih:** 2026-06-09

---

## 📞 İletişim

Sorularınız veya geri bildirimleri için GitHub Issues kullanın.
