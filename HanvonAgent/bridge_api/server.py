"""
BridgeApi — Gömülü HTTP sunucu (FastAPI).

Dış sistemler tarafından GET ile veri çekebilmesi için.

Endpoints:
- GET /api/status              → Uygulama durumu
- GET /api/devices             → Cihaz listesi
- GET /api/records             → Tüm kayıtlar (filtre ile)
- GET /api/records/{date}      → Belirli tarih
- GET /api/employees           → Personel listesi
"""

from fastapi import FastAPI, Query, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, List
from contextlib import asynccontextmanager

from models import Device, Record, Employee, Setting, get_session


# Global state
_app_state = {
    "running": False,
    "db_session": None,
}


_bearer_scheme = HTTPBearer(auto_error=False)


def create_app(db_session: Session) -> FastAPI:
    """FastAPI uygulaması oluştur."""
    _app_state["db_session"] = db_session

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup/shutdown."""
        _app_state["running"] = True
        yield
        _app_state["running"] = False

    app = FastAPI(
        title="HanvonAgent BridgeApi",
        version="1.0.0",
        lifespan=lifespan,
    )

    def verify_token(credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme)):
        """Bearer token doğrulama. api_token ayarı boşsa auth devre dışı."""
        setting = db_session.query(Setting).filter(Setting.key == "api_token").first()
        expected = setting.value if setting else None
        if not expected:
            return  # token ayarlanmamışsa herkese açık
        if credentials is None or credentials.credentials != expected:
            raise HTTPException(status_code=401, detail="Geçersiz veya eksik Bearer token")

    @app.get("/api/status")
    async def get_status(_=Depends(verify_token)):
        """Uygulama durumu."""
        session = _app_state["db_session"]
        device_count = session.query(Device).count()
        record_count = session.query(Record).count()
        employee_count = session.query(Employee).count()

        return {
            "status": "online",
            "timestamp": datetime.utcnow().isoformat(),
            "devices": device_count,
            "employees": employee_count,
            "records": record_count,
        }

    @app.get("/api/devices")
    async def get_devices(_=Depends(verify_token)):
        """Kayıtlı cihazlar."""
        session = _app_state["db_session"]
        devices = session.query(Device).all()

        return {
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "ip": d.ip,
                    "enabled": d.enabled,
                    "last_connected": d.last_connected.isoformat() if d.last_connected else None,
                    "created_at": d.created_at.isoformat(),
                }
                for d in devices
            ]
        }

    @app.get("/api/records")
    async def get_records(
        date: Optional[str] = Query(None, description="Tarih (YYYY-MM-DD)"),
        device_ip: Optional[str] = Query(None, description="Cihaz IP'si"),
        push_status: Optional[str] = Query(None, description="Push durumu (pending/sent/failed)"),
        _=Depends(verify_token),
    ):
        """Kayıtları getir (filtre ile)."""
        session = _app_state["db_session"]
        query = session.query(Record)

        if date:
            query = query.filter(Record.record_time.like(f"{date}%"))
        if device_ip:
            query = query.join(Device).filter(Device.ip == device_ip)
        if push_status:
            query = query.filter(Record.push_status == push_status)

        records = query.all()

        return {
            "count": len(records),
            "records": [
                {
                    "id": r.id,
                    "device_ip": r.device.ip,
                    "record_time": r.record_time,
                    "employee_id": r.employee.employee_device_id if r.employee else None,
                    "employee_name": r.employee.name if r.employee else None,
                    "status": r.status,
                    "card_src": r.card_src,
                    "source": r.source,
                    "push_status": r.push_status,
                    "pushed_at": r.pushed_at.isoformat() if r.pushed_at else None,
                }
                for r in records
            ]
        }

    @app.get("/api/records/{date}")
    async def get_records_by_date(date: str, device_ip: Optional[str] = None, _=Depends(verify_token)):
        """Belirli tarih için kayıtlar."""
        session = _app_state["db_session"]
        query = session.query(Record).filter(Record.record_time.like(f"{date}%"))

        if device_ip:
            query = query.join(Device).filter(Device.ip == device_ip)

        records = query.all()

        return {
            "date": date,
            "count": len(records),
            "records": [
                {
                    "id": r.id,
                    "device_ip": r.device.ip,
                    "record_time": r.record_time,
                    "employee_id": r.employee.employee_device_id if r.employee else None,
                    "employee_name": r.employee.name if r.employee else None,
                    "status": r.status,
                    "card_src": r.card_src,
                    "source": r.source,
                    "push_status": r.push_status,
                }
                for r in records
            ]
        }

    @app.get("/api/employees")
    async def get_employees(device_id: Optional[int] = None, _=Depends(verify_token)):
        """Personel listesi."""
        session = _app_state["db_session"]
        query = session.query(Employee)

        if device_id:
            query = query.filter(Employee.device_id == device_id)

        employees = query.all()

        return {
            "count": len(employees),
            "employees": [
                {
                    "id": e.id,
                    "device_id": e.device_id,
                    "employee_device_id": e.employee_device_id,
                    "name": e.name,
                    "card_num": e.card_num,
                    "check_type": e.check_type,
                    "last_synced": e.last_synced.isoformat() if e.last_synced else None,
                }
                for e in employees
            ]
        }

    return app


class BridgeApiServer:
    """BridgeApi sunucu wrapper."""

    def __init__(self, db_session: Session, host: str = "127.0.0.1", port: int = 8765):
        self.db_session = db_session
        self.host = host
        self.port = port
        self.app = create_app(db_session)

    def start(self):
        """Sunucuyu başlat (ayrı thread'de)."""
        import uvicorn
        import threading

        def run_server():
            uvicorn.run(
                self.app,
                host=self.host,
                port=self.port,
                log_level="warning",
            )

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

    def stop(self):
        """Sunucuyu durdur (uvicorn shutdown)."""
        # Uvicorn shutdown mekanizması
        pass
