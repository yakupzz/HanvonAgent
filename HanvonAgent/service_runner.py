"""
Windows Service runner — NSSM ile çalıştırılan headless arka plan servisi.

Kurulum:
  NSSM install HanvonAgent "python D:\Projeler\F710\HanvonAgent\service_runner.py"
  NSSM start HanvonAgent

Kaldırma:
  NSSM stop HanvonAgent
  NSSM remove HanvonAgent confirm
"""

import sys
import logging
from datetime import datetime

from core import app_paths
from models import init_db, get_session
from services.scheduler_service import SchedulerService
from services.record_service import RecordService
from services.push_service import PushService
from bridge_api.server import BridgeApiServer


# Logging setup — under %PROGRAMDATA%\HanvonAgent\logs (shared with the GUI).
log_dir = app_paths.logs_dir()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "hanvon_service.log"),
        logging.StreamHandler(sys.stdout),
    ]
)

logger = logging.getLogger(__name__)


class HanvonService:
    """Windows Service application."""

    def __init__(self):
        logger.info("=" * 60)
        logger.info("HanvonAgent Service Starting")
        logger.info("=" * 60)

        # Database init
        init_db()
        logger.info("Database initialized")

        self.session = get_session()
        self.scheduler = None
        self.bridge_api = None

    def start(self):
        """Servisi başlat."""
        try:
            # SchedulerService başlat
            self.scheduler = SchedulerService(self.session)
            self.scheduler.start()
            logger.info("SchedulerService started")

            # BridgeApi başlat
            self.bridge_api = BridgeApiServer(self.session, host="0.0.0.0", port=8765)
            self.bridge_api.start()
            logger.info("BridgeApi started (port 8765)")

            logger.info("HanvonAgent Service is running")

            # Infinity loop
            try:
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Interrupt received")
                self.stop()

        except Exception as e:
            logger.error(f"Service startup failed: {str(e)}", exc_info=True)
            sys.exit(1)

    def stop(self):
        """Servisi durdur."""
        logger.info("Stopping HanvonService...")

        try:
            if self.scheduler:
                self.scheduler.stop()
                logger.info("SchedulerService stopped")

            if self.bridge_api:
                self.bridge_api.stop()
                logger.info("BridgeApi stopped")

            if self.session:
                self.session.close()
                logger.info("Database session closed")

            logger.info("=" * 60)
            logger.info("HanvonAgent Service Stopped")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}", exc_info=True)


def main():
    """Main entry point."""
    service = HanvonService()
    service.start()


if __name__ == "__main__":
    main()
