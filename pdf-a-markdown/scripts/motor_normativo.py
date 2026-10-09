#!/usr/bin/env python3
"""
motor_normativo.py
===========================
Convierte normas en PDF (leyes, decretos, resoluciones, circulares con
"ARTÍCULO N") en archivos Markdown estructurados y optimizados para RAG.
Calibrado originalmente para decretos, también reconoce leyes, resoluciones
y circulares (ver TIPO_NORMA_PATTERNS en la sección 2).

QUÉ HACE
--------
1. Extrae el texto del PDF (pdfplumber) y limpia encabezados/pies de página
   repetidos (numeración de página, "Página N de M", "Hoja N de M"). El
   membrete o pie propio de un portal o publicador concreto se limpia con
   un perfil de fuente opcional (--perfil-fuente, ver PERFILES_FUENTE).
2. Detecta metadatos básicos de la norma (tipo, número, fecha,
   presidente/firmante) mediante expresiones regulares sobre el propio
   texto, buscando el tipo/número/objeto solo en la "cabecera" (los
   primeros HEADER_WINDOW_CHARS caracteres) para no confundir el
   encabezado real con una cita a otra norma dentro del articulado.
3. Reconoce la jerarquía normativa habitual en normas en español:
       LIBRO > PARTE > TÍTULO > CAPÍTULO > SECCIÓN > SUBSECCIÓN > ARTÍCULO > PARÁGRAFO
   (LIBRO/PARTE/TÍTULO son opcionales: una ley simple puede ir directo de
   TÍTULO a ARTÍCULO sin CAPÍTULO/SECCIÓN, y un decreto reglamentario
   corto puede no tener ninguno de los tres niveles superiores) y la
   traduce a niveles de encabezado Markdown (H1-H4, ver HEADING_LEVEL).
4. Genera un "breadcrumb" (**Ruta:** ...) al inicio de cada bloque, para que
   ningún fragmento pierda el contexto jerárquico cuando el splitter de tu
   pipeline de RAG lo separe del resto del documento.
5. Envuelve cada unidad semántica (normalmente un artículo, o un artículo muy
   largo dividido en sub-bloques temáticos) en marcas de chunk:
       <!-- CHUNK id="..." ruta="..." -->
       ...
       <!-- /CHUNK -->
   Estas marcas NUNCA parten un artículo o parágrafo a la mitad.
6. Escribe un front-matter YAML con los metadatos detectados y campos
   pendientes marcados como TODO para revisión manual rápida.

QUÉ NO HACE (y por qué)
------------------------
- No usa un LLM ni depende de internet: es 100% determinístico (regex +
  reglas), pensado para lotes grandes de decretos con estructura similar.
- No adivina campos jurídicos que no están en el texto (p. ej. si el decreto
  deroga o modifica otra norma de forma implícita). Esos casos quedan
  marcados con "[REVISAR]" para que un humano los complete en segundos.
- Si el PDF es escaneado (imagen, sin texto seleccionable), este script no
  hará OCR. Ver la sección "Documentos escaneados" más abajo.

USO
---
    python3 motor_normativo.py entrada.pdf salida.md
    python3 motor_normativo.py entrada.pdf                 # usa el mismo nombre .md
    python3 motor_normativo.py carpeta_pdfs/ carpeta_md/   # modo lote (carpeta -> carpeta)
    ... --metadatos metadatos.json                         # campos del front-matter (ver metadatos.py)
    ... --perfil-fuente perfil.json                        # reglas de un portal/publicador (repetible)
    ... --sin-chunks                                       # sin marcas CHUNK ni **Ruta:** (solo conversión)

Requisitos: pip install pdfplumber --break-system-packages
"""

import html
import re
import sys
import os
import glob
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metadatos  # noqa: E402  front-matter configurable por el usuario

# ----------------------------------------------------------------------------
# 1. EXTRACCIÓN Y LIMPIEZA DE TEXTO
# ----------------------------------------------------------------------------

FOOTER_HEADER_PATTERNS = [
    r"^\s*\d+\s*$",  # números de página sueltos
    # Pie de página de resoluciones con paginación "Hoja N de M" ("RESOLUCIÓN
    # NÚMERO 123 DE 02 ABR 2024 Hoja N de M"). Se ancla en "Hoja N de M"
    # para no confundirse con una mención real de "Resolución número..."
    # dentro del cuerpo. Sin filtrarlo, contamina el cuerpo de casi todos
    # los chunks y se cuela en la heurística de unión de nombres de
    # encabezado envueltos en varias líneas (ver esa heurística más abajo),
    # generando encabezados de LIBRO con el pie pegado al nombre real.
    r"RESOLUCI[ÓO]N\s+N[ÚU]MERO\s+\d+\s+DE\s+.*Hoja\s+\d+\s+de\s+\d+",
    # Variante del mismo pie sola en su línea, sin "Hoja": "RESOLUCIÓN
    # NÚMERO 123 DE 02 ABR 2024" (suele ir precedida de "Página N de M").
    # Anclada de extremo a extremo ($) para no confundirse con una mención
    # real de la resolución dentro de una oración del cuerpo (esas nunca
    # terminan justo ahí, siguen con más texto en la misma línea).
    r"^RESOLUCI[ÓO]N\s+N[ÚU]MERO\s+\d+\s+DE\s+\d{1,2}\s+\S+\s+\d{4}\s*$",
    # Pie "Página N de M" genérico (formato común en resoluciones y
    # decretos).
    r"^P[áa]gina\s+\d+\s+de\s+\d+\s*$",
]

# Reglas propias de una fuente concreta (membrete o pie de un portal, título
# de un documento repetido como encabezado de página, nota legal del
# publicador...). No viven en el código para que el motor no dependa de
# ningún portal ni entidad: se cargan desde perfiles JSON con
# --perfil-fuente (ver SKILL_DIR/references/perfiles-fuente.md). Cada perfil
# cargado se añade a esta lista con sus regex ya compiladas.
PERFILES_FUENTE = []


def cargar_perfil_fuente(ruta: str) -> dict:
    """Carga un perfil de fuente (JSON) y lo activa para clean_text,
    detect_metadata y build_markdown."""
    import json

    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    perfil = {
        "nombre": datos.get("nombre") or os.path.splitext(os.path.basename(ruta))[0],
        "lineas_ruido": [re.compile(r, re.IGNORECASE) for r in datos.get("lineas_ruido", [])],
        "bloques_ruido": [re.compile(r) for r in datos.get("bloques_ruido", [])],
        "deteccion": re.compile(datos["deteccion"], re.IGNORECASE) if datos.get("deteccion") else None,
        "fuente": datos.get("fuente"),
        "nota_final": datos.get("nota_final"),
    }
    PERFILES_FUENTE.append(perfil)
    return perfil


# Marcas pensadas para un pipeline de RAG: <!-- CHUNK ... --> / <!-- /CHUNK -->
# alrededor de cada bloque y la línea "**Ruta:** ..." (breadcrumb). Con
# --sin-chunks se omiten en el .md final y queda una conversión limpia para
# leer (front-matter + encabezados + párrafos rearmados, ver
# _rearmar_parrafos).
MARCAS_RAG = True
_MARCA_RAG_RE = re.compile(r"^(?:<!-- /?CHUNK\b.*-->|\*\*Ruta:\*\*.*)\n", re.MULTILINE)


def extraer_opciones_salida(args: list) -> list:
    """Quita "--sin-chunks" de args (desactiva MARCAS_RAG) y devuelve el resto."""
    global MARCAS_RAG
    if "--sin-chunks" in args:
        MARCAS_RAG = False
        args = [a for a in args if a != "--sin-chunks"]
    return args


# Líneas que nunca se unen con la anterior ni con la siguiente: encabezados,
# ítems de lista, tablas, citas, separadores y comentarios.
_LINEA_ESTRUCTURA_RE = re.compile(
    r"^(?:#|[-*+•]\s|\d+[.)°º]\s|\(?[a-zA-Z0-9]{1,3}\)\s|\||>|---|<!--|PAR[ÁA]GRAFO|ART[ÍI]CULO)"
)


def _rearmar_parrafos(cuerpo: str) -> str:
    """Deshace los saltos de línea del PDF: une palabras cortadas con guion
    al final de línea ("pala-" + "bra" -> "palabra") y junta en un párrafo
    las líneas de una misma oración (la línea no termina en puntuación de
    cierre y la siguiente empieza en minúscula). Conservador: nunca toca
    encabezados, listas ni tablas, y no adivina cuando la siguiente línea
    empieza en mayúscula."""
    salida = []
    for linea in cuerpo.split("\n"):
        prev = salida[-1] if salida else ""
        if (
            prev and linea[:1].islower()
            and not _LINEA_ESTRUCTURA_RE.match(prev)
            and not _LINEA_ESTRUCTURA_RE.match(linea)
        ):
            if re.search(r"[a-záéíóúñü]-$", prev):
                salida[-1] = prev[:-1] + linea
                continue
            if not re.search(r"[.:;!?»”\"]$", prev):
                salida[-1] = f"{prev} {linea}"
                continue
        salida.append(linea)
    return "\n".join(salida)


def finalizar_markdown(md: str) -> str:
    """Aplica las opciones de salida al .md ya armado, justo antes de escribirlo."""
    if MARCAS_RAG:
        return md
    md = _MARCA_RAG_RE.sub("", md)
    # El front-matter (--- ... ---) no se toca.
    m = re.match(r"(---\n.*?\n---\n)(.*)", md, re.DOTALL)
    cabecera, cuerpo = (m.group(1), m.group(2)) if m else ("", md)
    return cabecera + re.sub(r"\n{3,}", "\n\n", _rearmar_parrafos(cuerpo))


def extraer_perfiles_fuente(args: list) -> list:
    """Quita de args cada "--perfil-fuente RUTA" (repetible), carga esos
    perfiles y devuelve el resto de argumentos."""
    resto = []
    i = 0
    while i < len(args):
        if args[i] == "--perfil-fuente" and i + 1 < len(args):
            cargar_perfil_fuente(args[i + 1])
            i += 2
            continue
        resto.append(args[i])
        i += 1
    return resto


def extract_pdf_text(pdf_path: str) -> str:
    """Extrae texto de todas las páginas de un PDF usando pdfplumber."""
    import pdfplumber

    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
    return "\n".join(pages_text)


def clean_text(raw_text: str) -> str:
    """Elimina encabezados/pies de página repetidos y normaliza saltos de línea."""
    # Algunos PDF (probablemente impresos desde una página HTML) conservan
    # entidades sin decodificar en el texto extraído ("Art&iacuteculo" en vez
    # de "Artículo"), incluso sin el ";" final — html.unescape() de Python ya
    # resuelve esa forma abreviada. No tiene efecto sobre texto que no trae
    # entidades.
    raw_text = html.unescape(raw_text)
    # Restos de anclas HTML rotas en la extracción (ej. 'ARTÍCULO
    # -">2.2.1.4.8.1.-', 'PARÁGRAFO -.p1">1.-'): el fragmento '-...">'
    # sobrevive de un anchor original (probablemente <a name="...">) justo
    # antes del número, y rompe el reconocimiento de ARTÍCULO/PARÁGRAFO en
    # HIERARCHY_PATTERNS — visto en un decreto compilatorio extenso (se
    # perdían dos secciones completas, no solo el encabezado, porque
    # NINGÚN artículo ahí llegaba a reconocerse).
    raw_text = re.sub(r'-\.?p?\d*">', "", raw_text)
    # Ruido de varias líneas propio de una fuente (p. ej. un pie de página
    # que corta el título del documento y deja el resto en la línea de
    # abajo): se elimina antes de trocear por línea, cuando hay un perfil
    # de fuente cargado que lo describe.
    for perfil in PERFILES_FUENTE:
        for patron in perfil["bloques_ruido"]:
            raw_text = patron.sub("\n", raw_text)
    lines = raw_text.split("\n")
    cleaned = []
    footer_re = re.compile("|".join(FOOTER_HEADER_PATTERNS), re.IGNORECASE)
    ruido_perfiles = [p for perfil in PERFILES_FUENTE for p in perfil["lineas_ruido"]]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if footer_re.match(stripped):
            continue
        if any(p.match(stripped) for p in ruido_perfiles):
            continue
        cleaned.append(stripped)
    text = "\n".join(cleaned)
    # Unir párrafos que quedaron partidos por saltos de línea del PDF
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text


# ----------------------------------------------------------------------------
# 2. DETECCIÓN DE METADATOS
# ----------------------------------------------------------------------------

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}

# Cuántos caracteres iniciales del texto se consideran "cabecera" (donde
# vive el encabezado real de la norma: "DECRETO N DE AÑO", "LEY N DE AÑO",
# etc., seguido del objeto "Por el/la cual..."). Buscar el tipo/número/objeto
# SOLO en esta ventana evita el bug detectado al procesar leyes largas: si
# se busca en el documento completo, una cita interna a otra norma dentro
# del articulado ("...modificado por el Decreto 200 de 2025...") puede
# matchear antes que el encabezado real y contaminar
# titulo/objeto de TODOS los chunks con datos de una norma equivocada.
HEADER_WINDOW_CHARS = 2500

# Cada tipo de norma usa una palabra clave distinta en su
# encabezado. tipo_norma queda fijo según cuál coincidió (antes quedaba
# hardcodeado en "Decreto" aunque el documento fuera una ley o resolución).
# El texto entre la palabra clave y el número puede traer basura de
# extracción del PDF (ej. "RESOLUCIÓN NÚMERO O 011 1234(cid:9) DE 2021",
# donde el número real es 1234 y "(cid:9)" es un glifo de tabulación que
# pdfplumber no logró decodificar): [^\n]*? salta el texto intermedio sin
# cruzar de línea, y el "(cid:N)" opcional entre el número y "DE" evita que
# ese artefacto rompa el match justo antes del año.
# Todos los sub-patrones usan grupos con NOMBRE ("numero", "anio", y
# opcionalmente "mes"/"dia") en vez de posición: así detect_metadata puede
# leerlos igual sin importar en qué orden aparecen en el texto fuente (el
# formato abreviado trae día-mes-año, el de fecha completa trae mes-día-año).
_NUM_DE_ANIO = r"(?P<numero>\d+)\s*(?:\(cid:\d+\)\s*)?DE\s+(?P<anio>\d{4})"

# Normas antiguas no usan "NÚMERO ... DE <año>" sino la fecha completa de
# expedición: "RESOLUCIÓN 1016 DE MARZO 31 DE 1989". Ahí el patrón
# _NUM_DE_ANIO suelto es ambiguo: como "31 DE 1989" (día + año de la fecha)
# también cumple la forma "(\d+) DE (\d{4})", sin este patrón más específico
# el matching se "cuela" por el día en vez del número real de la norma. Se
# prueba ANTES que el patrón suelto (mismo tipo, mismo punto de inicio del
# match) para que gane por orden cuando ambos aplican — ver desempate por
# m.start() en detect_metadata().
_MESES_ALT = "|".join(MESES.keys())
_NUM_DE_FECHA_COMPLETA = (
    rf"(?P<numero>\d+)\s+DE\s+(?P<mes>{_MESES_ALT})\s+(?P<dia>\d{{1,2}})\s+DE\s+(?P<anio>\d{{4}})"
)

# Formato de algunos emisores: "RESOLUCIÓN NÚMERO\n(01652 )\n19 NOV 2019", sin
# ningún "DE" entre el número y la fecha, con el mes abreviado. Sin este
# patrón, el matching suelto de _NUM_DE_ANIO no encuentra nada válido cerca
# del encabezado real y termina "colándose" por una cita a otra norma más
# abajo en el texto.
MESES_ABREV = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}
_MESES_ABREV_ALT = "|".join(MESES_ABREV.keys())
_NUM_PARENS_FECHA_ABREV = (
    rf"N[ÚU]MERO\s*\(?\s*(?P<numero>\d+)\s*\)?\s+(?P<dia>\d{{1,2}})\s+"
    rf"(?P<mes>{_MESES_ABREV_ALT})\.?\s+(?P<anio>\d{{4}})"
)

TIPO_NORMA_PATTERNS = [
    ("Decreto", re.compile(rf"DECRETO\s+{_NUM_DE_FECHA_COMPLETA}", re.IGNORECASE)),
    ("Decreto", re.compile(rf"DECRETO\s+{_NUM_PARENS_FECHA_ABREV}", re.IGNORECASE)),
    ("Decreto", re.compile(rf"DECRETO[^\n]*?{_NUM_DE_ANIO}", re.IGNORECASE)),
    ("Ley", re.compile(rf"LEY\s+{_NUM_DE_FECHA_COMPLETA}", re.IGNORECASE)),
    ("Ley", re.compile(rf"LEY\s+{_NUM_PARENS_FECHA_ABREV}", re.IGNORECASE)),
    ("Ley", re.compile(rf"LEY[^\n]*?{_NUM_DE_ANIO}", re.IGNORECASE)),
    ("Resolución", re.compile(rf"RESOLUCI[ÓO]N\s+{_NUM_DE_FECHA_COMPLETA}", re.IGNORECASE)),
    ("Resolución", re.compile(rf"RESOLUCI[ÓO]N\s+{_NUM_PARENS_FECHA_ABREV}", re.IGNORECASE)),
    ("Resolución", re.compile(rf"RESOLUCI[ÓO]N[^\n]*?{_NUM_DE_ANIO}", re.IGNORECASE)),
    ("Circular", re.compile(rf"CIRCULAR\s+{_NUM_DE_FECHA_COMPLETA}", re.IGNORECASE)),
    ("Circular", re.compile(rf"CIRCULAR\s+{_NUM_PARENS_FECHA_ABREV}", re.IGNORECASE)),
    ("Circular", re.compile(rf"CIRCULAR[^\n]*?{_NUM_DE_ANIO}", re.IGNORECASE)),
]


def detect_metadata(text: str) -> dict:
    meta = {
        "titulo": "TODO [REVISAR]",
        "tipo_norma": "TODO [REVISAR]",
        "numero": "TODO [REVISAR]",
        "anio": "TODO [REVISAR]",
        "fecha_expedicion": "TODO [REVISAR]",
        "objeto": "TODO [REVISAR]",
        "firmante": "TODO [REVISAR]",
        "fuente": "TODO [REVISAR]",
    }

    # La fuente solo se rellena si un perfil de fuente cargado la reconoce
    # en el propio texto (en otro caso queda pendiente o la define el
    # usuario en metadatos.json).
    for perfil in PERFILES_FUENTE:
        if perfil["deteccion"] and perfil["deteccion"].search(text):
            if perfil["fuente"]:
                meta["fuente"] = perfil["fuente"]
            if perfil["nota_final"]:
                meta["nota_fuente"] = perfil["nota_final"]
            break

    cabecera = text[:HEADER_WINDOW_CHARS]

    # Tipo de norma + número y año: "DECRETO 100 DE 2017", "LEY 200 DE
    # 2012", "RESOLUCIÓN 300 DE 2021"... Se toma el match que aparece MÁS
    # TEMPRANO en la cabecera (no el primero de la lista): el encabezado
    # real siempre es lo primero que aparece en el documento, antes que
    # cualquier cita a otra norma dentro del "considerando" o el articulado.
    mejor_match, mejor_tipo = None, None
    for tipo, patron in TIPO_NORMA_PATTERNS:
        m = patron.search(cabecera)
        if m and (mejor_match is None or m.start() < mejor_match.start()):
            mejor_match, mejor_tipo = m, tipo
    if mejor_match:
        meta["tipo_norma"] = mejor_tipo
        grupos = mejor_match.groupdict()
        numero, anio_txt = grupos["numero"], grupos["anio"]
        meta["numero"] = numero
        meta["anio"] = int(anio_txt)
        meta["titulo"] = f"{mejor_tipo} {numero} de {anio_txt}"
        # Los patrones de fecha completa (día + mes, en letras o abreviado)
        # traen suficiente para fecha_expedicion, sin dejarla en TODO.
        mes_txt, dia = grupos.get("mes"), grupos.get("dia")
        if mes_txt and dia:
            mes_num = MESES.get(mes_txt.lower()) or MESES_ABREV.get(mes_txt.lower())
            if mes_num:
                meta["fecha_expedicion"] = f"{anio_txt}-{mes_num:02d}-{int(dia):02d}"

    # Objeto: "Por medio del cual ...", "Por el cual ..." o "Por la cual ..."
    # (leyes y resoluciones suelen usar "la cual" por concordancia de género).
    # El objeto real suele envolver a varias líneas del PDF (ej. "...y
    # se\nadiciona el Capítulo 7... del Decreto 500 del 2015..."): cortar en
    # el primer "\n" (como antes) trunca la
    # frase a mitad de camino, perdiendo justo la parte más importante
    # (qué otra norma adiciona/modifica). Por eso se usa DOTALL y se corta
    # recién en el siguiente marcador que arranca la sección de firmantes/
    # considerandos, no en el primer salto de línea del PDF.
    m = re.search(
        r"Por\s+(?:medio\s+del\s+cual|medio\s+de\s+la\s+cual|el\s+cual|la\s+cual)\s+.{1,500}?"
        r"(?=\s*(?:(?:EL|LA|LOS|LAS)\s+(?:PRESIDENTE|MINISTR\w*|DIRECTOR\w*|GERENTE\w*|CONGRESO)\b"
        r"|CONSIDERANDO\b|DECRETA\b|RESUELVE\b|\n\s*\n))",
        cabecera, re.IGNORECASE | re.DOTALL,
    )
    if m:
        objeto_txt = re.sub(r"\s+", " ", m.group(0)).strip()
        # Comillas de apertura del título citado tal cual en el PDF (ej.
        # '"Por el cual...ambientales"') pueden quedar
        # con la de cierre pegada justo antes del marcador de corte.
        meta["objeto"] = objeto_txt.strip("\"'“”’.,").strip()

    # Fecha textual: "(Diciembre 20)" + "20 días del mes de diciembre de 2017"
    m = re.search(
        r"a\s+los\s+(\d{1,2})\s+d[ií]as\s+del\s+mes\s+de\s+(\w+)\s+de\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        dia, mes_txt, anio_txt = m.group(1), m.group(2).lower(), m.group(3)
        mes_num = MESES.get(mes_txt)
        if mes_num:
            meta["fecha_expedicion"] = f"{anio_txt}-{mes_num:02d}-{int(dia):02d}"

    # Firmante (presidente de la república, en decretos y leyes): "EL
    # PRESIDENTE DE LA REPÚBLICA (FDO.) NOMBRE", el orden típico de un
    # decreto.
    m = re.search(r"EL PRESIDENTE DE LA REP[ÚU]BLICA\s*\n?\(?FDO\.?\)?\s*([A-ZÁÉÍÓÚÑ .]+)", text)
    if m:
        meta["firmante"] = m.group(1).strip().title()
    else:
        # Varias leyes invierten el orden y omiten
        # "(FDO.)": "NOMBRE.\nEL PRESIDENTE DE LA REPÚBLICA,\nNOMBRE DEL
        # MINISTRO.\nEL MINISTRO DE...,". El nombre en mayúscula sostenida
        # queda en la línea INMEDIATAMENTE ANTERIOR al título del cargo, no
        # después. [^\n]+ para el nombre (no solo may/espacios): a veces
        # trae un punto final pegado ("TRUJILLO.") que se recorta abajo.
        m = re.search(
            r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .]+?)\.?\s*\n\s*EL PRESIDENTE DE LA REP[ÚU]BLICA\b",
            text,
        )
        if m:
            meta["firmante"] = m.group(1).strip().title()

    # Decreto destino: muchos decretos NO tienen artículos propios más
    # allá del que ordena adicionar/modificar un Decreto Único
    # Reglamentario (DUR) — el resto de "artículos" que detecta el parser
    # (numerados "2.2.4.12.1", "2.2.4.12.2"...) en realidad pasan a
    # integrar ESE decreto compilado, no el que se está procesando (p. ej.
    # un decreto cuyo único artículo propio es el 1, que dice "Adiciónese
    # el Capítulo 12... del Decreto 500 de 2015"; en la práctica,
    # "2.2.4.12.3" siempre se cita como artículo del Decreto 500, nunca
    # del decreto que lo adicionó). Se detecta ese decreto destino a partir del
    # objeto para poder anotarlo en la ruta de esos artículos (ver
    # build_ruta en parse_document) y no perder esa referencia al
    # fragmentar en chunks — si no se anota, una búsqueda por "Decreto
    # 500 de 2015 artículo 2.2.4.12.3" no encontraría el chunk.
    # Entre "Decreto" y su número puede venir una descripción ("Decreto
    # Único 500 de 2015", "Decreto Único Reglamentario del Sector..."). A
    # diferencia de TIPO_NORMA_PATTERNS (que busca en toda
    # la cabecera con muchas oraciones y por eso evita cruzar un punto),
    # esto busca solo dentro de meta["objeto"] — ya una única oración
    # limpia — así que no hace falta esa restricción; de hecho, un
    # artículo destino tipo "2.3.1.2.2.4.3" trae puntos propios que la
    # rompían.
    m = re.search(
        r"(?:adicion|modific|sustituy|derog)[a-zñ]*.*?\bDecreto\b.*?(\d+)\s+del?\s+(\d{4})",
        meta.get("objeto", ""), re.IGNORECASE,
    )
    if m:
        meta["decreto_destino"] = f"Decreto {m.group(1)} de {m.group(2)}"

    return meta


# ----------------------------------------------------------------------------
# 3. PARSEO DE JERARQUÍA NORMATIVA
# ----------------------------------------------------------------------------

# Algunas normas antiguas numeran sus artículos
# en letras en vez de dígitos: ordinales del 1 al 10 ("Artículo primero.")
# y luego cardinales del 11 en adelante ("Artículo once.", "Artículo
# dieciocho."), como se publicaban en algunas gacetas oficiales.
ORDINALES_ARTICULO = {
    "primero": "1", "primera": "1",
    "segundo": "2", "segunda": "2",
    "tercero": "3", "tercera": "3",
    "cuarto": "4", "cuarta": "4",
    "quinto": "5", "quinta": "5",
    "sexto": "6", "sexta": "6",
    "septimo": "7", "séptimo": "7", "setimo": "7", "sétimo": "7",
    "octavo": "8", "octava": "8",
    "noveno": "9", "novena": "9",
    "decimo": "10", "décimo": "10", "decima": "10", "décima": "10",
    "once": "11", "doce": "12", "trece": "13", "catorce": "14", "quince": "15",
    "dieciseis": "16", "dieciséis": "16",
    "diecisiete": "17", "dieciocho": "18", "diecinueve": "19",
    "veinte": "20", "veintiuno": "21", "veintiun": "21", "veintiún": "21",
    "veintidos": "22", "veintidós": "22", "veintitres": "23", "veintitrés": "23",
    "veinticuatro": "24", "veinticinco": "25",
    "veintiseis": "26", "veintiséis": "26", "veintisiete": "27",
    "veintiocho": "28", "veintinueve": "29", "treinta": "30",
}
_ORDINALES_ALT = "|".join(
    re.escape(w) for w in sorted(ORDINALES_ARTICULO, key=len, reverse=True)
)

# Algunas portadillas de TÍTULO vienen con cada letra separada por un espacio
# ("T I T U L O I I"), un efecto tipográfico de énfasis que pdfplumber extrae
# literal — visto en una ley donde solo algunos Títulos vienen así y el resto
# del mismo documento está en formato normal. Sin normalizar esto antes de
# HIERARCHY_PATTERNS, la línea no matchea como TÍTULO y queda pegada como
# texto suelto al final del artículo anterior, y todo el contenido que sigue
# hereda la ruta del TÍTULO anterior hasta el próximo encabezado que sí
# matchee.
_TITULO_ESPACIADO_RE = re.compile(
    r"^(?:t\s+[ií]\s+t\s+u\s+l\s+o)\s+((?:[ivxlc]\s*)+)\.?\s*$",
    re.IGNORECASE,
)


def _normalizar_titulo_espaciado(line: str) -> str:
    m = _TITULO_ESPACIADO_RE.match(line.strip())
    if not m:
        return line
    numero = re.sub(r"\s+", "", m.group(1)).upper()
    return f"TÍTULO {numero}"


# Cada patrón captura el tipo de bloque y su título/número.
# El "[\"'“]?" inicial tolera una comilla suelta que a veces deja la
# extracción del PDF pegada antes de "CAPÍTULO"/"SECCIÓN"/"SUBSECCIÓN" (ej.
# '"CAPÍTULO 12', o '"SECCIÓN 10' cuando un decreto posterior sustituye la
# sección y el PDF cita el texto sustituido entre comillas); sin esto la
# línea completa no matchea y el nivel entero se pierde (queda como texto
# suelto dentro del nivel anterior, con su ruta y sus encabezados "#" mal
# calculados para todos los artículos que le siguen).
HIERARCHY_PATTERNS = [
    # LIBRO/PARTE/TÍTULO — mismo diseño (y mismas razones) que los patrones de
    # CAPITULO más abajo: variante con sufijo de letra primero (para que
    # "(\d+)" no se coma la letra del sufijo y la deje suelta como si fuera el
    # nombre en la misma línea), luego dígito/romano solo, luego ordinal en
    # palabra. Se prueban ANTES que CAPITULO/SECCION porque son niveles
    # superiores en la jerarquía y no hay ambigüedad de palabra clave entre
    # ellos. (?-i:LIBRO) fuerza la palabra completa en mayúscula real (no
    # basta con que el resto del patrón sea case-insensitive): sin esto, una
    # cita cruzada de otra norma en minúscula sostenida dentro de un párrafo
    # que el PDF cortó justo ahí ("...del título 1, libro 2, del Decreto...")
    # podría abrir un LIBRO/TÍTULO falso — visto ya con "sección" en minúscula
    # para el patrón de SECCION (ver su comentario más abajo). Para LIBRO
    # específicamente hace falta proteger la palabra ENTERA (no solo la
    # primera letra, a diferencia de PARTE/TÍTULO más abajo): "Libro 3." en
    # mayúscula-de-inicio-de-oración (no minúscula sostenida) es una cita
    # cruzada real y común dentro del propio texto ("...ver Libro 3. En el
    # caso que..."), y con solo la "L" protegida igual calzaba como encabezado
    # falso — visto dos veces en un reglamento técnico extenso, generando un
    # LIBRO 3 falso que se comía el resto del documento hasta el LIBRO 3 real
    # páginas después. (?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)? al final (igual que
    # SECCIÓN/SUBSECCIÓN más abajo): algunos reglamentos técnicos traen el
    # nombre en la MISMA línea que el número, separado por raya ("TÍTULO 1 –
    # OBJETO", "CAPÍTULO 1 – REQUERIMIENTOS GENERALES..."), a diferencia de la
    # mayoría de normas, donde LIBRO/PARTE/TÍTULO/CAPÍTULO traen el nombre en
    # la línea siguiente. Sin este grupo, esas líneas con texto después del
    # número no calzaban con el `$` final del patrón original y NINGÚN
    # Título/Capítulo del documento se reconocía: los 589 artículos quedaban
    # planos, colgados directo de su LIBRO, sin la subestructura
    # Título/Capítulo/Sección real.
    ("LIBRO", re.compile(r"^[\"'“]?\s*(?-i:LIBRO)\s+(\d+\s?(?-i:[A-Zª]))\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("LIBRO", re.compile(r"^[\"'“]?\s*(?-i:LIBRO)\s+([\dIVXLC]+)\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("LIBRO", re.compile(rf"^[\"'“]?\s*(?-i:LIBRO)\s+({_ORDINALES_ALT})\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("PARTE", re.compile(r"^[\"'“]?\s*(?-i:P)ARTE\s+(\d+\s?(?-i:[A-Zª]))\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("PARTE", re.compile(r"^[\"'“]?\s*(?-i:P)ARTE\s+([\dIVXLC]+)\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("PARTE", re.compile(rf"^[\"'“]?\s*(?-i:P)ARTE\s+({_ORDINALES_ALT})\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("TITULO", re.compile(r"^[\"'“]?\s*(?-i:T)[ÍI]TULO\s+(\d+\s?(?-i:[A-Zª]))\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("TITULO", re.compile(r"^[\"'“]?\s*(?-i:T)[ÍI]TULO\s+([\dIVXLC]+)\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("TITULO", re.compile(rf"^[\"'“]?\s*(?-i:T)[ÍI]TULO\s+({_ORDINALES_ALT})\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    # \.?\s*$ (no solo \s*$): algunas SECCIÓN/CAPÍTULO del PDF traen un punto
    # final ("SECCIÓN 2."), y sin tolerarlo la línea completa no matcheaba
    # nada — el parser seguía apilando el contenido bajo la sección anterior
    # en vez de abrir una nueva (caso real: secciones 2/4/5 de un capítulo
    # quedaban fusionadas con la 1/3/3). Igual que las SECCIÓN/SUBSECCIÓN de
    # más abajo: capítulos insertados entre dos existentes traen sufijo de
    # letra ("CAPÍTULO 3A", "CAPÍTULO 5ª" — este último con el ordinal "ª", no
    # la letra "A" — ambos vistos en un mismo decreto compilatorio). Con o sin
    # espacio antes de la letra, a diferencia de SECCIÓN que siempre trae
    # espacio. \.? tras CAPITULO/CAPÍTULO (antes del \s+): algunos portales de
    # normas renderizan capítulos como "CAPITULO. II" (punto pegado, antes del
    # espacio y el numeral) en vez de "CAPÍTULO II" — caso real: una ley con
    # los Capítulos II a VII así. Sin el punto opcional, esas líneas no
    # calzaban ningún patrón de CAPITULO y quedaban como texto de cuerpo:
    # todos los artículos de esos capítulos (la mayoría del documento)
    # quedaban colgados bajo el Capítulo I, sin ningún error visible.
    # (?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)? final: mismo motivo que
    # LIBRO/PARTE/TÍTULO arriba — nombre en la misma línea, separado por raya
    # ("CAPÍTULO 1 – REQUERIMIENTOS GENERALES...").
    ("CAPITULO", re.compile(r"^[\"'“]?\s*(?-i:C)AP[ÍI]TULO\.?\s+(\d+\s?(?-i:[A-Zª]))\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("CAPITULO", re.compile(r"^[\"'“]?\s*(?-i:C)AP[ÍI]TULO\.?\s+([\dIVXLC]+)\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    # Algunos capítulos insertados por decretos posteriores se numeran con
    # el ordinal en palabra en vez de dígito o romano ("CAPÍTULO PRIMERO",
    # "CAPÍTULO SEGUNDO"..., p. ej. en un Título adicionado por un decreto
    # posterior). Sin este patrón, esas líneas no matcheaban
    # ningún CAPITULO y el capítulo/artículos que seguían quedaban colgados
    # del último Capítulo numérico visto páginas antes (con su ruta y
    # encabezados apuntando al capítulo equivocado).
    ("CAPITULO", re.compile(rf"^[\"'“]?\s*(?-i:C)AP[ÍI]TULO\.?\s+({_ORDINALES_ALT})\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    # El número puede traer un punto final suelto ("SECCION 1.") y el título
    # puede venir en la misma línea ("SECCIÓN 1 DISPOSICIONES GENERALES") en
    # vez de en la línea siguiente; si no se contemplan ambas formas, la
    # sección queda como texto suelto sin encabezado "###". Secciones
    # "insertadas" entre dos ya existentes se numeran con una letra sufijo
    # ("SECCIÓN 3 A", que va entre la Sección 3 y la Sección 4 originales,
    # insertada por un decreto posterior). Se prueba ANTES que el patrón
    # solo-dígitos: si no, "(\d+)" captura nada más "3" y dejaba la "A" suelta
    # como si fuera el título en la misma línea, perdiendo el nombre real dos
    # líneas más abajo. (?-i:[A-Z]) fuerza mayúscula sin importar el
    # IGNORECASE del resto del patrón: el sufijo real siempre es mayúscula,
    # nunca hay que confundirlo con una palabra en minúscula pegada al número.
    # (?-i:S)ECCIÓN (no solo el sufijo de letra): sin esto, una referencia
    # cruzada normal en minúscula dentro de un párrafo ("...previstas en
    # la\nsección 18 y 19 de este capítulo.") coincide igual si el PDF cortó
    # la línea justo ahí, abriendo una "sección" falsa y atribuyendo mal los
    # artículos reales que siguen (visto en un decreto compilatorio extenso).
    # (?-i:[A-ZÁÉÍÓÚÑ]) en el grupo de nombre en línea (no solo [A-ZÁÉÍÓÚÑ] a
    # secas): bug real que pasó desapercibido desde que se agregó este grupo —
    # sin el (?-i:...), la clase de caracteres queda bajo el IGNORECASE global
    # del patrón y termina aceptando minúsculas también, exactamente lo que
    # este chequeo de "debe empezar en mayúscula" pretendía impedir. Se
    # detectó al extender LIBRO/PARTE/ TÍTULO/CAPÍTULO con este mismo grupo
    # (ver más arriba) y encontrar que un decreto generaba un "TÍTULO" falso a
    # partir de "Título Vill de la Ley 100 de 1993..." (cita cruzada en
    # minúscula sostenida que el PDF cortó justo después de "Vill", un numeral
    # romano corrupto por OCR/extracción) — el grupo de nombre, sin protección
    # real, capturó "de la Ley 100..." completo como si fuera el nombre del
    # título.
    ("SECCION", re.compile(r"^[\"'“]?\s*(?-i:S)ECCI[ÓO]N\s+(\d+\s?(?-i:[A-Zª]))\s*\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("SECCION", re.compile(r"^[\"'“]?\s*(?-i:S)ECCI[ÓO]N\s+(\d+)\s*\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    # "SESIÓN N" (sin la segunda "C"): error tipográfico real visto en un
    # portal de normas ("SESIÓN 15" en vez de "SECCIÓN 15"). Sin esto la línea
    # no calza ningún patrón y cae como texto de cuerpo: la pila de jerarquía
    # nunca avanza a la sección nueva y los artículos siguientes quedan mal
    # anidados bajo la sección anterior, sin ningún error visible. Anclado
    # igual de estricto que los patrones de SECCION de arriba (línea completa)
    # para no confundir un uso legítimo de "sesión" (reunión) que no sea en
    # realidad un encabezado de este tipo.
    ("SECCION", re.compile(r"^[\"'“]?\s*(?-i:S)ESI[ÓO]N\s+(\d+)\s*\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("SUBSECCION", re.compile(r"^[\"'“]?\s*(?-i:S)UBSECCI[ÓO]N\s+(\d+\s?(?-i:[A-Zª]))\s*\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    ("SUBSECCION", re.compile(r"^[\"'“]?\s*(?-i:S)UBSECCI[ÓO]N\s+(\d+)\s*\.?\s*(?:[–-]\s*)?((?-i:[A-ZÁÉÍÓÚÑ]).*)?$", re.IGNORECASE)),
    (
        "ARTICULO",
        re.compile(
            # El número puede venir como "1°", "2.3.1.5.1.1.1", etc.
            # Se restringe a dígitos/puntos/° para NO devorar palabras del
            # título que sigue (bug de versiones anteriores de este script).
            # (?-i:[A-Z])? opcional entre dos tramos de puntos: artículos de
            # una sección con sufijo de letra ("Sección 3 A") se numeran
            # "2.2.3.2.3A.1" — la A es parte del número, no del título.
            r"^ART[ÍI]CULO\s+(\d+(?:\.\d+)*(?-i:[A-Zª])?(?:\.\d+)*°?)\.?\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
    (
        "ARTICULO",
        re.compile(
            # Variante SIN espacio entre ARTÍCULO y el número ("ARTÍCULO3°.",
            # "ARTÍCULO128."): el PDF a
            # veces pega ambos. Con \s+ obligatorio esa línea no matcheaba
            # nada y el artículo entero quedaba como texto suelto (huérfano
            # bajo el capítulo anterior) en vez de abrir su propio
            # encabezado. (?-i:ART[ÍI]CULO) fuerza mayúscula sostenida real
            # (a diferencia del patrón de arriba, que es case-insensitive):
            # sin esto, una cita cruzada en minúscula sostenida dentro de un
            # párrafo que el PDF envuelve justo ahí ("...conferidas por el
            # artículo16de la Ley 300 de 2021...") abriría un ARTÍCULO falso
            # — visto en dos decretos compilatorios distintos, ambos con
            # "artículoNde" (número y palabra siguiente también pegados, sin
            # espacio) como resto de una oración envuelta, no un encabezado.
            r"^(?-i:ART[ÍI]CULO)(\d+(?:\.\d+)*(?-i:[A-Zª])?(?:\.\d+)*°?)\.?\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
    (
        "ARTICULO",
        re.compile(
            rf"^ART[ÍI]CULO\s+({_ORDINALES_ALT})\.\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
]

# Nota editorial de modificación normativa (con o sin paréntesis) que a
# veces aparece pegada justo después de "CAPÍTULO N" y antes del nombre real
# del capítulo, ej. "(Capítulo Adicionado por el Art. 1 del Decreto 600 de
# 2021)" o "Capítulo 5, modificado y adicionado por el Art. 1 del Decreto
# 700 de 2021". Nunca es el nombre del capítulo, así que se descarta al
# buscar el título.
EDITORIAL_NOTE_RE = re.compile(
    r"\b(?:Adicionad[oa]|Modificad[oa]|Subrogad[oa]|Derogad[oa]|Reemplazad[oa]|Suprimid[oa])\b",
    re.IGNORECASE,
)

# Entrada de tabla de contenido/índice: texto seguido de puntos-guía
# (mínimo 3, tolerando espacios sueltos entre ellos por cómo pdfplumber
# extrae a veces los "tab leaders") y un número de página al final. Ver
# TOC_ENTRY_RE en el bucle principal de parse_document.
TOC_ENTRY_RE = re.compile(r"(?:\.\s?){3,}\s*\d+\s*$")

# Abreviaturas legales comunes cuyo punto NO debe interpretarse
# como cierre de la etiqueta/título de un ARTÍCULO — ver _fin_de_etiqueta().
# Caso real: un decreto cuyos Artículos 101-105 se publican como
# "Artículo 101. Derogado por el art. 42, Decreto 400 de 2005.
# Toda disposición administrativa..."; sin este guardia, el punto de "art."
# se toma como fin de etiqueta y el título queda truncado en "Derogado por
# el art", con "42, Decreto 400 de 2005." colándose como inicio
# del cuerpo.
_ABREVIATURAS_LEGALES = {
    "art", "arts", "núm", "num", "lit", "cap", "caps", "inc", "par", "ord", "ords",
}


def _fin_de_etiqueta(rest):
    """Índice del primer punto de `rest` que no sea el punto de cierre de una
    abreviatura legal común (art., núm., lit., cap., inc., par...), o -1 si
    no hay ninguno. Reemplaza a `rest.find(".")` en la extracción de
    etiqueta/título de ARTÍCULO."""
    inicio = 0
    while True:
        idx = rest.find(".", inicio)
        if idx == -1:
            return -1
        palabra = re.search(r"(\w+)$", rest[:idx], re.UNICODE)
        if palabra and palabra.group(1).lower() in _ABREVIATURAS_LEGALES:
            inicio = idx + 1
            continue
        return idx


# Orden jerárquico real (de mayor a menor), usado para: (a) construir el
# breadcrumb/ruta en ese orden, (b) decidir qué niveles "por debajo" de uno
# que acaba de cambiar deben olvidar su último valor emitido (para volver a
# emitir su encabezado si reaparecen, ej. "Sección 1" bajo dos Capítulos
# distintos), y (c) el heading Markdown de cada nivel vía HEADING_LEVEL.
# LIBRO y TÍTULO comparten nivel H1: ambos son encabezados "de tapa" en la
# práctica (un decreto reglamentario grande divide en LIBRO, uno mediano
# empieza directo en TÍTULO, una ley simple va directo a ARTÍCULO) y nunca
# aparecen anidados uno dentro del otro con distinto peso visual en los
# documentos reales usados para calibrar el motor (en un decreto
# compilatorio, tanto "LIBRO 2 - ..." como los "TÍTULO 9/10/11..." que le
# siguen, varios niveles más abajo en la jerarquía real, se renderizan
# como "#").
NIVEL_ORDEN = ["LIBRO", "PARTE", "TITULO", "CAPITULO", "SECCION", "SUBSECCION"]

HEADING_LEVEL = {
    "LIBRO": 1,
    "PARTE": 2,
    "TITULO": 1,
    "CAPITULO": 2,
    "SECCION": 3,
    "SUBSECCION": 4,
    "ARTICULO": 5,
}

DISPLAY_NAMES = {
    # LIBRO/PARTE/TÍTULO van en mayúscula sostenida ("LIBRO 2 - ...",
    # "TÍTULO 8 - ..."), CAPÍTULO/SECCIÓN/SUBSECCIÓN solo con inicial
    # mayúscula ("Capítulo 1 – ...", "Sección 3 – ..."): distinción real
    # de los documentos de origen, no una preferencia arbitraria de este
    # script.
    "LIBRO": "LIBRO",
    "PARTE": "PARTE",
    "TITULO": "TÍTULO",
    "CAPITULO": "Capítulo",
    "SECCION": "Sección",
    "SUBSECCION": "Subsección",
}

# Separador entre el número del nivel y su nombre en el encabezado
# generado. LIBRO/PARTE/TÍTULO usan guion simple ("TÍTULO 9 - ...") y
# CAPÍTULO/SECCIÓN/SUBSECCIÓN usan guion largo ("Capítulo 9 – ..."):
# distinción real de los documentos de origen ("# TÍTULO 8 - GESTIÓN
# INSTITUCIONAL" con guion simple vs. "## Capítulo 1 – TRANSICIÓN
# INSTITUCIONAL" con guion largo) — no una preferencia arbitraria de este
# script.
LEVEL_SEPARATOR = {
    "LIBRO": "-",
    "PARTE": "-",
    "TITULO": "-",
    "CAPITULO": "–",
    "SECCION": "–",
    "SUBSECCION": "–",
}

# Tamaño máximo (en caracteres) recomendado por chunk antes de forzar una
# subdivisión temática dentro de un mismo artículo. Ajusta según tu modelo
# de embeddings (ver instrucciones al final del script).
MAX_CHUNK_CHARS = 3500

# ----------------------------------------------------------------------------
# 3.1 NORMALIZACIÓN DE LISTAS NUMERADAS ROTAS
# ----------------------------------------------------------------------------

# Algunos PDF descargados de portales de normas pierden los numerales de
# las listas numeradas durante la extracción: solo se conserva el primero y
# alguno suelto, mientras que los párrafos intermedios quedan sin numerar.
# Estas expresiones detectan el inicio de una lista numerada.
LIST_INTRO_PATTERNS = [
    re.compile(r"tienen las siguientes obligaciones\s*:", re.IGNORECASE),
    re.compile(r"serán las siguientes\s*:", re.IGNORECASE),
    re.compile(r"deberán cumplir las siguientes\s*:", re.IGNORECASE),
    re.compile(r"desarrollarán las siguientes\s*:", re.IGNORECASE),
    re.compile(r"las siguientes actividades\s*:", re.IGNORECASE),
    re.compile(r"las siguientes obligaciones\s*:", re.IGNORECASE),
    re.compile(r"son las siguientes\s*:", re.IGNORECASE),
    re.compile(r"deberán\s*:", re.IGNORECASE),
]

# Verbos en infinitivo típicos con los que empiezan los elementos de una lista
# de obligaciones/acciones en normas en español.
INFINITIVE_START_RE = re.compile(
    r"^(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+)*(?:"
    r"Promover|Establecer|Realizar|Emitir|Implementar|Brindar|Afiliar|Recaudar|"
    r"Garantizar|Disponer|Diligenciar|Procurar|Practicarse|Participar|Trabajar|"
    r"Fomentar|Apoyar|Convocar|Designar|Examinar|Instalar|Pagar|Informar|"
    r"Suministrar|Capacitar|Asesorar|Velar|Cumplir|Adoptar|Adelantar|"
    r"Priorizar|Identificar|Evaluar|Controlar|Gestionar|Prestar|Presentar|"
    r"Solicitar|Definir|Desarrollar|Formular|Ejecutar|Reportar|Actualizar|"
    r"Conservar|Registrar|Conocer|Respetar|Cooperar|Colaborar|Facilitar|"
    r"Permitir|Orientar|Divulgar|Allegar|Dar|Verificar|Ordenar|Asegurarse|"
    r"Restituir|Incluir|Entregar)\b",
    re.IGNORECASE,
)

# Detecta numerales enteros o decimales, con o sin separador, al inicio de
# línea.
NUMERAL_RE = re.compile(r"^(\d+(?:\.\d+)*)\s*[\.,]?\s*")
NUMERAL_INLINE_RE = re.compile(r"(\d+(?:\.\d+)*)\s*[\.,]?\s*")

# Frases que indican una cláusula final y no deben numerarse como ítems.
# El numeral opcional al inicio cubre casos en que el PDF original asignó un
# número a una línea que en realidad es una nota final (p. ej.
# "9. Las demás obligaciones..." o "12. (Artículo MODIFICADO...)").
FINAL_CLAUSE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\s*[\.,]?\s+)?(?:Las demás|Lo demás|Demás|"
    r"Las obligaciones señaladas|En todo caso|Sin perjuicio|Salvo|"
    r"A excepción|Excepto|\(Artículo MODIFICADO|\(Decreto|\(Art\.)\)",
    re.IGNORECASE,
)

_END_OF_SENTENCE_RE = re.compile(r"[.!?;:]$")


def _reflow_lines(lines: list) -> list:
    """
    Recompone párrafos que pdfplumber partió por ancho de página.

    Une líneas consecutivas cuando la primera no termina en signo de
    puntuación final. Conserva guiones al final de línea como indicio de
    palabra partida, aunque en la práctica los PDF normativos rara vez los usan.
    """
    out = []
    buf = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            if buf:
                out.append(buf)
                buf = ""
            continue
        if buf:
            if _END_OF_SENTENCE_RE.search(buf):
                out.append(buf)
                buf = line
            else:
                sep = "" if buf.endswith("-") else " "
                buf = buf.rstrip() + sep + line
        else:
            buf = line
    if buf:
        out.append(buf)
    return out


def _extract_numeral(text: str):
    m = NUMERAL_RE.match(text.strip())
    return m.group(1) if m else None


def _parse_numeral(num_str: str):
    try:
        return tuple(int(x) for x in num_str.split("."))
    except ValueError:
        return None


def _numerals_are_consecutive(numbers: list) -> bool:
    """Verifica si una lista de numerales (str) es consecutiva."""
    parsed = [_parse_numeral(n) for n in numbers]
    if any(p is None for p in parsed):
        return False
    for i in range(1, len(parsed)):
        prev, curr = parsed[i - 1], parsed[i]
        if len(prev) != len(curr):
            return False
        if curr[:-1] != prev[:-1]:
            return False
        if curr[-1] != prev[-1] + 1:
            return False
    return True


def normalize_broken_numbered_lists(body: str) -> str:
    """
    Detecta listas numeradas rotas dentro del cuerpo de un artículo y las
    renumerá consecutivamente cuando haya evidencia suficiente.

    Heurística conservadora:
      1. Busca un introductor de lista numerada.
      2. Recompone los párrafos que el extractor partió por ancho de página.
      3. Toma los párrafos siguientes mientras parezcan elementos de lista.
      4. Si hay numerales faltantes o la secuencia presente no es consecutiva,
         renumerar con enteros. Si todos los numerales están presentes y son
         consecutivos, solo normalizar el formato cuando esté pegado.

    Esto corrige casos reales donde el PDF original de un artículo solo
    conserva los numerales "1." y "7,".
    """
    paragraphs = body.split("\n")
    out = []
    i = 0
    while i < len(paragraphs):
        p = paragraphs[i]
        intro_match = None
        for pat in LIST_INTRO_PATTERNS:
            m = pat.search(p)
            if m:
                intro_match = m
                break
        if intro_match is None:
            out.append(p)
            i += 1
            continue

        intro_paragraph = p
        raw_candidates = []
        j = i + 1
        while j < len(paragraphs):
            cand = paragraphs[j].strip()
            if not cand:
                j += 1
                continue
            if FINAL_CLAUSE_RE.match(cand):
                break
            raw_candidates.append(cand)
            j += 1

        # Recomponer líneas partidas por ancho de página antes de decidir
        # dónde termina la lista y qué es cada elemento.
        candidates = _reflow_lines(raw_candidates)

        # Tras el reflow, algún candidato puede empezar con una cláusula final
        # (p. ej. porque el reflow unió su continuación). Cortar ahí.
        for k, cand in enumerate(candidates):
            if FINAL_CLAUSE_RE.match(cand):
                candidates = candidates[:k]
                break

        numerals = [_extract_numeral(c) for c in candidates]
        present = [n for n in numerals if n is not None]
        has_missing = any(n is None for n in numerals)

        if not present or len(candidates) < 2:
            out.append(p)
            i += 1
            continue

        # Si el numeral 1 (o el primero) quedó pegado al introductor,
        # separarlo como primer elemento de la lista.
        m_inline = NUMERAL_INLINE_RE.search(intro_paragraph)
        if m_inline:
            prefix = intro_paragraph[:m_inline.start()].rstrip()
            first_item = intro_paragraph[m_inline.start():].strip()
            first_item = NUMERAL_INLINE_RE.sub("", first_item, count=1).strip()
            intro_paragraph = prefix
            candidates = [first_item] + candidates
            numerals = [_extract_numeral(c) for c in candidates]
            present = [n for n in numerals if n is not None]
            has_missing = any(n is None for n in numerals)

        # Si todos los elementos tienen numeral y son consecutivos, solo
        # normalizar el formato cuando esté pegado (p. ej. "1Participar").
        if not has_missing and _numerals_are_consecutive(present):
            valid_numeral_re = re.compile(r"^\d+(?:\.\d+)*(?:\.\s+|\s+)")
            all_well_formatted = all(valid_numeral_re.match(c) for c in candidates)
            if all_well_formatted:
                new_items = [
                    re.sub(r"\bcorno\b", "como", c, flags=re.IGNORECASE)
                    for c in candidates
                ]
                out.append(intro_paragraph)
                out.extend(new_items)
                i = j
                continue

            # Algunos elementos están pegados: normalizar formato.
            new_items = []
            for cand in candidates:
                num = _extract_numeral(cand)
                rest = NUMERAL_RE.sub("", cand, count=1)
                rest = re.sub(r"\bcorno\b", "como", rest, flags=re.IGNORECASE)
                new_items.append(f"{num}. {rest}")
            out.append(intro_paragraph)
            out.extend(new_items)
            i = j
            continue

        # Si hay numerales faltantes o la secuencia presente no es consecutiva,
        # renumerar todos con enteros consecutivos.
        if has_missing or not _numerals_are_consecutive(present):
            new_items = []
            for idx, cand in enumerate(candidates, start=1):
                cand = NUMERAL_RE.sub("", cand, count=1)
                cand = re.sub(r"\bcorno\b", "como", cand, flags=re.IGNORECASE)
                new_items.append(f"{idx}. {cand}")
            out.append(intro_paragraph)
            out.extend(new_items)
            i = j
            continue

        out.append(p)
        i += 1

    return "\n".join(out)


def slugify(text: str, maxlen: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9áéíóúñ\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:maxlen].strip("-")


def split_long_block(body: str, max_chars: int) -> list:
    """
    Si un artículo es demasiado largo (típico en decretos que definen procesos
    con numerales 1.1, 1.2, 2.1...), lo parte en sub-bloques usando como
    puntos de corte los numerales de primer nivel (1., 2., 3. ...) o, en su
    defecto, párrafos completos. Nunca corta a mitad de una oración/numeral.
    """
    if len(body) <= max_chars:
        return [body]

    # Intentar cortar en numerales de primer nivel: líneas que empiezan con
    # "1.", "2.1.", "En el Proceso de..." etc. Aquí usamos como separador
    # los numerales tipo "N.N." al inicio de línea/párrafo.
    # \d+ (no \d): un artículo con más de 9 numerales (caso real: una
    # lista de funciones con más de 40) tiene ítems como "10.",
    # "23.", etc. — \d suelto solo reconoce el primer dígito y nunca hace
    # match en el "0"/"1" que sigue (la "." literal del patrón no coincide
    # con el segundo dígito), así que ningún numeral de dos o más cifras se
    # reconocía como punto de corte: el artículo completo quedaba sin
    # dividir a partir de ahí (visto como un solo chunk de 17k+ caracteres,
    # ~5x MAX_CHUNK_CHARS, cuando el primer intento de corte encontraba como
    # mucho un puñado de numerales de un dígito antes de rendirse).
    # (?:\.\d+)* (no solo \d*) y -?\s (no solo \s) tras el punto opcional:
    # algunas circulares usan numerales de hasta 3 niveles con guion pegado
    # ("1.1.1. texto", "1.1.- texto") en vez de "1.1. texto" — \d* solo
    # reconocía UN nivel adicional (N.N.) y \s exigía espacio inmediato tras
    # el punto, así que ni "1.1.1." (tres niveles) ni "1.1.-" (guion antes
    # del espacio) se reconocían como punto de corte, y el bloque completo
    # quedaba sin dividir (visto como chunks de hasta 14.5k caracteres,
    # ~4x MAX_CHUNK_CHARS).
    def _split_por_lineas(texto):
        # Partir por línea (no por "párrafo doble"/"\n\n") y agrupar hasta
        # max_chars. clean_text() descarta toda línea en blanco y nunca vuelve a
        # dejar un "\n\n" en el cuerpo del artículo — así que
        # "texto.split('\n\n')" nunca encuentra más de 1 parte.
        paras = texto.split("\n")
        partes = []
        actual = ""
        for p in paras:
            if len(actual) + len(p) > max_chars and actual:
                partes.append(actual.strip())
                actual = p
            else:
                actual += ("\n" if actual else "") + p
        if actual:
            partes.append(actual.strip())
        return partes

    parts = re.split(r"\n(?=\d+(?:\.\d+)*\.?-?\s|\d+\.\s[A-ZÁÉÍÓÚÑ])", body)
    if len(parts) <= 1:
        # Un artículo largo sin numerales de primer nivel (ej. una lista con
        # guiones "-", no dígitos) cae aquí.
        # Visto con 10k+ caracteres, ~3x MAX_CHUNK_CHARS, antes de que este
        # fallback funcionara.
        return _split_por_lineas(body)

    # Un artículo/glosario con numerales de primer nivel MUY dispersos dentro
    # de párrafos largos (ej. un artículo de Definiciones de un reglamento
    # técnico: un glosario alfabético de cientos de términos donde solo
    # unas pocas definiciones mencionan un numeral que calza por accidente
    # con el patrón de arriba) deja algún `part` individual ya de por sí
    # mucho más grande que max_chars — el reagrupado de abajo solo FUSIONA
    # partes chicas entre sí, nunca vuelve a partir una que ya nació grande.
    # Sin este paso, esa definición terminaba en un chunk de hasta 30k
    # caracteres (~8.5x el techo) mientras el resto del artículo quedaba
    # repartido en partes normales. Se aplica el split por líneas a CUALQUIER
    # parte que por sí sola ya supere max_chars, antes de reagrupar.
    parts = [
        subparte
        for part in parts
        for subparte in (_split_por_lineas(part) if len(part) > max_chars else [part])
    ]

    # Reagrupar fragmentos pequeños para no generar chunks minúsculos
    grouped = []
    current = ""
    for part in parts:
        if len(current) + len(part) > max_chars and current:
            grouped.append(current.strip())
            current = part
        else:
            current += ("\n" if current else "") + part
    if current:
        grouped.append(current.strip())
    return grouped


def parse_document(text: str, meta: dict) -> list:
    """
    Recorre el texto línea por línea manteniendo una pila de contexto
    (capítulo/sección/subsección/artículo actuales) y devuelve una lista de
    "bloques" con su ruta jerárquica completa y su contenido.
    """
    lines = text.split("\n")
    blocks = []
    stack = {t: None for t in NIVEL_ORDEN}
    current_articulo = None
    current_body = []
    # Títulos de artículos "cáscara" (solo rótulo, sin cuerpo propio — ver
    # comentario en flush_articulo) en espera de fusionarse con el próximo
    # artículo real.
    pending_titulos = []

    def _etiqueta_de_titulo(titulo_articulo):
        m = re.match(r"^Artículo [\d.°]+\.?\s*(.+)$", titulo_articulo)
        return m.group(1).strip() if m else None

    def _niveles_reales(stack):
        # Lista ordenada (tipo, label) de los niveles LIBRO/PARTE/TITULO/
        # CAPITULO/SECCION/SUBSECCION realmente activos en este punto del
        # documento (no None), en orden jerárquico. build_markdown() la usa
        # para decidir qué encabezados "#"/"##"/... emitir sin depender de
        # reconstruir la jerarquía a partir del breadcrumb de texto plano.
        return [(t, stack[t]) for t in NIVEL_ORDEN if stack[t]]

    def flush_pending_como_bloques():
        # Si un artículo-cáscara nunca llega a fusionarse (cambia de
        # Capítulo/Sección antes de que aparezca un artículo real, o es el
        # último del documento), no se descarta en silencio: se emite como
        # bloque propio, igual que antes de este fix.
        for titulo in pending_titulos:
            blocks.append({
                "tipo": "ARTICULO",
                "titulo": titulo,
                "ruta": build_ruta(stack, titulo),
                "niveles": _niveles_reales(stack),
                "body": "",
            })
        pending_titulos.clear()

    def flush_articulo():
        nonlocal current_articulo, current_body
        if current_articulo is not None:
            body = "\n".join(current_body).strip()
            body = normalize_broken_numbered_lists(body)
            if not body:
                # Artículo "cáscara": solo título/rótulo, sin cuerpo propio
                # (común en el Libro 1 de los DUR: "ARTÍCULO 1.2.1.1 Nombre
                # Entidad." es apenas un nombre, y el contenido real arranca
                # en "ARTÍCULO 1.2.1.1.1"). En vez de un chunk casi vacío
                # con "[REVISAR: cuerpo vacío]", se guarda para fusionarlo
                # como contexto en la ruta del próximo artículo real — así
                # no se pierde el nombre de la entidad ni se desperdicia un
                # chunk sin contenido recuperable.
                pending_titulos.append(current_articulo)
            else:
                extra = [
                    e for e in (_etiqueta_de_titulo(t) for t in pending_titulos) if e
                ]
                blocks.append({
                    "tipo": "ARTICULO",
                    "titulo": current_articulo,
                    "ruta": build_ruta(stack, current_articulo, extra=extra),
                    "niveles": _niveles_reales(stack),
                    "body": body,
                })
                pending_titulos.clear()
        elif current_body:
            # Texto huérfano: párrafos de prosa entre un encabezado
            # LIBRO/PARTE/TÍTULO/CAPÍTULO/SECCIÓN y el siguiente encabezado
            # (o el primer ARTÍCULO), sin que nunca se abriera un ARTÍCULO
            # en el medio — común en reglamentos técnicos extensos, cuyos
            # "Libros" mezclan artículos numerados con secciones enteras
            # redactadas como texto corrido sin numeral de artículo (caso
            # real: ~260 líneas de requisitos técnicos, ninguna bajo un
            # "ARTÍCULO"). Como los encabezados de sección solo se
            # renderizan como efecto colateral de renderizar un bloque de
            # artículo (ver build_markdown), sin este bloque sintético el
            # texto completo se perdía en silencio: current_body se
            # descartaba acá mismo al procesar el siguiente encabezado, sin
            # generar ningún chunk ni ningún aviso.
            body = "\n".join(current_body).strip()
            body = normalize_broken_numbered_lists(body)
            if body:
                blocks.append({
                    "tipo": "ARTICULO",
                    "titulo": "Introducción",
                    "ruta": build_ruta(stack, "Introducción"),
                    "niveles": _niveles_reales(stack),
                    "body": body,
                })
        current_articulo = None
        current_body = []

    def build_ruta(stack, articulo_titulo=None, extra=None):
        parts = [meta.get("titulo", "Documento")]
        parts.extend(label for _, label in _niveles_reales(stack))
        if extra:
            parts.extend(extra)
        if articulo_titulo:
            destino = meta.get("decreto_destino")
            if destino:
                # Numeración con puntos (2.2.4.12.1) = artículo insertado
                # en el decreto destino, no un artículo propio de este
                # decreto (esos van sin puntos: "Artículo 1", "Artículo 2").
                m_num = re.match(r"^Artículo (\d+(?:\.\d+)+)", articulo_titulo)
                if m_num:
                    articulo_titulo = (
                        f"{articulo_titulo} (pasa a ser {destino}, "
                        f"Artículo {m_num.group(1)})"
                    )
            parts.append(articulo_titulo)
        return " > ".join(parts)

    # Bloques de tabla de contenido: en vez de mirar línea por línea (frágil,
    # ver historial de este comentario), se detecta el BLOQUE completo del
    # índice de una vez. Una entrada de índice real ("TÍTULO 2 -
    # DEFINICIONES ..... 4", con puntos-guía y número de página) puede
    # envolver su título en 1-3 líneas antes de llegar a la línea con los
    # puntos (caso real: un TÍTULO del índice de un Libro con título en 2
    # líneas, puntos en la 3ª). Y como LIBRO/PARTE/TÍTULO/CAPÍTULO ahora
    # aceptan nombre en la misma línea (ver arriba), cada entrada del
    # índice calza igual que un encabezado real — sin excluir el bloque
    # completo, cada índice (uno por cada Libro del documento)
    # generaba encabezados falsos duplicados de los reales, y algunos
    # títulos reales quedaban con el nombre truncado por el índice que los
    # precede. Un tramo de líneas con marcadores de índice separados por 6
    # líneas o menos se trata como UN solo bloque de índice (cubre el caso
    # de varias entradas seguidas), extendido 3 líneas hacia atrás desde el
    # primer marcador para cubrir el título envuelto de esa primera entrada.
    _toc_markers = [idx for idx, l in enumerate(lines) if TOC_ENTRY_RE.search(l.strip())]
    toc_block_lines = set()
    if _toc_markers:
        cluster_start, prev = _toc_markers[0], _toc_markers[0]
        for idx in _toc_markers[1:] + [None]:
            if idx is not None and idx - prev <= 6:
                prev = idx
                continue
            toc_block_lines.update(range(max(0, cluster_start - 3), prev + 1))
            if idx is not None:
                cluster_start = prev = idx

    preamble_lines = []
    started_hierarchy = False
    enacted = False
    ENACTED_RE = re.compile(r"^\s*(?:DECRETA|DECRETAN|RESUELVE|RESUELVEN|ACUERDA|ACUERDAN|HA\s+RESUELTO)\b", re.IGNORECASE)

    i = 0
    while i < len(lines):
        line = _normalizar_titulo_espaciado(lines[i].strip())
        matched = False

        if ENACTED_RE.search(line):
            enacted = True

        for tipo, pattern in ([] if i in toc_block_lines else HIERARCHY_PATTERNS):
            m = pattern.match(line)
            if not m:
                continue

            # Un ARTÍCULO no puede existir antes de DECRETA/RESUELVE ni de un CAPÍTULO/SECCIÓN.
            # Citas en considerandos (ej. "el artículo 189 de la Constitución") se tratan como preámbulo.
            if tipo == "ARTICULO" and not enacted and not stack["CAPITULO"] and not stack["SECCION"]:
                continue

            matched = True
            started_hierarchy = True

            if tipo == "ARTICULO":
                flush_articulo()
                numero = m.group(1)
                if not re.match(r"^[\d.°]+$", numero):
                    numero = ORDINALES_ARTICULO.get(numero.lower(), numero)
                rest = m.group(2).strip()

                # Heurística para separar una "etiqueta" corta (p. ej. "Objeto",
                # "Adición", "Alcance") del cuerpo del artículo, buscando el
                # primer punto seguido de pocas palabras. Si no aplica, todo
                # el texto queda como cuerpo y el encabezado usa solo el número.
                #
                # Tope original 70 caracteres/8 palabras: calibrado para
                # títulos cortos típicos de decretos ("Objeto.", "Vigencia.").
                # Varias leyes (p. ej. "De las entidades científicas adscritas
                # y vinculadas al ministerio del ramo." — 80 caracteres, 12
                # palabras) usan títulos de artículo bastante
                # más descriptivos, que quedaban rechazados y caían enteros
                # dentro del cuerpo, dejando el encabezado como solo el número
                # ("Artículo 16") sin ninguna pista de contenido — un chunk
                # recuperado solo por su breadcrumb no decía de qué trataba
                # hasta leer el cuerpo completo.
                #
                # Por eso se AMPLÍA el tope a 150/20 solo como rango
                # adicional, no reemplazando el original: dentro de 70/8 se
                # acepta la etiqueta igual que siempre (sin chequeo extra,
                # para no arriesgar ningún caso ya probado), y el rango
                # ampliado (70-150 car./8-20 palabras) exige ADEMÁS que la
                # candidata arranque con una mayúscula real. Sin esa condición
                # extra, la primera oración COMPLETA de un artículo sin título
                # propio (sujeto + verbo conjugado, no una etiqueta) se cuela
                # como si fuera título en cuanto supera las 8 palabras — visto
                # en un decreto cuyo Artículo 7 arranca con "º El Plan está
                # estructurado en tres capítulos básicos..." (el "º"
                # es un resto de numeral de lista roto en la extracción del
                # PDF), una oración de cuerpo normal, no un título, que con el
                # tope ampliado sin este chequeo pasaba igual. Un título real,
                # a diferencia de una oración de cuerpo, arranca con letra
                # mayúscula de verdad ("De las...", "Del...", "Creación..."),
                # nunca con un símbolo/numeral suelto — no es un filtro
                # perfecto (no distingue frase nominal de oración con sujeto
                # en mayúscula), pero cubre el caso observado.
                # Mantener el rango 70/8 sin este chequeo importa además por
                # otro caso real (una ley, Artículos 90/91): un cáscara
                # cuyo único contenido es una cita cruzada de 8 palabras que
                # arranca en minúscula ("de la Constitución Política
                # reglamentará la presente ley") — si se le exigiera mayúscula
                # también en ese rango, dejaría de vaciarse por completo, el
                # cáscara pasaría a tener cuerpo no vacío y se renderizaría
                # como un chunk propio "Artículo 189" (número tomado de esa
                # misma cita, un falso artículo) en vez de fusionarse
                # silenciosamente como contexto del artículo siguiente (el
                # comportamiento ya existente, que tampoco es perfecto — esa
                # cita cruzada mal detectada como límite de ARTÍCULO es un bug
                # aparte, no introducido por este cambio — pero es claramente
                # menos dañino que un chunk fantasma con número inventado).
                etiqueta = None
                remainder = rest
                primer_punto = _fin_de_etiqueta(rest)
                if 0 < primer_punto <= 150:
                    candidata = rest[:primer_punto].strip()
                    if candidata:
                        n_palabras = len(candidata.split())
                        posible_remainder = rest[primer_punto + 1:].strip()
                        dentro_tope_original = primer_punto <= 70 and n_palabras <= 8
                        # En el rango ampliado se exige además que quede algo
                        # de cuerpo después del punto (posible_remainder no
                        # vacío). Sin este chequeo, un artículo corto de una
                        # sola oración completa (ej. un Artículo 13: "Los
                        # muros o paredes de las oficinas talleres y bodegas
                        # deberán ser construidos con materiales
                        # incombustibles.", 110 caracteres/15 palabras —
                        # dentro del rango ampliado) se clasifica como
                        # "etiqueta" con cuerpo vacío. Un artículo con cuerpo
                        # vacío se trata como "cáscara" (ver flush_articulo) y
                        # se fusiona en silencio como contexto extra del
                        # SIGUIENTE artículo real — el texto normativo
                        # completo del Artículo 13 quedaba enterrado en la
                        # ruta del Artículo 14 en vez de tener su propio chunk
                        # recuperable. El chequeo del tope original (70/8, sin
                        # este requisito) se deja intacto: calibrado para
                        # etiquetas cortas reales ("Objeto.", "Vigencia.") ya
                        # probadas en el corpus.
                        en_rango_ampliado = (
                            n_palabras <= 20
                            and candidata[:1].isupper()
                            and posible_remainder
                        )
                        if dentro_tope_original or en_rango_ampliado:
                            etiqueta = candidata
                            remainder = posible_remainder

                # Título en línea física separada, sin texto en la misma
                # línea que "ARTÍCULO N" (rest vacío, no solo sin etiqueta
                # reconocida): visto en un reglamento técnico extenso, cuyos
                # artículos de definición/producto van "Artículo 1.3.1" solo
                # en su línea, y el título real ("Abreviaturas, acrónimos y
                # siglas", "Aerogeneradores"...) en la línea siguiente, como
                # frase corta SIN punto final (a diferencia del título en la
                # misma línea, que si existe siempre lo cierra un punto — de
                # ahí que la heurística de arriba, basada en buscar el primer
                # punto, nunca lo encuentre acá). Confirmado sobre 173 casos
                # de ese documento: 171 títulos reales, ninguno por encima
                # de 68 caracteres/11 palabras y todos con mayúscula inicial;
                # los 2 restantes ("del presente Reglamento..." x2) no son
                # títulos sino cuerpo de una cita cruzada numérica envuelta
                # ("...el artículo 2.3.27 del presente Reglamento...") que ya
                # se detecta (mal) como límite de ARTÍCULO — bug aparte, no
                # introducido ni resuelto por este cambio; el
                # arranque en minúscula de ambos los excluye igual que
                # excluiría un título real que fuera oración de cuerpo.
                if not etiqueta and not rest.strip():
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        candidata = lines[j].strip()
                        n_palabras = len(candidata.split())
                        es_encabezado_o_toc = (
                            any(p.match(candidata) for _, p in HIERARCHY_PATTERNS)
                            or TOC_ENTRY_RE.search(candidata)
                        )
                        if (
                            candidata
                            and not es_encabezado_o_toc
                            and len(candidata) <= 90
                            and n_palabras <= 15
                            and candidata[:1].isupper()
                            and not candidata.rstrip().endswith(":")
                        ):
                            etiqueta = candidata
                            i = j

                current_articulo = f"Artículo {numero}" + (f". {etiqueta}" if etiqueta else "")
                if remainder:
                    current_body.append(remainder)
            else:
                flush_articulo()
                # Un artículo-cáscara pendiente de fusión no debe "saltar"
                # a un Capítulo/Sección distinto del suyo: si no aparece un
                # artículo real antes del próximo encabezado, se emite tal
                # cual (ver flush_pending_como_bloques).
                flush_pending_como_bloques()
                # Si el patrón ya capturó el título en la misma línea
                # (grupo 2, p. ej. "SECCIÓN 1 DISPOSICIONES GENERALES"),
                # se usa directamente; si no, el título real suele venir en
                # la línea siguiente, pero a veces el PDF intercala antes una
                # nota editorial completa (ej. "(Capítulo Adicionado por el
                # Art. 1 del Decreto 600 de 2021)") entre el número y su
                # nombre real en mayúscula sostenida. Saltamos esas notas en
                # vez de tomarlas como si fueran el título.
                #
                # Pero la nota editorial también puede venir PEGADA AL FINAL
                # de un título real, en la misma línea, sin salto (ej.
                # "ACTUACIÓN EN CASO DE IMPOSICIÓN DE COMPARENDO AL CONDUCTOR
                # PARA EL TRANSPORTE PÚBLICO. Modificado por el art. 23, Ley
                # 800 de 2010"). Si
                # se descartara la línea completa en ese caso (mismo criterio
                # que arriba), el nombre quedaba vacío ("## Capítulo IV" sin
                # texto) y el título real terminaba huérfano como un bloque
                # "Introducción" suelto en el chunk siguiente. Se distingue
                # por posición: si la nota aparece cerca del inicio (línea
                # que ES la nota, con como mucho una etiqueta corta tipo
                # "Capítulo 5," antes), se descarta igual que siempre; si
                # aparece bien entrada la línea, hay contenido real de título
                # antes y se conserva la línea completa (incluida la nota,
                # igual que ya se conservan notas de este tipo dentro del
                # cuerpo de un ARTÍCULO).
                nombre = ""
                if m.lastindex and m.lastindex >= 2 and m.group(2):
                    nombre = m.group(2).strip()
                j = i + 1
                while not nombre and j < len(lines) and j <= i + 5:
                    candidata = lines[j].strip()
                    if not candidata or any(
                        p.match(candidata) for _, p in HIERARCHY_PATTERNS
                    ):
                        break
                    _m_nota = EDITORIAL_NOTE_RE.search(candidata)
                    if _m_nota and _m_nota.start() <= 25:
                        j += 1
                        continue
                    nombre = candidata
                    i = j
                    break
                # Nombre envuelto en 2-3 líneas físicas del PDF (venga de la
                # captura en línea o del fallback anterior): mientras la
                # línea ya capturada no termine en puntuación de cierre de
                # oración y la siguiente línea "parezca" continuación de un
                # encabezado (mayúscula sostenida, corta, no es ella misma
                # otro encabezado ni un ARTÍCULO), se va uniendo — caso
                # real: "TÍTULO 4 – ESPACIOS PARA MONTAJE
                # DE EQUIPOS Y DISTANCIAS" seguía en "MÍNIMAS DE SEGURIDAD,
                # PARA OPERACIÓN Y MANTENIMIENTO DE" y terminaba en
                # "INFRAESTRUCTURA ELÉCTRICA" (2 líneas más), y sin esto el
                # nombre quedaba cortado a la primera línea nada más. Tope
                # de 3 líneas extra para no arrastrar párrafos enteros si la
                # heurística falla en algún caso no previsto.
                _extra_lineas = 0
                while (
                    nombre
                    and not nombre.rstrip().endswith((".", ":", "!", "?", ")"))
                    and _extra_lineas < 3
                    and i + 1 < len(lines)
                ):
                    candidata = lines[i + 1].strip()
                    if (
                        not candidata
                        or len(candidata) > 90
                        or re.match(r"^ART[ÍI]CULO\b", candidata, re.IGNORECASE)
                        or any(p.match(candidata) for _, p in HIERARCHY_PATTERNS)
                        or TOC_ENTRY_RE.search(candidata)
                    ):
                        break
                    letras = [c for c in candidata if c.isalpha()]
                    if not letras or sum(1 for c in letras if c.isupper()) / len(letras) < 0.7:
                        break
                    nombre = f"{nombre} {candidata}"
                    i += 1
                    _extra_lineas += 1
                # "ª" (ordinal femenino, ej. "CAPÍTULO 5ª") se normaliza a
                # "A" para que coincida con la numeración real de sus
                # artículos ("2.2.8.5A.1", no "2.2.8.5ª.1"). Un ordinal en
                # palabra ("PRIMERO", "SEGUNDO"...) se convierte al dígito
                # equivalente por la misma razón: los artículos del capítulo
                # se numeran con dígitos ("2.2.12.1.1", no "2.2.12.PRIMERO.1").
                numero_nivel = m.group(1)
                if not re.match(r"^\d", numero_nivel):
                    numero_nivel = ORDINALES_ARTICULO.get(numero_nivel.lower(), numero_nivel)
                numero_nivel = numero_nivel.replace("ª", "A")
                sep = LEVEL_SEPARATOR[tipo]
                label = f"{DISPLAY_NAMES[tipo]} {numero_nivel}" + (f" {sep} {nombre}" if nombre else "")
                stack[tipo] = label
                # Al reiniciar un nivel superior, se limpian todos los
                # inferiores en NIVEL_ORDEN (antes solo CAPITULO->SECCION/
                # SUBSECCION; ahora también LIBRO/PARTE/TITULO en cascada
                # hacia abajo, ej. un nuevo TÍTULO limpia el CAPÍTULO/
                # SECCIÓN/SUBSECCIÓN del título anterior).
                idx_tipo = NIVEL_ORDEN.index(tipo)
                for inferior in NIVEL_ORDEN[idx_tipo + 1:]:
                    stack[inferior] = None
            break

        if not matched:
            if started_hierarchy:
                if current_articulo is not None:
                    current_body.append(lines[i])
                else:
                    # texto entre encabezados de sección y el primer artículo
                    current_body.append(lines[i])
            else:
                preamble_lines.append(lines[i])
        i += 1

    flush_articulo()
    flush_pending_como_bloques()

    preamble = "\n".join(preamble_lines).strip()

    # Separar el bloque de firmas (suele quedar pegado al último artículo)
    firmas_block = None
    # C[UÚ]MPLASE|EJEC[UÚ]TESE: la fórmula de cierre varía por tipo de norma
    # ("PUBLÍQUESE Y CÚMPLASE" en decretos, "PUBLÍQUESE Y EJECÚTESE" en varias
    # leyes). Sin la segunda variante, el bloque de firmas de esas leyes no se
    # separaba del cuerpo del último artículo (quedaba fusionado con
    # "Vigencia"), y como firmas_block quedaba None, detect_metadata tampoco
    # tenía dónde buscar el firmante. PUBL[IÍ]QUESE|NOTIF[IÍ]QUESE: varias
    # resoluciones ministeriales cierran con "NOTIFÍQUESE Y CÚMPLASE" en vez
    # de "PUBLÍQUESE..." — mismo problema de fusión con el último artículo si
    # solo se reconoce la variante de publicación. COMUN[IÍ]QUESE: algunas
    # leyes cierran con "COMUNÍQUESE Y EJECÚTESE" — tercera variante del mismo
    # problema: sin ella, el bloque de firmas (incluidas las firmas de quienes
    # expiden la norma) quedaba fusionado dentro del cuerpo del último
    # artículo (Vigencia) en vez de separarse en su propio chunk "Firmas".
    firma_marker = re.compile(r"(?:PUBL[IÍ]QUESE|NOTIF[IÍ]QUESE|COMUN[IÍ]QUESE) Y (?:C[UÚ]MPLASE|EJEC[UÚ]TESE)", re.IGNORECASE)
    if blocks:
        last = blocks[-1]
        m = firma_marker.search(last["body"])
        if m:
            firmas_body = last["body"][m.start():].strip()
            last["body"] = last["body"][:m.start()].strip()
            firmas_block = {
                "tipo": "FIRMAS",
                "titulo": "Firmas",
                "ruta": f"{meta.get('titulo', 'Documento')} > Firmas",
                "body": firmas_body,
            }

    return preamble, blocks, firmas_block


# ----------------------------------------------------------------------------
# 4. GENERACIÓN DE MARKDOWN
# ----------------------------------------------------------------------------

def build_markdown(meta: dict, preamble: str, blocks: list, source_filename: str, firmas_block: dict = None) -> str:
    out = []

    # --- Front matter ---
    out.append("---")
    out.append(f'titulo: "{meta.get("titulo")}"')
    out.append(f'tipo_norma: "{meta.get("tipo_norma")}"')
    out.append(f'numero: "{meta.get("numero")}"')
    out.append(f'anio: {meta.get("anio")}')
    out.append(f'fecha_expedicion: "{meta.get("fecha_expedicion")}"')
    out.append(f'objeto: "{meta.get("objeto")}"')
    out.append(f'firmante: "{meta.get("firmante")}"')
    out.append('modifica: "TODO [REVISAR] - norma que este decreto adiciona/modifica, si aplica"')
    out.append('deroga: "TODO [REVISAR] - norma derogada, si aplica"')
    out.append(f'fuente: "{meta.get("fuente")}"')
    out.append(f'archivo_origen: "{source_filename}"')
    out.append(f'fecha_conversion: "{datetime.now().strftime("%Y-%m-%d")}"')
    out.append("---")
    out.append("")

    titulo = meta.get("titulo", "Documento")
    out.append(f"# {titulo}")
    out.append("")
    out.append(f"**Ruta:** {titulo}")
    out.append("")
    if meta.get("objeto") and "TODO" not in str(meta.get("objeto")):
        out.append(f"**Sinopsis:** {meta.get('objeto')}.")
        out.append("")

    # --- Preámbulo / considerandos ---
    # Igual que los artículos, el preámbulo pasa por split_long_block(): antes
    # se emitía siempre como un solo chunk sin importar su tamaño (a
    # diferencia de los ARTICULO, que sí se parten desde siempre), y en
    # decretos/resoluciones con muchos "Que..." de considerandos podía
    # superar 2x MAX_CHUNK_CHARS sin que nada lo detectara (caso real:
    # preámbulo de 7459 caracteres).
    if preamble:
        preamble_ruta = f"{titulo} > Encabezado y considerandos"
        sub_preambulos = split_long_block(preamble, MAX_CHUNK_CHARS)
        for idx, sub_body in enumerate(sub_preambulos):
            suffix = "" if len(sub_preambulos) == 1 else f"-p{idx+1}"
            chunk_id = f'{slugify(titulo)}-preambulo{suffix}'
            chunk_ruta = preamble_ruta if len(sub_preambulos) == 1 else f"{preamble_ruta} (parte {idx+1}/{len(sub_preambulos)})"

            out.append(f'<!-- CHUNK id="{chunk_id}" ruta="{chunk_ruta}" -->')
            out.append("")
            if idx == 0:
                out.append("## Encabezado y considerandos")
                out.append("")
            out.append(f"**Ruta:** {chunk_ruta}")
            out.append("")
            out.append(sub_body)
            out.append("")
            out.append("<!-- /CHUNK -->")
            out.append("")
        out.append("---")
        out.append("")

    # --- Artículos --- Encabezados emitidos por tipo (no por posición): antes
    # se reconstruía la jerarquía trozando el breadcrumb de texto plano por "
    # > " y asumiendo posiciones fijas (0=Capítulo, 1=Sección, 2=Subsección),
    # lo cual ya no alcanza con LIBRO/PARTE/TÍTULO opcionales por delante (esa
    # reconstrucción posicional los habría renderizado como si fueran
    # Capítulo/Sección/Subsección). Cada bloque trae ahora su propia lista
    # "niveles" (tipo, label) armada directamente desde el stack real del
    # parser (ver _niveles_reales), así que no hace falta adivinar nada a
    # partir del texto del breadcrumb. Algunos portales de normas muestran,
    # para un artículo modificado, el texto vigente ("<El nuevo texto es el
    # siguiente>") seguido íntegro del texto original anterior a la reforma
    # ("El texto original era el siguiente:") — visto en el Artículo 3 de un
    # reglamento técnico. Ambos bloques comparten el mismo número/título de
    # artículo, así que sin desambiguar generaban dos chunks con id y ruta
    # IDÉNTICOS (colisión silenciosa: el segundo pisaría al primero en
    # cualquier índice por id). Se detecta la repetición de título y, si el
    # bloque anterior contiene el marcador de "texto original", se etiqueta
    # explícitamente como tal; si no hay marcador reconocible pero igual hay
    # colisión, se usa un sufijo genérico "(versión N)" como red de seguridad.
    TEXTO_ORIGINAL_MARKER_RE = re.compile(r"el texto original era el siguiente", re.IGNORECASE)
    titulo_art_vistos = {}
    prev_block_body = ""
    last_por_tipo = {t: None for t in NIVEL_ORDEN}
    for block in blocks:
        ruta = block["ruta"]
        titulo_art_original = block["titulo"]
        body = block["body"]

        ocurrencias_previas = titulo_art_vistos.get(titulo_art_original, 0)
        titulo_art_vistos[titulo_art_original] = ocurrencias_previas + 1
        if ocurrencias_previas == 0:
            titulo_art = titulo_art_original
        elif TEXTO_ORIGINAL_MARKER_RE.search(prev_block_body):
            titulo_art = f"{titulo_art_original} (texto original, anterior a la modificación)"
            ruta = f"{ruta} (texto original, anterior a la modificación)"
        else:
            titulo_art = f"{titulo_art_original} (versión {ocurrencias_previas + 1})"
            ruta = f"{ruta} (versión {ocurrencias_previas + 1})"
        prev_block_body = body

        activos = dict(block.get("niveles", []))
        cambio_arriba = False
        for t in NIVEL_ORDEN:
            if cambio_arriba:
                last_por_tipo[t] = None
            label = activos.get(t)
            if label and label != last_por_tipo[t]:
                out.append("#" * HEADING_LEVEL[t] + f" {label}")
                out.append("")
                last_por_tipo[t] = label
                cambio_arriba = True

        sub_bodies = split_long_block(body, MAX_CHUNK_CHARS)
        for idx, sub_body in enumerate(sub_bodies):
            suffix = "" if len(sub_bodies) == 1 else f"-p{idx+1}"
            chunk_id = f"{slugify(titulo)}-{slugify(titulo_art)}{suffix}"
            chunk_ruta = ruta if len(sub_bodies) == 1 else f"{ruta} (parte {idx+1}/{len(sub_bodies)})"

            out.append(f'<!-- CHUNK id="{chunk_id}" ruta="{chunk_ruta}" -->')
            out.append("")
            heading_level = "#" * (HEADING_LEVEL["ARTICULO"])
            if idx == 0:
                out.append(f"{heading_level} {titulo_art}")
                out.append("")
            out.append(f"**Ruta:** {chunk_ruta}")
            out.append("")
            out.append(sub_body if sub_body else "[REVISAR: cuerpo del artículo vacío o no reconocido]")
            out.append("")
            out.append("<!-- /CHUNK -->")
            out.append("")

    if firmas_block and firmas_block.get("body"):
        chunk_id = f"{slugify(titulo)}-firmas"
        out.append(f'<!-- CHUNK id="{chunk_id}" ruta="{firmas_block["ruta"]}" -->')
        out.append("")
        out.append("## Firmas")
        out.append("")
        out.append(f"**Ruta:** {firmas_block['ruta']}")
        out.append("")
        out.append(firmas_block["body"])
        out.append("")
        out.append("<!-- /CHUNK -->")
        out.append("")

    if meta.get("nota_fuente"):
        out.append("---")
        out.append("")
        out.append(f"**Nota de la fuente:** {meta['nota_fuente']}")

    return "\n".join(out)


# ----------------------------------------------------------------------------
# 5. ORQUESTACIÓN / CLI
# ----------------------------------------------------------------------------

def resolver_metadatos(meta: dict, pdf_path: str, spec: dict) -> dict:
    """Front-matter final: spec del usuario (metadatos.py) + lo detectado en
    el texto de la norma + las propiedades del PDF. Si el usuario fija el
    título, también se usa en el H1 y en las rutas de los chunks."""
    detectados = {k: v for k, v in metadatos.info_pdf(pdf_path).items() if v}
    normativos = {
        "titulo": meta.get("titulo"),
        "tipo_documento": meta.get("tipo_norma"),
        "numero": meta.get("numero"),
        "anio": meta.get("anio"),
        "fecha_expedicion": meta.get("fecha_expedicion"),
        "fecha_publicacion": meta.get("fecha_expedicion"),
        "descripcion": meta.get("objeto"),
        "firmante": meta.get("firmante"),
        "fuente": meta.get("fuente"),
    }
    detectados.update({k: v for k, v in normativos.items() if metadatos._detectado(v)})
    valores = metadatos.resolver(spec, detectados, os.path.basename(pdf_path))
    if metadatos._detectado(valores.get("titulo")):
        meta["titulo"] = valores["titulo"]
    return valores


def convert_one(pdf_path: str, md_path: str, spec: dict = None):
    spec = spec or metadatos.cargar_spec()
    print(f"[1/4] Leyendo PDF: {pdf_path}")
    raw = extract_pdf_text(pdf_path)
    if not raw.strip():
        print(f"  ⚠️  No se extrajo texto de {pdf_path}. ¿Es un PDF escaneado? "
              f"Ver sección 'Documentos escaneados' en el encabezado del script.")
        return

    print("[2/4] Limpiando encabezados/pies de página...")
    text = clean_text(raw)

    print("[3/4] Detectando metadatos y jerarquía normativa...")
    meta = detect_metadata(text)
    valores = resolver_metadatos(meta, pdf_path, spec)
    preamble, blocks, firmas_block = parse_document(text, meta)

    if not blocks:
        print(f"  ⚠️  No se reconocieron artículos en {pdf_path}. "
              f"Revisa manualmente el patrón de 'ARTÍCULO' en este documento; "
              f"puede tener un formato distinto (ej. 'Artículo Primero').")

    print(f"[4/4] Escribiendo Markdown: {md_path}")
    md = build_markdown(meta, preamble, blocks, os.path.basename(pdf_path), firmas_block)
    md = finalizar_markdown(metadatos.reemplazar_front_matter(md, valores))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    todo_count = md.count("TODO [REVISAR]") + md.count("[REVISAR")
    print(f"  ✅ Listo. Campos/bloques marcados para revisión manual: {todo_count}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = extraer_opciones_salida(extraer_perfiles_fuente(sys.argv[1:]))
    ruta_spec = None
    if "--metadatos" in args:
        i = args.index("--metadatos")
        ruta_spec = args[i + 1]
        args = args[:i] + args[i + 2:]
    spec = metadatos.cargar_spec(ruta_spec)
    src = args[0]
    dst = args[1] if len(args) > 1 else None

    if os.path.isdir(src):
        # Modo lote: carpeta de entrada -> carpeta de salida
        out_dir = dst or (src.rstrip("/") + "_md")
        os.makedirs(out_dir, exist_ok=True)
        pdfs = sorted(glob.glob(os.path.join(src, "*.pdf")))
        if not pdfs:
            print(f"No se encontraron .pdf en {src}")
            sys.exit(1)
        print(f"Procesando {len(pdfs)} documentos de '{src}' -> '{out_dir}'\n")
        for pdf in pdfs:
            name = os.path.splitext(os.path.basename(pdf))[0]
            md_path = os.path.join(out_dir, f"{name}.md")
            try:
                convert_one(pdf, md_path, spec)
            except Exception as e:
                print(f"  ❌ Error procesando {pdf}: {e}")
            print()
    else:
        if not dst:
            dst = os.path.splitext(src)[0] + ".md"
        convert_one(src, dst, spec)


if __name__ == "__main__":
    main()
