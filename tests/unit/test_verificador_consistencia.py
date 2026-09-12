from unittest.mock import MagicMock

from src.infrastructure.sqlalchemy.verificador_consistencia import verificar_consistencia_organizaciones


def test_verificar_consistencia_organizaciones_sin_huerfanos():
    mock_db = MagicMock()
    mock_yaml_repo = MagicMock()

    org1 = MagicMock()
    org1.id = "org-1"
    org2 = MagicMock()
    org2.id = "org-2"
    mock_yaml_repo.listar_organizaciones.return_value = [org1, org2]

    user1 = MagicMock()
    user1.id = "user-1"
    user1.username = "juan"
    user1.organization_id = "org-1"
    mock_db.query().filter().all.return_value = [user1]

    res = verificar_consistencia_organizaciones(mock_db, mock_yaml_repo)

    assert res["total_usuarios_con_org"] == 1
    assert res["usuarios_huerfanos"] == 0
    assert res["orgs_validas_yaml"] == 2


def test_verificar_consistencia_organizaciones_con_huerfanos():
    mock_db = MagicMock()
    mock_yaml_repo = MagicMock()

    org1 = MagicMock()
    org1.id = "org-1"
    mock_yaml_repo.listar_organizaciones.return_value = [org1]

    user1 = MagicMock()
    user1.id = "user-1"
    user1.username = "juan"
    user1.organization_id = "org-fantasma"
    mock_db.query().filter().all.return_value = [user1]

    res = verificar_consistencia_organizaciones(mock_db, mock_yaml_repo)

    assert res["total_usuarios_con_org"] == 1
    assert res["usuarios_huerfanos"] == 1
    assert res["orgs_validas_yaml"] == 1
