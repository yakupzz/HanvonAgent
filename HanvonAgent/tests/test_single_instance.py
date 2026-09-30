"""
SingleInstance testleri — ikinci GUI açılışı yeni kopya başlatmaz, açık
pencereyi öne getirir (2026-09-30: iki örnek aynı cihaza paralel bağlandı).
"""

import os
import subprocess
import sys
import time
import uuid

import pytest

from core.single_instance import SingleInstance


@pytest.fixture
def names(tmp_path):
    return tmp_path / "gui.lock", f"HanvonAgent-test-{uuid.uuid4().hex}"


def _holder_process(lock_path):
    """Kilidi alıp bekleyen ayrı bir süreç (gerçek 'ilk örnek')."""
    code = (
        "import sys, time\n"
        "from PySide6.QtCore import QLockFile\n"
        "lock = QLockFile(sys.argv[1]); lock.setStaleLockTime(0)\n"
        "assert lock.tryLock(1000)\n"
        "print('locked', flush=True)\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(lock_path)],
        stdout=subprocess.PIPE, text=True,
    )
    assert proc.stdout.readline().strip() == "locked"
    return proc


class TestSingleInstance:
    def test_first_acquires_second_does_not(self, qapp, names):
        lock_path, server = names
        first = SingleInstance(lock_path, server)
        second = SingleInstance(lock_path, server)
        try:
            assert first.acquire() is True
            assert second.acquire() is False
        finally:
            first.release()

    def test_second_activates_first(self, qapp, qtbot, names):
        lock_path, server = names
        first = SingleInstance(lock_path, server)
        second = SingleInstance(lock_path, server)
        try:
            assert first.acquire()
            with qtbot.waitSignal(first.activated, timeout=3000):
                assert second.notify_primary() is True
        finally:
            first.release()

    def test_notify_without_primary_returns_false(self, qapp, names):
        lock_path, server = names
        assert SingleInstance(lock_path, server).notify_primary(timeout_ms=200) is False

    def test_release_lets_next_instance_acquire(self, qapp, names):
        lock_path, server = names
        first = SingleInstance(lock_path, server)
        assert first.acquire()
        first.release()
        again = SingleInstance(lock_path, server)
        try:
            assert again.acquire() is True
        finally:
            again.release()

    def test_old_lock_of_live_process_not_stolen_dead_process_lock_recovered(self, qapp, names):
        """Uygulama günlerce açık kalır: kilit dosyası eski diye çalınmamalı.
        Kilidi tutan süreç ölünce (çökme) kilit geri alınabilmeli."""
        lock_path, server = names
        holder = _holder_process(lock_path)
        try:
            hour_ago = time.time() - 3600
            os.utime(lock_path, (hour_ago, hour_ago))
            assert SingleInstance(lock_path, server).acquire() is False
        finally:
            holder.kill()
            holder.wait(timeout=10)

        after_crash = SingleInstance(lock_path, server)
        try:
            assert after_crash.acquire() is True
        finally:
            after_crash.release()
