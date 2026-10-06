"""tests/unit/test_auditoria_cambios_ti.py — Tests de detección de cambios TI."""

from scripts.detect_ti_changes import compare_ti_config, extract_device_id_from_yaml


class TestCompareTIConfig:
    """Test cases para detección de cambios en configuración TI."""

    def test_detectar_cambio_correccion_angular_fases(self) -> None:
        old_config = {"correccion_angular_fases": "R:180,S:-120"}
        new_config = {"correccion_angular_fases": "R:0,S:15"}
        changes = compare_ti_config(old_config, new_config)

        assert len(changes) == 1
        assert changes[0]["field"] == "correccion_angular_fases"
        assert changes[0]["old"] == "R:180,S:-120"
        assert changes[0]["new"] == "R:0,S:15"

    def test_ignorar_cambios_no_ti(self) -> None:
        old_config = {"nombre": "Medidor 1", "ubicacion": "TGBT Trafo 2"}
        new_config = {"nombre": "Medidor 1", "ubicacion": "TGBT Trafo 3"}
        changes = compare_ti_config(old_config, new_config)

        assert len(changes) == 0

    def test_multiples_cambios_ti(self) -> None:
        old_config = {
            "correccion_angular_fases": "R:0,S:0",
            "invertido": False,
            "fases_con_ti": "R,S,T",
        }
        new_config = {
            "correccion_angular_fases": "R:0,S:15",
            "invertido": True,
            "fases_con_ti": "R,S,T",
        }
        changes = compare_ti_config(old_config, new_config)

        assert len(changes) == 2
        assert any(c["field"] == "correccion_angular_fases" for c in changes)
        assert any(c["field"] == "invertido" for c in changes)

    def test_cambio_invertido(self) -> None:
        old_config = {"invertido": False}
        new_config = {"invertido": True}
        changes = compare_ti_config(old_config, new_config)

        assert len(changes) == 1
        assert changes[0]["field"] == "invertido"
        assert changes[0]["old"] == "False"
        assert changes[0]["new"] == "True"

    def test_sin_cambios(self) -> None:
        old_config = {"correccion_angular_fases": "R:0,S:15", "invertido": False}
        new_config = {"correccion_angular_fases": "R:0,S:15", "invertido": False}
        changes = compare_ti_config(old_config, new_config)

        assert len(changes) == 0

    def test_capturar_motivo_desde_fuente_dato(self) -> None:
        config = {
            "correccion_angular_fases": "R:0,S:15",
            "fuente_dato": "A0 Trafo 2 (2026-10-05): análisis 4 días",
        }
        assert config.get("fuente_dato") == "A0 Trafo 2 (2026-10-05): análisis 4 días"

    def test_ninguno_vs_valor(self) -> None:
        old_config = {"correccion_angular_fases": None}
        new_config = {"correccion_angular_fases": "R:0,S:15"}
        changes = compare_ti_config(old_config, new_config)

        assert len(changes) == 1
        assert changes[0]["old"] is None
        assert changes[0]["new"] == "R:0,S:15"


class TestExtractDeviceIDFromYAML:
    """Test cases para extracción de dispositivos desde YAML."""

    def test_extraer_dispositivos_validos(self) -> None:
        yaml_data = {
            "organizaciones": [
                {
                    "org_id": "ABC",
                    "plantas": [
                        {
                            "planta_id": "P1",
                            "dispositivos": [
                                {"dispositivo_id": "uuid-1", "alias": "369"},
                                {"dispositivo_id": "uuid-2", "alias": "370"},
                            ],
                        }
                    ],
                }
            ]
        }
        mapping = extract_device_id_from_yaml(yaml_data)

        assert len(mapping) == 2
        assert "uuid-1" in mapping
        assert "uuid-2" in mapping
        assert mapping["uuid-1"]["alias"] == "369"

    def test_yaml_vacio(self) -> None:
        mapping = extract_device_id_from_yaml(None)
        assert mapping == {}

    def test_yaml_sin_dispositivos(self) -> None:
        yaml_data = {"organizaciones": [{"org_id": "ABC", "plantas": []}]}
        mapping = extract_device_id_from_yaml(yaml_data)
        assert mapping == {}

    def test_dispositivos_sin_id(self) -> None:
        yaml_data = {
            "organizaciones": [
                {
                    "org_id": "ABC",
                    "plantas": [
                        {
                            "planta_id": "P1",
                            "dispositivos": [{"alias": "369"}],  # Sin dispositivo_id
                        }
                    ],
                }
            ]
        }
        mapping = extract_device_id_from_yaml(yaml_data)
        assert mapping == {}
