from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import re
from app.config import settings


def _neutralize_description(description: str) -> str:
    text = re.sub(r"(?m)^(#{1,2})(\s|$)", r"\\\1\2", description.strip())
    if sum(1 for line in text.split("\n") if line.lstrip().startswith("```")) % 2:
        text += "\n```"
    return text


def generate_bitacora_markdown(
    ticket_code: str,
    title: str,
    description: str,
    queue_slug: str,
    priority_name: str,
    estimated_points: int,
    channel: str,
    sender_email: Optional[str] = None,
) -> str:
    target_dir: Path = settings.bitacoras_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{ticket_code}.md"
    file_path = target_dir / file_name
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not file_path.exists():
        sender_line = f"\nsender_email: {sender_email}" if sender_email else ""
        content = f"""---
ticket_code: {ticket_code}
title: "{title.replace('"', '\\"')}"
queue: {queue_slug}
priority: {priority_name}
estimated_points: {estimated_points}
source_channel: {channel}{sender_line}
created_at: {now_iso}
status: NEW
---

# {ticket_code}: {title}

## 1. Descripción del Ticket
{_neutralize_description(description)}

## 2. Bitácora de Investigación y Ejecución
- [ ] Análisis inicial del requerimiento
- [ ] Ejecución de pasos técnicos

```bash
# Registra aquí los comandos, pruebas o notas relevantes
```

## 3. Causa Raíz / Hallazgos
_Pendiente de documentar._

## 4. Solución Aplicada y Verificación
_Pendiente de documentar al resolver el ticket._
"""
        file_path.write_text(content, encoding="utf-8")

    return f"bitacoras/{file_name}"


def update_bitacora_status(ticket_code: str, new_status: str) -> None:
    file_path = settings.bitacoras_dir / f"{ticket_code}.md"
    if not file_path.exists():
        return

    content = file_path.read_text(encoding="utf-8")
    updated = re.sub(
        r"(?m)^status:\s*\S+$",
        f"status: {new_status}",
        content,
        count=1,
    )
    if updated != content:
        file_path.write_text(updated, encoding="utf-8")


def read_bitacora_markdown(ticket_code: str) -> str:
    file_path = settings.bitacoras_dir / f"{ticket_code.upper()}.md"
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


SECTIONS = (
    ("descripcion", 1, "Descripción del Ticket", False),
    ("investigacion", 2, "Bitácora de Investigación y Ejecución", True),
    ("causa_raiz", 3, "Causa Raíz / Hallazgos", True),
    ("solucion", 4, "Solución Aplicada y Verificación", True),
)
SECTION_KEYS = {key for key, _, _, _ in SECTIONS}
MAX_SECTION_CHARS = 20000
EMPTY_SECTION_TEXT = "_Pendiente de documentar._"

_FENCE_RE = re.compile(r"^\s*```")
_SECTION_HEADING_RE = re.compile(r"^## (\d)\. ")
_STRUCTURE_LINE_RE = re.compile(r"^#{1,2}(\s|$)")
_HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z!?]")
_DANGEROUS_URI_RE = re.compile(r"(?i)\b(?:javascript|vbscript|data)\s*:")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class BitacoraValidationError(ValueError):
    pass


def _split_document(text: str):
    head_lines, bodies, current = [], {}, None
    in_fence = False
    number_to_key = {number: key for key, number, _, _ in SECTIONS}
    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _SECTION_HEADING_RE.match(line)
        if match and int(match.group(1)) in number_to_key:
            current = number_to_key[int(match.group(1))]
            bodies[current] = []
            continue
        (head_lines if current is None else bodies[current]).append(line)
    return "\n".join(head_lines).rstrip("\n"), {k: "\n".join(v).strip("\n") for k, v in bodies.items()}


def parse_bitacora_sections(text: str) -> list:
    _, bodies = _split_document(text)
    return [
        {"key": key, "number": number, "title": title, "editable": editable, "content": bodies.get(key, "")}
        for key, number, title, editable in SECTIONS
    ]


def sanitize_section_content(content: str) -> str:
    text = _CONTROL_CHARS_RE.sub("", content.replace("\r\n", "\n").replace("\r", "\n"))
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")
    if len(text) > MAX_SECTION_CHARS:
        raise BitacoraValidationError(f"El bloque excede {MAX_SECTION_CHARS} caracteres.")
    if _DANGEROUS_URI_RE.search(text):
        raise BitacoraValidationError("Se rechazan enlaces con esquemas javascript:, vbscript: o data:.")
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _HTML_TAG_RE.search(line):
            raise BitacoraValidationError("No se permite HTML ni etiquetas de script en la bitácora.")
        if _STRUCTURE_LINE_RE.match(line):
            raise BitacoraValidationError("No se permiten encabezados de nivel 1 o 2: la estructura del archivo es fija.")
    if in_fence:
        raise BitacoraValidationError("Hay un bloque de código sin cerrar (```).")
    return text


def apply_section_update(text: str, key: str, content: str, mode: str) -> str:
    if key not in SECTION_KEYS:
        raise BitacoraValidationError("Sección desconocida.")
    section = next(s for s in SECTIONS if s[0] == key)
    if not section[3]:
        raise BitacoraValidationError("Esta sección es de solo lectura.")
    if not text.strip():
        raise BitacoraValidationError("La bitácora del ticket no existe.")

    clean = sanitize_section_content(content)
    head, bodies = _split_document(text)
    if mode == "append":
        previous = bodies.get(key, "")
        if previous.strip() == EMPTY_SECTION_TEXT:
            previous = ""
        clean = sanitize_section_content(f"{previous}\n\n{clean}" if previous and clean else previous or clean)
    bodies[key] = clean or EMPTY_SECTION_TEXT

    parts = [head, ""]
    for skey, number, title, _ in SECTIONS:
        parts.append(f"## {number}. {title}")
        parts.append(bodies.get(skey, "") or EMPTY_SECTION_TEXT)
        parts.append("")
    return "\n".join(parts)


def write_bitacora_atomic(ticket_code: str, content: str) -> str:
    target_dir: Path = settings.bitacoras_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{ticket_code.upper()}.md"
    tmp_path = target_dir / f".{file_name}.tmp"
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(target_dir / file_name)
    return f"bitacoras/{file_name}"
