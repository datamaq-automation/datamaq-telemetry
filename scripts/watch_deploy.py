#!/usr/bin/env python3
"""
Monitorea en tiempo real el progreso de GitHub Actions (CI & CD Deploy al VPS)
después de un git push, mostrando estado, duración y logs en caso de fallos.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from typing import Any


def check_gh_cli() -> bool:
    """Verifica si GitHub CLI (gh) está instalado y autenticado."""
    if not shutil.which("gh"):
        print("[!] GitHub CLI ('gh') no está instalado en el sistema.", file=sys.stderr)
        print("[i] Instálelo con: sudo apt install gh && gh auth login", file=sys.stderr)
        return False
    res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if res.returncode != 0:
        print("[!] GitHub CLI no está autenticado. Ejecute 'gh auth login'.", file=sys.stderr)
        return False
    return True


def obtener_commit_actual() -> str:
    res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return res.stdout.strip()


def obtener_commit_corto() -> str:
    res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
    return res.stdout.strip()


def obtener_rama_actual() -> str:
    res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
    return res.stdout.strip()


def buscar_runs_para_commit(commit_sha: str) -> list[dict[str, Any]]:
    """Consulta la API de GitHub Actions vía gh CLI para listar workflows de este commit."""
    cmd = [
        "gh",
        "run",
        "list",
        "--commit",
        commit_sha,
        "--json",
        "databaseId,name,status,conclusion,url,createdAt,updatedAt",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return []
    try:
        data = json.loads(res.stdout)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def formatear_estado(status: str, conclusion: str | None) -> tuple[str, str]:
    """Devuelve un emoji/icono y descripción con color."""
    if status == "completed":
        if conclusion == "success":
            return "✓", "\033[92mSUCCESS\033[0m"  # Verde
        elif conclusion == "failure":
            return "✗", "\033[91mFAILED\033[0m"   # Rojo
        elif conclusion == "cancelled":
            return "⊘", "\033[90mCANCELLED\033[0m"
        else:
            return "•", f"\033[93m{conclusion or 'UNKNOWN'}\033[0m"
    elif status == "in_progress":
        return "⟳", "\033[93mIN_PROGRESS\033[0m"  # Amarillo
    elif status == "queued":
        return "⏳", "\033[94mQUEUED\033[0m"       # Azul
    return "•", status


def monitorear_workflows(commit_sha: str, timeout_seconds: int = 600, poll_interval: float = 3.0) -> bool:
    short_sha = commit_sha[:7]
    branch = obtener_rama_actual()

    print("\n" + "=" * 65)
    print(f"  🚀 MONITOREO DE DESPLIEGUE CONTINUO (CI/CD) — {short_sha} ({branch})")
    print("=" * 65)
    print("[*] Esperando a que GitHub Actions registre los workflows...")

    start_time = time.time()
    runs: list[dict[str, Any]] = []

    # Esperar hasta 20 segundos para que aparezcan los workflows disparados por el push
    wait_registered_max = 20
    registered_elapsed = 0
    while registered_elapsed < wait_registered_max:
        runs = buscar_runs_para_commit(commit_sha)
        if runs:
            break
        time.sleep(2)
        registered_elapsed += 2
        print(f"    Esperando registro en GitHub... ({registered_elapsed}s)", end="\r", flush=True)

    if not runs:
        print("\n[!] No se encontraron workflows iniciados en GitHub para este commit.")
        print("[i] Verifique que el commit haya sido pusheado a la rama correcta en el remoto.")
        return False

    print(f"\n[+] {len(runs)} workflows detectados para este commit:")
    for r in runs:
        print(f"    • {r.get('name')}: {r.get('url')}")
    print()

    # Loop de seguimiento en tiempo real
    todos_completados = False
    exito_total = True

    while not todos_completados and (time.time() - start_time) < timeout_seconds:
        runs = buscar_runs_para_commit(commit_sha)
        if not runs:
            time.sleep(poll_interval)
            continue

        todos_completados = True
        elapsed_total = int(time.time() - start_time)

        output_lines = []
        output_lines.append(f"⏱  Tiempo transcurrido: {elapsed_total}s")

        for r in runs:
            status = r.get("status", "")
            conclusion = r.get("conclusion")
            name = r.get("name", "Workflow")
            icon, color_status = formatear_estado(status, conclusion)

            output_lines.append(f"  {icon} [{color_status}] {name:<20}")

            if status != "completed":
                todos_completados = False

        # Imprimir actualización en terminal
        sys.stdout.write("\033[F" * len(output_lines))
        for line in output_lines:
            sys.stdout.write(f"\033[K{line}\n")
        sys.stdout.flush()

        if not todos_completados:
            time.sleep(poll_interval)

    # Evaluación final
    print("\n" + "=" * 65)
    fallos = []
    for r in runs:
        name = r.get("name", "")
        conclusion = r.get("conclusion")
        run_id = r.get("databaseId")
        if conclusion != "success":
            exito_total = False
            fallos.append((name, run_id))

    if exito_total:
        print("  ✓ ¡DESPLIEGUE Y CI COMPLETADOS EXITOSAMENTE!")
        print("  ✓ El backend datamaq-telemetry está activo y verificado en el VPS.")
        print("=" * 65 + "\n")
        return True
    else:
        print("  ✗ EL PIPELINE DE CI/CD FINALIZÓ CON ERRORES.")
        print("=" * 65 + "\n")
        for name, run_id in fallos:
            if run_id:
                print(f"\n[*] Extrayendo logs de error para '{name}' (Run ID: {run_id})...\n")
                subprocess.run(["gh", "run", "view", str(run_id), "--log-failed"])
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitorea el progreso de CI/CD en GitHub Actions tras un git push."
    )
    parser.add_argument(
        "--commit",
        default=None,
        help="Hash del commit a monitorear (default: HEAD actual)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Tiempo máximo de espera en segundos (default: 600)",
    )
    args = parser.parse_args()

    if not check_gh_cli():
        sys.exit(1)

    commit_sha = args.commit or obtener_commit_actual()
    exito = monitorear_workflows(commit_sha, timeout_seconds=args.timeout)
    sys.exit(0 if exito else 1)


if __name__ == "__main__":
    main()
