#!/usr/bin/env python3
"""
metadatos.py
=============
Front-matter YAML configurable para los .md que genera la skill.

Los campos del front-matter NO están fijos: los define el usuario en un
archivo de especificación JSON ("spec") que se pasa a los conversores con
--metadatos. Si no se pasa ninguno, se usa el perfil "general".

FORMATO DE LA SPEC (metadatos.json)
-----------------------------------
{
  "perfil": "general",               # opcional: base de campos (general | normativo | minimo)
  "campos": {                        # se agregan/sobrescriben sobre el perfil, en este orden
    "titulo": "auto",
    "cliente": "Acme S.A.",
    "area": "Recursos Humanos",
    "etiquetas": ["onboarding", "políticas"],
    "version": null,
    "fuente": false
  },
  "documentos": {                    # opcional: valores por archivo (nombre del PDF)
    "manual-2024.pdf": {"version": "3.1"}
  }
}

Valor de cada campo:
  "auto"      -> lo detecta el conversor (ver DETECTABLES); si no lo logra, queda pendiente
  null        -> pendiente: se escribe "TODO [REVISAR]" para completarlo a mano
  false       -> el campo se omite
  cualquier otro valor (texto, número, lista, objeto) -> se escribe tal cual

Siempre se agregan al final archivo_origen y fecha_conversion (trazabilidad),
salvo que la spec los ponga en false.

DETECTABLES ("auto")
--------------------
  Todos los PDF : titulo, autor, fecha_creacion, paginas (propiedades del PDF)
  Ruta normativa: titulo, tipo_documento, numero, anio, fecha_expedicion,
                  fecha_publicacion, descripcion, firmante, fuente
  Ruta guías    : cualquier campo puesto en el índice JSON (titulo, tipo_documento, ...)

USO DIRECTO
-----------
    python3 metadatos.py plantilla [perfil] > metadatos.json   # punto de partida para editar
    python3 metadatos.py perfiles                              # lista perfiles y sus campos
    python3 metadatos.py aplicar doc.md metadatos.json [--pdf original.pdf]
        # reescribe el front-matter de un .md ya generado (los valores
        # existentes cuentan como "detectados" para los campos "auto")
"""

import json
import os
import re
import sys
from datetime import datetime

PENDIENTE = "TODO [REVISAR]"

PERFILES = {
    "minimo": {
        "titulo": "auto",
        "tipo_documento": "auto",
        "fecha_publicacion": "auto",
    },
    "general": {
        "titulo": "auto",
        "tipo_documento": "auto",
        "autor": "auto",
        "fecha_publicacion": "auto",
        "descripcion": "auto",
        "idioma": "es",
        "etiquetas": [],
        "fuente": "auto",
    },
    "normativo": {
        "titulo": "auto",
        "tipo_documento": "auto",
        "numero": "auto",
        "anio": "auto",
        "fecha_expedicion": "auto",
        "descripcion": "auto",
        "emisor": None,
        "firmante": "auto",
        "modifica": None,
        "deroga": None,
        "jurisdiccion": None,
        "fuente": "auto",
        "etiquetas": [],
    },
}

CAMPOS_SISTEMA = ("archivo_origen", "fecha_conversion")


# ----------------------------------------------------------------------------
# Spec
# ----------------------------------------------------------------------------

def cargar_spec(ruta=None) -> dict:
    """Devuelve la spec normalizada: {"campos": {...ordenados}, "documentos": {...}}."""
    spec = {}
    if ruta:
        with open(ruta, "r", encoding="utf-8") as f:
            spec = json.load(f)
    perfil = spec.get("perfil", "general")
    if perfil not in PERFILES:
        raise ValueError(f"Perfil desconocido '{perfil}'. Opciones: {', '.join(PERFILES)}")
    campos = dict(PERFILES[perfil])
    campos.update(spec.get("campos", {}))
    return {"campos": campos, "documentos": spec.get("documentos", {})}


def _detectado(valor):
    if valor is None:
        return False
    if isinstance(valor, str) and (not valor.strip() or "TODO" in valor or "REVISAR" in valor):
        return False
    return True


def resolver(spec: dict, detectados: dict, archivo_origen: str) -> dict:
    """Combina spec + valores detectados -> dict ordenado listo para escribir."""
    campos = dict(spec["campos"])
    campos.update(spec.get("documentos", {}).get(archivo_origen, {}))
    sistema = {
        "archivo_origen": archivo_origen,
        "fecha_conversion": datetime.now().strftime("%Y-%m-%d"),
    }

    final = {}
    for campo, valor in campos.items():
        if campo in CAMPOS_SISTEMA:
            continue
        if valor is False:
            continue
        if valor == "auto":
            v = detectados.get(campo)
            final[campo] = v if _detectado(v) else PENDIENTE
        elif valor is None:
            final[campo] = PENDIENTE
        else:
            final[campo] = valor
    for campo, valor in sistema.items():
        if campos.get(campo) is not False:
            final[campo] = valor
    return final


# ----------------------------------------------------------------------------
# Detección común a cualquier PDF
# ----------------------------------------------------------------------------

def _fecha_pdf(valor):
    if isinstance(valor, bytes):
        valor = valor.decode("latin-1", "ignore")
    m = re.search(r"(\d{4})(\d{2})(\d{2})", str(valor or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def info_pdf(ruta_pdf) -> dict:
    """Propiedades del PDF (Title, Author, CreationDate) + nº de páginas."""
    try:
        import logging
        import pdfplumber
        logging.getLogger("pdfminer").setLevel(logging.ERROR)
        with pdfplumber.open(ruta_pdf) as pdf:
            meta = pdf.metadata or {}
            paginas = len(pdf.pages)
    except Exception:
        return {}

    def txt(k):
        v = meta.get(k)
        if isinstance(v, bytes):
            v = v.decode("utf-8", "ignore")
        v = (v or "").strip()
        # Títulos genéricos que dejan los editores no sirven como título real.
        if not v or v.lower() in ("untitled", "sin título", "microsoft word") or v.lower().endswith((".doc", ".docx", ".indd")):
            return None
        return v

    fecha = _fecha_pdf(meta.get("CreationDate"))
    return {
        "titulo": txt("Title"),
        "autor": txt("Author"),
        "fecha_creacion": fecha,
        "paginas": paginas,
    }


# ----------------------------------------------------------------------------
# YAML
# ----------------------------------------------------------------------------

def front_matter(valores: dict) -> str:
    """Emite YAML usando JSON para cada valor (JSON es YAML válido): comillas
    y caracteres especiales quedan bien escapados sin depender de PyYAML."""
    lineas = ["---"]
    for k, v in valores.items():
        lineas.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lineas.append("---")
    return "\n".join(lineas)


_FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def leer_front_matter(md: str) -> dict:
    m = _FM_RE.match(md)
    if not m:
        return {}
    datos = {}
    for linea in m.group(1).splitlines():
        if ":" not in linea or linea.startswith((" ", "-")):
            continue
        k, v = linea.split(":", 1)
        v = v.strip()
        try:
            datos[k.strip()] = json.loads(v)
        except Exception:
            datos[k.strip()] = v.strip('"')
    return datos


def reemplazar_front_matter(md: str, valores: dict) -> str:
    nuevo = front_matter(valores) + "\n"
    if _FM_RE.match(md):
        return _FM_RE.sub(lambda _m: nuevo, md, count=1)
    return nuevo + "\n" + md


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]
    if cmd == "perfiles":
        for nombre, campos in PERFILES.items():
            print(f"{nombre}: {', '.join(campos)}  (+ {', '.join(CAMPOS_SISTEMA)})")
    elif cmd == "plantilla":
        perfil = args[1] if len(args) > 1 else "general"
        print(json.dumps({"perfil": perfil, "campos": PERFILES[perfil], "documentos": {}},
                         ensure_ascii=False, indent=2))
    elif cmd == "aplicar" and len(args) >= 3:
        ruta_md, ruta_spec = args[1], args[2]
        ruta_pdf = args[args.index("--pdf") + 1] if "--pdf" in args else None
        with open(ruta_md, "r", encoding="utf-8") as f:
            md = f.read()
        detectados = leer_front_matter(md)
        if ruta_pdf:
            detectados = {**{k: v for k, v in info_pdf(ruta_pdf).items() if v}, **detectados}
        archivo = detectados.get("archivo_origen") or os.path.basename(ruta_pdf or ruta_md)
        valores = resolver(cargar_spec(ruta_spec), detectados, archivo)
        with open(ruta_md, "w", encoding="utf-8") as f:
            f.write(reemplazar_front_matter(md, valores))
        pendientes = sum(1 for v in valores.values() if v == PENDIENTE)
        print(f"✅ Front-matter actualizado en {ruta_md} ({len(valores)} campos, {pendientes} pendientes)")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
