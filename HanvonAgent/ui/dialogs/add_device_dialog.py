"""
Cihaz ekleme / düzenleme dialogu.
"""

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QLabel, QVBoxLayout,
    QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt
from models import Device, Setting, get_session
from core.hanvon_client import HanvonClient


class AddDeviceDialog(QDialog):
    """Cihaz ekle veya düzenle dialogu.

    device=None  → Ekle modu (yeni Device oluşturur)
    device=<obj> → Düzenle modu (mevcut Device günceller)
    """

    def __init__(self, parent=None, device: Device = None):
        super().__init__(parent)
        self._edit_device = device
        self._is_edit = device is not None

        self.setWindowTitle("Cihaz Düzenle" if self._is_edit else "Cihaz Ekle")
        self.setGeometry(200, 200, 420, 320)
        self.device = None
        self._init_ui()

        if self._is_edit:
            self._prefill()

    def _init_ui(self):
        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ör: Lab Cihazı")
        layout.addRow("Cihaz Adı:", self.name_input)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Ör: 172.16.1.218")
        layout.addRow("IP Adresi:", self.ip_input)

        self.comm_key_input = QLineEdit()
        self.comm_key_input.setPlaceholderText("Ör: 12345678 (1-8 rakam)")
        self.comm_key_input.setEchoMode(QLineEdit.Password)
        layout.addRow("CommKey (Şifre):", self.comm_key_input)

        info_label = QLabel("Port otomatik olarak 9922 kullanılır")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addRow("", info_label)

        self.delete_after_pull_cb = QCheckBox(
            "Cihazdan verileri sil\n"
            "(G/C verisi çekilen personelin verisini cihazdan temizle)"
        )
        self.delete_after_pull_cb.setChecked(False)
        self.delete_after_pull_cb.setToolTip(
            "İşaretlenirse: otomatik çekme tamamlandıktan sonra cihazdaki TÜM G/C kayıtları silinir.\n"
            "Not: F710 sadece DeleteAllRecord() destekler — belirli personel kaydı silinemez."
        )
        layout.addRow("", self.delete_after_pull_cb)

        button_layout = QVBoxLayout()

        test_btn = QPushButton("Bağlantıyı Test Et")
        test_btn.clicked.connect(self._test_connection)
        button_layout.addWidget(test_btn)

        save_label = "Güncelle" if self._is_edit else "Ekle"
        save_btn = QPushButton(save_label)
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("İptal")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addRow(button_layout)

    def _prefill(self):
        """Düzenle modunda mevcut cihaz bilgilerini doldur."""
        d = self._edit_device
        self.name_input.setText(d.name or "")
        self.ip_input.setText(d.ip or "")
        # CommKey şifreli saklandığı için göstermiyoruz; boş bırakılırsa değişmez
        self.comm_key_input.setPlaceholderText("Değiştirmek istemiyorsanız boş bırakın")

        # delete_after_pull ayarını DB'den oku
        session = get_session()
        try:
            setting = session.query(Setting).filter_by(
                key=f"delete_after_pull_{d.id}"
            ).first()
            self.delete_after_pull_cb.setChecked(setting is not None and setting.value == "1")
        finally:
            session.close()

    def _test_connection(self):
        ip = self.ip_input.text().strip()
        comm_key = self.comm_key_input.text().strip()

        if not ip:
            QMessageBox.warning(self, "Hata", "IP adresi giriniz")
            return

        try:
            client = HanvonClient(ip, comm_key=comm_key if comm_key else None)
            client.connect()
            device_info = client.get_device_info()
            client.disconnect()

            if device_info:
                dev_id = device_info.get('dev_id', 'N/A')
                edition = device_info.get('edition', 'N/A')
                QMessageBox.information(
                    self, "Başarı",
                    f"✓ Cihaza bağlanıldı!\n\nDev ID: {dev_id}\nEdition: {edition}"
                )
            else:
                QMessageBox.warning(self, "Hata", "Cihazdan yanıt yok")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Bağlantı başarısız:\n{str(e)}")

    def accept(self):
        name = self.name_input.text().strip()
        ip = self.ip_input.text().strip()
        comm_key = self.comm_key_input.text().strip()
        delete_val = "1" if self.delete_after_pull_cb.isChecked() else "0"

        if not name or not ip:
            QMessageBox.warning(self, "Hata", "Cihaz adı ve IP adresi gereklidir")
            return

        session = get_session()
        try:
            if self._is_edit:
                # Düzenle modu — mevcut device'ı güncelle
                d = session.merge(self._edit_device)
                d.name = name
                d.ip = ip
                if comm_key:
                    d.set_comm_key(comm_key)

                # delete_after_pull ayarını kaydet
                session.query(Setting).filter_by(
                    key=f"delete_after_pull_{d.id}"
                ).delete()
                session.add(Setting(key=f"delete_after_pull_{d.id}", value=delete_val))
                session.commit()

                self.device = d
            else:
                # Ekle modu — yeni Device
                new_device = Device(name=name, ip=ip, enabled=True)
                new_device.set_comm_key(comm_key)
                session.add(new_device)
                session.flush()  # ID al

                # delete_after_pull ayarını kaydet
                session.query(Setting).filter_by(
                    key=f"delete_after_pull_{new_device.id}"
                ).delete()
                session.add(Setting(key=f"delete_after_pull_{new_device.id}", value=delete_val))
                session.commit()

                self.device = new_device
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Hata", f"Kaydetme başarısız:\n{str(e)}")
            return
        finally:
            session.close()

        super().accept()

    def get_device(self):
        return self.device
