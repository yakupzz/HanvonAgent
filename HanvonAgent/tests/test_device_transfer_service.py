"""
DeviceTransferService testleri — cihazdan cihaza personel aktarımı.

2026-09-30 incelemesi (BUG-017/018/019): ID eşleşmesi kişi eşleşmesi değil;
hedef okunamazsa körlemesine üzerine yazılıyordu; boş kaynak isim hedefi
siliyordu; hata sonrası aynı soket kullanılıyordu.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models import Device, Employee
from services import device_transfer_service as svc
from services.device_transfer_service import (
    TRANSFER_FAILED, TRANSFER_OK, TRANSFER_SKIPPED, TransferItem,
    is_different_person, transfer_employee,
)

FACES_A = [f"faceA{i}" for i in range(18)]
FACES_B = [f"faceB{i}" for i in range(18)]


@pytest.fixture(autouse=True)
def _no_audit_file():
    """Testler gerçek transfer_audit.log'a yazmasın."""
    with patch.object(svc, "_audit"):
        yield


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'transfer.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def session(session_factory):
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def devices(session):
    src = Device(name="YONETIM", ip="172.16.1.219", enabled=True)
    dst = Device(name="ANA GIRIS", ip="172.16.1.218", enabled=True)
    session.add_all([src, dst])
    session.commit()
    return src, dst


def _emp(name, faces=FACES_A, **extra):
    data = {"result": "success", "name": name, "card_num": "0X1", "check_type": "face",
            "authority": "0X0", "calid": "", "opendoor_type": "face", "face_data": list(faces)}
    data.update(extra)
    return data


def _clients(source_data, target_data, verify_data=None):
    """source.get_employee → source_data; target: 1. çağrı target_data, sonrakiler verify_data."""
    source, target = MagicMock(ip="172.16.1.219"), MagicMock(ip="172.16.1.218")
    source.get_employee.return_value = source_data
    calls = {"n": 0}

    def target_get(_id):
        calls["n"] += 1
        if calls["n"] == 1:
            if isinstance(target_data, Exception):
                raise target_data
            return target_data
        return verify_data
    target.get_employee.side_effect = target_get
    target.set_name_table.return_value = True
    target.set_employee.return_value = True
    return source, target


def _run(session, devices, source, target, **kw):
    src, dst = devices
    return transfer_employee(source, target, "68", src.id, dst.id, session, **kw)


class TestIsDifferentPerson:
    def test_same_faces_different_names_is_same_person(self):
        assert is_different_person("YELDA EKINCI", FACES_A, "BENSU YANAR", FACES_A) is False

    def test_different_faces_same_name_is_same_person(self):
        assert is_different_person("AYSE KAYA", FACES_A, "AYŞE  kaya", FACES_B) is False

    def test_different_faces_different_names_is_other_person(self):
        assert is_different_person("FATEMEH AHMADI", FACES_A, "AYTEKIN URKMEZ", FACES_B) is True

    def test_without_faces_names_decide(self):
        assert is_different_person("A B", [], "C D", []) is True
        assert is_different_person("A B", [], "", []) is False


class TestTransferSafety:
    def test_other_person_on_target_is_skipped(self, session, devices):
        source, target = _clients(_emp("FATEMEH AHMADI", FACES_A), _emp("AYTEKIN URKMEZ", FACES_B))
        status, msg = _run(session, devices, source, target)
        assert status == TRANSFER_SKIPPED
        assert "AYTEKIN URKMEZ" in msg
        target.set_employee.assert_not_called()
        target.set_name_table.assert_not_called()
        assert session.query(Employee).count() == 0

    def test_other_person_overwritten_only_with_explicit_permission(self, session, devices):
        source, target = _clients(_emp("FATEMEH AHMADI", FACES_A), _emp("AYTEKIN URKMEZ", FACES_B))
        status, _ = _run(session, devices, source, target, allow_overwrite_other_person=True)
        assert status == TRANSFER_OK
        target.set_employee.assert_called_once()
        assert target.set_employee.call_args.kwargs["face_data"] == FACES_A

    def test_target_read_error_is_not_treated_as_new(self, session, devices):
        source, target = _clients(_emp("YELDA"), TimeoutError("timed out"))
        status, msg = _run(session, devices, source, target)
        assert status == TRANSFER_FAILED
        assert "okunamadı" in msg
        target.set_employee.assert_not_called()
        target.set_name_table.assert_not_called()
        target.disconnect.assert_called()  # akış kaymış olabilir → yeniden bağlan
        target.connect.assert_called()

    def test_empty_source_name_never_blanks_target(self, session, devices):
        source, target = _clients(_emp("", FACES_A), _emp("HASAN ALI SAHAN", FACES_A))
        status, _ = _run(session, devices, source, target)
        assert status == TRANSFER_OK
        target.set_name_table.assert_not_called()
        target.set_employee.assert_not_called()
        emp = session.query(Employee).one()
        assert emp.name == "HASAN ALI SAHAN"

    def test_source_read_error_reconnects_and_uses_local_backup(self, session, devices):
        src, _ = devices
        backup = Employee(employee_device_id=68, name="YEDEK ISIM", device_id=src.id)
        backup.face_data = FACES_A
        session.add(backup)
        session.commit()
        source, target = _clients(None, None, verify_data=_emp("YEDEK ISIM"))
        source.get_employee.side_effect = TimeoutError("timed out")
        status, _ = _run(session, devices, source, target)
        assert status == TRANSFER_OK
        source.disconnect.assert_called()
        source.connect.assert_called()
        assert target.set_employee.call_args.kwargs["name"] == "YEDEK ISIM"


class TestTransferMinimalCommands:
    def test_turkish_vs_ascii_name_is_not_a_change(self, session, devices):
        source, target = _clients(_emp("ESMANUR ÖNEM"), _emp("ESMANUR ONEM"))
        status, msg = _run(session, devices, source, target)
        assert status == TRANSFER_OK
        target.set_name_table.assert_not_called()
        target.set_employee.assert_not_called()

    def test_same_faces_name_differs_sends_only_name(self, session, devices):
        source, target = _clients(_emp("YELDA EKINCI", FACES_A), _emp("BENSU YANAR", FACES_A),
                                  verify_data=_emp("YELDA EKINCI"))
        status, _ = _run(session, devices, source, target, update_biometric=True)
        assert status == TRANSFER_OK
        target.set_name_table.assert_called_once_with({"68": "YELDA EKINCI"})
        target.set_employee.assert_not_called()  # yüz zaten aynı — 18 şablon tekrar gönderilmez

    def test_name_verification_mismatch_fails(self, session, devices):
        source, target = _clients(_emp("YELDA EKINCI"), _emp("BENSU YANAR"),
                                  verify_data=_emp("BENSU YANAR"))
        status, msg = _run(session, devices, source, target)
        assert status == TRANSFER_FAILED
        assert "değişmedi" in msg

    def test_new_record_gets_full_employee(self, session, devices):
        source, target = _clients(_emp("YENI KISI", FACES_A), None, verify_data=_emp("YENI KISI"))
        status, msg = _run(session, devices, source, target)
        assert status == TRANSFER_OK
        assert "yeni" in msg
        assert target.set_employee.call_args.kwargs["face_data"] == FACES_A
        assert session.query(Employee).one().name == "YENI KISI"


class TestTransferWorker:
    def _run_worker(self, session_factory, devices, items, source_map, target_map):
        """HanvonClient yerine ip'ye göre mock; worker.run() senkron çalıştırılır."""
        src, dst = devices
        clients = {}

        def factory(ip, port=None, comm_key=None):
            data = source_map if ip == src.ip else target_map
            client = MagicMock(ip=ip)
            calls = {}

            def get(emp_id):
                calls[emp_id] = calls.get(emp_id, 0) + 1
                value = data[emp_id]
                value = value[min(calls[emp_id], len(value)) - 1] if isinstance(value, list) else value
                if isinstance(value, Exception):
                    raise value
                return value
            client.get_employee.side_effect = get
            client.set_name_table.return_value = True
            client.set_employee.return_value = True
            clients[ip] = client
            return client

        results = []
        with patch.object(svc, "HanvonClient", side_effect=factory):
            worker = svc.DeviceTransferWorker(
                src.id, dst.id, items=items, session_factory=session_factory,
            )
            worker.finished_all.connect(lambda *counts: results.append(counts))
            worker.run()
        return results[0], clients[src.ip], clients[dst.ip]

    def test_counts_and_reconnect_after_failure(self, session_factory, session, devices):
        items = [TransferItem("68"), TransferItem("70"), TransferItem("3")]
        source_map = {"68": _emp("FATEMEH", FACES_A), "70": _emp("X"), "3": _emp("YELDA", FACES_A)}
        target_map = {
            "68": _emp("AYTEKIN", FACES_B),          # başka kişi → atlanır
            "70": TimeoutError("timed out"),          # okunamadı → başarısız
            "3": [_emp("BENSU", FACES_A), _emp("YELDA")],  # isim düzeltilir
        }
        (ok, failed, skipped), _, target = self._run_worker(
            session_factory, devices, items, source_map, target_map)
        assert (ok, failed, skipped) == (1, 1, 1)
        assert target.connect.call_count >= 2  # ilk bağlantı + hata sonrası yeniden
        target.set_name_table.assert_called_once_with({"3": "YELDA"})

    def test_per_item_options(self, session_factory, session, devices):
        items = [TransferItem("5", update_name=True, update_biometric=False),
                 TransferItem("6", allow_overwrite_other_person=True)]
        source_map = {"5": _emp("AD", FACES_A), "6": _emp("FATEMEH", FACES_A)}
        # 5: aynı yüz, farklı etiket (isim düzeltilir); 6: başka kişi ama açık izin var
        target_map = {"5": [_emp("ESKI", FACES_A), _emp("AD")], "6": [_emp("AYTEKIN", FACES_B), _emp("FATEMEH")]}
        (ok, failed, skipped), _, target = self._run_worker(
            session_factory, devices, items, source_map, target_map)
        assert (ok, failed, skipped) == (2, 0, 0)
        target.set_name_table.assert_called_once_with({"5": "AD"})  # yüz güncellenmedi
        assert target.set_employee.call_args.kwargs["employee_id"] == "6"

    def test_legacy_constructor_still_works(self, session_factory, session, devices):
        src, dst = devices
        worker = svc.DeviceTransferWorker(src.id, dst.id, ["1", "2"], update_name=False,
                                          update_biometric=True, session_factory=session_factory)
        assert [i.employee_id for i in worker.items] == ["1", "2"]
        assert all(not i.update_name and i.update_biometric for i in worker.items)
