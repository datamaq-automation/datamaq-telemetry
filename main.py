import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from database import get_db, engine, Base
import models
import schemas
from mqtt_service import MQTTTelemetryService

# Active WebSocket connections
active_connections: List[WebSocket] = []


def broadcast_mqtt_to_websockets(topic: str, payload: dict):
    if not active_connections:
        return
    msg = json.dumps({"topic": topic, "data": payload, "received_at": datetime.utcnow().isoformat()})
    # Loop over copy to handle disconnections safely
    for ws in list(active_connections):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(msg), loop)
        except Exception:
            pass


mqtt_daemon = MQTTTelemetryService(on_message_callback=broadcast_mqtt_to_websockets)
loop = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    # Try auto-create tables if connection works
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[Warning] Could not auto-create tables on start: {e}")

    # Start MQTT daemon
    try:
        mqtt_daemon.start()
    except Exception as e:
        print(f"[Warning] Could not connect MQTT daemon on start: {e}")

    yield

    # Shutdown MQTT daemon
    mqtt_daemon.stop()


app = FastAPI(
    title="Datamaq Telemetry Platform API",
    description="Backend de telemetría y gestión de medidores Powermeter para Datamaq",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "mqtt_connected": mqtt_daemon.client.is_connected() if hasattr(mqtt_daemon.client, "is_connected") else False,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ==============================
# WebSockets Live Telemetry Stream
# ==============================
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive / listen for ping
    except WebSocketDisconnect:
        active_connections.remove(websocket)


# ==============================
# Organizations / Clientes
# ==============================
@app.get("/api/organizations", response_model=List[schemas.OrganizationOut], tags=["Organizations"])
def list_organizations(db: Session = Depends(get_db)):
    return db.query(models.Organization).all()


@app.post("/api/organizations", response_model=schemas.OrganizationOut, tags=["Organizations"])
def create_organization(org_in: schemas.OrganizationCreate, db: Session = Depends(get_db)):
    org = models.Organization(**org_in.model_dump())
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


# ==============================
# Facilities / Plantas
# ==============================
@app.get("/api/facilities", response_model=List[schemas.FacilityOut], tags=["Facilities"])
def list_facilities(org_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Facility)
    if org_id:
        query = query.filter(models.Facility.organization_id == org_id)
    return query.all()


@app.post("/api/facilities", response_model=schemas.FacilityOut, tags=["Facilities"])
def create_facility(fac_in: schemas.FacilityCreate, db: Session = Depends(get_db)):
    fac = models.Facility(**fac_in.model_dump())
    db.add(fac)
    db.commit()
    db.refresh(fac)
    return fac


# ==============================
# Devices / Medidores
# ==============================
@app.get("/api/devices", response_model=List[schemas.DeviceOut], tags=["Devices"])
def list_devices(facility_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Device)
    if facility_id:
        query = query.filter(models.Device.facility_id == facility_id)
    return query.all()


@app.get("/api/devices/{device_id}", response_model=schemas.DeviceOut, tags=["Devices"])
def get_device(device_id: str, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        # Also try searching by device_uid
        device = db.query(models.Device).filter(models.Device.device_uid == device_id.upper()).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


@app.put("/api/devices/{device_id}", response_model=schemas.DeviceOut, tags=["Devices"])
def update_device(device_id: str, dev_in: schemas.DeviceUpdate, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    update_data = dev_in.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(device, k, v)

    db.commit()
    db.refresh(device)
    return device


# ==============================
# Telemetry Readings
# ==============================
@app.get("/api/telemetry/latest/{device_id}", tags=["Telemetry"])
def get_latest_telemetry(device_id: str, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(
        (models.Device.id == device_id) | (models.Device.device_uid == device_id.upper())
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    latest_inst = (
        db.query(models.TelemetryInstantaneous)
        .filter(models.TelemetryInstantaneous.device_id == device.id)
        .order_by(desc(models.TelemetryInstantaneous.recorded_at))
        .first()
    )

    latest_energy = (
        db.query(models.TelemetryEnergy)
        .filter(models.TelemetryEnergy.device_id == device.id)
        .order_by(desc(models.TelemetryEnergy.recorded_at))
        .first()
    )

    return {
        "device": schemas.DeviceOut.model_validate(device),
        "instantaneous": schemas.TelemetryInstantaneousOut.model_validate(latest_inst) if latest_inst else None,
        "energy": schemas.TelemetryEnergyOut.model_validate(latest_energy) if latest_energy else None,
    }


@app.get("/api/telemetry/instantaneous/{device_id}", response_model=List[schemas.TelemetryInstantaneousOut], tags=["Telemetry"])
def get_instantaneous_history(
    device_id: str,
    limit: int = Query(100, le=1000),
    hours: Optional[int] = Query(None, description="Últimas N horas"),
    db: Session = Depends(get_db),
):
    device = db.query(models.Device).filter(
        (models.Device.id == device_id) | (models.Device.device_uid == device_id.upper())
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    query = db.query(models.TelemetryInstantaneous).filter(
        models.TelemetryInstantaneous.device_id == device.id
    )

    if hours:
        since = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(models.TelemetryInstantaneous.recorded_at >= since)

    return query.order_by(desc(models.TelemetryInstantaneous.recorded_at)).limit(limit).all()


@app.get("/api/telemetry/energy/{device_id}", response_model=List[schemas.TelemetryEnergyOut], tags=["Telemetry"])
def get_energy_history(
    device_id: str,
    limit: int = Query(100, le=1000),
    days: Optional[int] = Query(None, description="Últimos N días"),
    db: Session = Depends(get_db),
):
    device = db.query(models.Device).filter(
        (models.Device.id == device_id) | (models.Device.device_uid == device_id.upper())
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    query = db.query(models.TelemetryEnergy).filter(
        models.TelemetryEnergy.device_id == device.id
    )

    if days:
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(models.TelemetryEnergy.recorded_at >= since)

    return query.order_by(desc(models.TelemetryEnergy.recorded_at)).limit(limit).all()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.API_HOST, port=settings.API_PORT, reload=settings.DEBUG)
