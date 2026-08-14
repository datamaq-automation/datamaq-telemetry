import json
import logging
import time
from datetime import datetime
from typing import Optional, Callable
import paho.mqtt.client as mqtt

from config import settings
from database import SessionLocal
from models import Device, TelemetryInstantaneous, TelemetryEnergy, DeviceStatusLog, DeviceAlert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (MQTT) %(message)s",
)
logger = logging.getLogger("mqtt_service")


class MQTTTelemetryService:
    def __init__(self, on_message_callback: Optional[Callable] = None):
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.MQTT_CLIENT_ID,
            clean_session=True,
        )
        if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
            self.client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.on_message_callback = on_message_callback
        self.is_running = False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info("Conectado exitosamente al Broker MQTT (%s:%s)", settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT)
            client.subscribe(settings.MQTT_TOPIC_PREFIX, qos=1)
            logger.info("Suscrito a tópico: %s", settings.MQTT_TOPIC_PREFIX)
        else:
            logger.error("Fallo al conectar a MQTT con código: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        logger.warning("Desconectado de Broker MQTT. Código: %s. Reintentando...", reason_code)

    def _get_or_create_device(self, db, device_uid: str, dev_info: Optional[dict] = None) -> Device:
        clean_uid = device_uid.replace(":", "").upper()
        device = db.query(Device).filter(Device.device_uid == clean_uid).first()
        if not device:
            logger.info("Registrando nuevo dispositivo Powermeter detectado: %s", clean_uid)
            device = Device(
                device_uid=clean_uid,
                name=f"Powermeter-{clean_uid[-4:]}",
                model=dev_info.get("device_model", "SmartPlus") if dev_info else "SmartPlus",
                serial_number=dev_info.get("serial_number") if dev_info else None,
                hw_version=dev_info.get("hw_model") if dev_info else None,
                fw_version=dev_info.get("device_fw") if dev_info else None,
                status="ONLINE",
                last_seen_at=datetime.utcnow(),
            )
            db.add(device)
            db.commit()
            db.refresh(device)
        else:
            device.status = "ONLINE"
            device.last_seen_at = datetime.utcnow()
            if dev_info:
                if dev_info.get("serial_number"):
                    device.serial_number = dev_info.get("serial_number")
                if dev_info.get("device_fw"):
                    device.fw_version = dev_info.get("device_fw")
                if dev_info.get("hw_model"):
                    device.hw_version = dev_info.get("hw_model")
            db.commit()
        return device

    def _parse_timestamp(self, ts_val) -> datetime:
        if ts_val:
            try:
                if isinstance(ts_val, (int, float)) and ts_val > 1000000000:
                    return datetime.utcfromtimestamp(ts_val)
                elif isinstance(ts_val, str):
                    return datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.utcnow()

    def _handle_instantaneous(self, db, device: Device, payload: dict):
        recorded_at = self._parse_timestamp(payload.get("timestamp"))

        phase_r = payload.get("phase_r", {})
        phase_s = payload.get("phase_s", {})
        phase_t = payload.get("phase_t", {})
        total = payload.get("total", {})

        reading = TelemetryInstantaneous(
            device_id=device.id,
            recorded_at=recorded_at,
            # Fase R
            voltage_r=phase_r.get("voltage_V"),
            current_r=phase_r.get("current_A"),
            active_power_r=phase_r.get("net_active_power_W"),
            reactive_power_r=phase_r.get("net_reactive_power_VAR"),
            apparent_power_r=phase_r.get("net_apparent_power_VA"),
            power_factor_r=phase_r.get("power_factor"),
            # Fase S
            voltage_s=phase_s.get("voltage_V"),
            current_s=phase_s.get("current_A"),
            active_power_s=phase_s.get("net_active_power_W"),
            reactive_power_s=phase_s.get("net_reactive_power_VAR"),
            apparent_power_s=phase_s.get("net_apparent_power_VA"),
            power_factor_s=phase_s.get("power_factor"),
            # Fase T
            voltage_t=phase_t.get("voltage_V"),
            current_t=phase_t.get("current_A"),
            active_power_t=phase_t.get("net_active_power_W"),
            reactive_power_t=phase_t.get("net_reactive_power_VAR"),
            apparent_power_t=phase_t.get("net_apparent_power_VA"),
            power_factor_t=phase_t.get("power_factor"),
            # Totales
            total_active_power=total.get("net_active_power_W"),
            total_reactive_power=total.get("net_reactive_power_VAR"),
            total_apparent_power=total.get("net_apparent_power_VA"),
            total_power_factor=total.get("power_factor"),
        )
        db.add(reading)
        db.commit()

    def _handle_energy(self, db, device: Device, payload: dict):
        recorded_at = self._parse_timestamp(payload.get("timestamp"))

        total = payload.get("total", payload)
        reading = TelemetryEnergy(
            device_id=device.id,
            recorded_at=recorded_at,
            net_active_energy_kwh=total.get("net_active_energy_KWH"),
            net_reactive_energy_kvarh=total.get("net_reactive_energy_KVARH"),
            imported_active_energy_kwh=total.get("imported_active_energy_KWH"),
            exported_active_energy_kwh=total.get("exported_active_energy_KWH"),
            imported_reactive_energy_kvarh=total.get("imported_reactive_energy_KVARH"),
            exported_reactive_energy_kvarh=total.get("exported_reactive_energy_KVARH"),
        )
        db.add(reading)
        db.commit()

    def _handle_status(self, db, device: Device, payload: dict):
        recorded_at = self._parse_timestamp(payload.get("timestamp"))

        wifi_info = payload.get("wifi_sta", {})
        log = DeviceStatusLog(
            device_id=device.id,
            recorded_at=recorded_at,
            wifi_rssi_dbm=wifi_info.get("dbm"),
            wifi_quality=wifi_info.get("quality"),
            ip_address=wifi_info.get("ip"),
            uptime_seconds=payload.get("uptime") or payload.get("device_info", {}).get("uptime"),
            raw_payload=payload,
        )
        db.add(log)
        db.commit()

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            raw_text = msg.payload.decode("utf-8")
            payload = json.loads(raw_text) if raw_text else {}
        except Exception as e:
            logger.error("Error decodificando payload de %s: %s", topic, e)
            return

        # Notificar a WebSockets / frontend si hay callback
        if self.on_message_callback:
            try:
                self.on_message_callback(topic, payload)
            except Exception:
                pass

        # Topic format: m/wifi/{device_uid}/{subtopic}
        parts = topic.split("/")
        if len(parts) >= 4:
            channel = parts[1]  # wifi, eth, etc.
            device_uid = parts[2]
            subtopic = parts[3]

            db = SessionLocal()
            try:
                dev_info = payload.get("device_info") if isinstance(payload, dict) else None
                device = self._get_or_create_device(db, device_uid, dev_info)

                if subtopic == "inst":
                    self._handle_instantaneous(db, device, payload)
                elif subtopic in ("acc", "energyio"):
                    self._handle_energy(db, device, payload)
                elif subtopic == "status":
                    self._handle_status(db, device, payload)
                elif subtopic == "event":
                    event_msg = payload.get("event") or json.dumps(payload)
                    alert = DeviceAlert(
                        device_id=device.id,
                        alert_type="DEVICE_EVENT",
                        severity="INFO",
                        message=str(event_msg),
                        triggered_at=datetime.utcnow(),
                    )
                    db.add(alert)
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error("Error procesando mensaje de %s: %s", topic, e, exc_info=True)
            finally:
                db.close()

    def start(self):
        logger.info("Iniciando servicio de Ingesta MQTT Datamaq...")
        self.is_running = True
        self.client.connect_async(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
        self.client.loop_start()

    def stop(self):
        logger.info("Deteniendo servicio MQTT...")
        self.is_running = False
        self.client.loop_stop()
        self.client.disconnect()


if __name__ == "__main__":
    service = MQTTTelemetryService()
    service.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        service.stop()
