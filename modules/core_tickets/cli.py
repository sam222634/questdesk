#!/usr/bin/env python3
"""
Cliente CLI ligero para QuestDesk (sin dependencias externas; usa librería estándar de Python).
Permite gestionar tickets desde la terminal hablando con el servicio en http://localhost:8000.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = os.environ.get("QUESTDESK_API_URL", "http://localhost:8000/api/v1")


def _request(method: str, path: str, data: dict | None = None):
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        print(f"Error HTTP {err.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as err:
        print(f"No se pudo conectar con {API_BASE}: {err.reason}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args):
    params = {}
    if args.status:
        params["status"] = args.status
    if args.queue:
        params["queue"] = args.queue
    if args.all:
        params["include_closed"] = "true"
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    tickets = _request("GET", f"/tickets{query}")
    if not tickets:
        print("No hay tickets que coincidan con el filtro.")
        return
    print(f"{'CÓDIGO':<10} {'ESTADO':<13} {'PRIO':<9} {'PTS':<4} {'MIN':<5} TÍTULO")
    print("-" * 78)
    for t in tickets:
        print(
            f"{t['ticket_code']:<10} {t['status_name']:<13} {t['priority_name']:<9} "
            f"{t['estimated_points']:<4} {t['total_minutes']:<5} {t['title']}"
        )


def cmd_new(args):
    payload = {
        "title": args.title,
        "description": args.desc or args.title,
        "queue_slug": args.queue,
        "priority_name": args.prio.upper(),
        "estimated_points": args.points,
        "channel": "CLI",
    }
    res = _request("POST", "/tickets", payload)
    print(f"Ticket creado: {res['ticket_code']} -> Bitácora: {res['bitacora_uri']}")


def cmd_status(args, status_name: str):
    res = _request(
        "PATCH",
        f"/tickets/{args.code}/status",
        {"status_name": status_name, "actor": "cli", "notes": args.notes},
    )
    print(f"{res['ticket_code']}: {res['previous_status']} -> {res['new_status']}")


def main():
    parser = argparse.ArgumentParser(description="QuestDesk CLI — Gestor de Tickets")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Listar tickets pendientes")
    p_list.add_argument("--status", help="Filtrar por estado (NEW, IN_PROGRESS, RESOLVED...)")
    p_list.add_argument("--queue", help="Filtrar por cola (general, infra, dev, personal)")
    p_list.add_argument("--all", action="store_true", help="Incluir tickets resueltos/cerrados")

    p_new = sub.add_parser("new", help="Crear un nuevo ticket")
    p_new.add_argument("title", help="Título del ticket")
    p_new.add_argument("-d", "--desc", help="Descripción detallada")
    p_new.add_argument("-q", "--queue", default="general", help="Cola (general, infra, dev, personal)")
    p_new.add_argument("-p", "--prio", default="MEDIUM", help="Prioridad (LOW, MEDIUM, HIGH, CRITICAL)")
    p_new.add_argument("--points", type=int, default=1, help="Esfuerzo estimado (1-10)")

    p_start = sub.add_parser("start", help="Iniciar trabajo/foco en un ticket (IN_PROGRESS)")
    p_start.add_argument("code", help="Código del ticket (ej. DEV-0001)")
    p_start.add_argument("-n", "--notes", help="Nota de inicio de sesión")

    p_done = sub.add_parser("done", help="Marcar ticket como resuelto (RESOLVED)")
    p_done.add_argument("code", help="Código del ticket (ej. DEV-0001)")
    p_done.add_argument("-n", "--notes", help="Nota de resolución")

    args = parser.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "new":
        cmd_new(args)
    elif args.cmd == "start":
        cmd_status(args, "IN_PROGRESS")
    elif args.cmd == "done":
        cmd_status(args, "RESOLVED")


if __name__ == "__main__":
    main()
