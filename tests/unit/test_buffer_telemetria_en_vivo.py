from src.adapters.gateways.in_memory_telemetria_buffer import InMemoryTelemetriaBuffer


def test_agrega_solo_topicos_inst():
    buffer = InMemoryTelemetriaBuffer()
    buffer.agregar("m/wifi/D48C49F03564/alertas", {"dispositivo_id": "dev-1"})
    buffer.agregar("system/heartbeat", {"dispositivo_id": "dev-1"})

    assert buffer.obtener("dev-1") == []


def test_agrega_y_recupera_lecturas_inst_por_dispositivo():
    buffer = InMemoryTelemetriaBuffer()
    dato_1 = {"dispositivo_id": "dev-1", "registrado_en": "2026-08-17T12:00:00Z"}
    dato_2 = {"dispositivo_id": "dev-1", "registrado_en": "2026-08-17T12:00:05Z"}
    dato_otro_dispositivo = {"dispositivo_id": "dev-2", "registrado_en": "2026-08-17T12:00:05Z"}

    buffer.agregar("m/wifi/D48C49F03564/inst", dato_1)
    buffer.agregar("m/wifi/D48C49F03564/inst", dato_2)
    buffer.agregar("m/wifi/AABBCCDDEEFF/inst", dato_otro_dispositivo)

    assert buffer.obtener("dev-1") == [dato_1, dato_2]
    assert buffer.obtener("dev-2") == [dato_otro_dispositivo]


def test_ignora_mensajes_sin_dispositivo_id():
    buffer = InMemoryTelemetriaBuffer()
    buffer.agregar("m/wifi/D48C49F03564/inst", {"potencia_activa_total_W": 100.0})

    assert buffer.obtener("dev-1") == []


def test_dispositivo_sin_lecturas_devuelve_lista_vacia():
    buffer = InMemoryTelemetriaBuffer()

    assert buffer.obtener("dev-inexistente") == []


def test_descarta_lecturas_mas_viejas_que_el_maxlen():
    buffer = InMemoryTelemetriaBuffer(max_por_dispositivo=2)
    for i in range(5):
        buffer.agregar("m/wifi/D48C49F03564/inst", {"dispositivo_id": "dev-1", "n": i})

    assert [d["n"] for d in buffer.obtener("dev-1")] == [3, 4]
