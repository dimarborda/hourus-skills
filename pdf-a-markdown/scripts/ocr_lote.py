#!/usr/bin/env python3
"""
ocr_lote.py
================
Prepara PDF escaneados (sin texto seleccionable) de "PDF/Requiere-revision/"
para que motor_normativo.py / procesar_lote.py puedan
convertirlos. No reemplaza a ninguno de esos dos scripts ni reimplementa su
parseo: solo le agrega al PDF una capa de texto invisible (OCR) y lo deja
listo para el pipeline normal.

QUÉ HACE
--------
1. Recibe uno o más nombres de archivo que deben existir en
   "PDF/Requiere-revision/" (ver USO). NO recorre la carpeta completa por sí
   solo — a propósito: no todo lo que cae ahí es un PDF escaneado válido
   para OCR (ver "QUÉ NO HACE").
2. Para cada archivo, corre `ocrmypdf` (idioma español, con enderezado
   "--deskew" y limpieza "--clean" para escaneos torcidos o con ruido de
   fondo) generando una copia con texto embebido.
3. Verifica el resultado reutilizando la misma función que usa
   motor_normativo.py (extract_pdf_text) para confirmar que ahora sí
   se puede extraer texto real, no solo asumir que el OCR funcionó porque no
   hubo error.
4. Si el texto se extrae correctamente:
   - Mueve la copia OCR (con texto embebido) a "PDF/No procesados/",
     reemplazando al PDF original de "PDF/Requiere-revision/" (que ya no
     hace falta conservar aparte: la copia OCR contiene las mismas imágenes
     de página, solo que ahora también tiene texto seleccionable encima).
   - Dentro de PDF/No procesados/ queda igual que cualquier PDF nuevo: el
     siguiente paso es correr `procesar_lote.py` para generar su .md.
   - Registra el éxito en PDF/Requiere-revision/NOTAS.md.
5. Si aun con OCR no se puede extraer texto (escaneo ilegible, página en
   blanco, etc.), dice el archivo en su lugar y registra el motivo en
   NOTAS.md para revisión humana (no reintenta indefinidamente).

QUÉ NO HACE (y por qué)
------------------------
- No decide por su cuenta cuáles PDF de Requiere-revision "merecen" OCR.
  Un PDF puede no tener texto por estar escaneado (candidato válido) o por
  ser, simplemente, el archivo equivocado en el catálogo (ej. un
  póster/infográfico en vez del documento normativo real — caso real
  documentado en references/lecciones-aprendidas.md). Distinguir esos dos casos
  requiere mirar el PDF, así que este script exige que le pasen los nombres
  explícitamente en vez de barrer la carpeta entera.
- No corre motor_normativo.py ni procesar_lote.py por sí mismo:
  solo le agrega texto al PDF; la conversión a Markdown sigue siendo un paso
  aparte y deliberado.
- No reintenta con distintos ajustes de OCR automáticamente si el primer
  intento falla (ej. no prueba otro idioma o mayor resolución): lo reporta
  para que un humano decida el siguiente paso.

USO
---
    python3 ocr_lote.py documento-escaneado.pdf
    python3 ocr_lote.py archivo1.pdf archivo2.pdf

Requisitos (además de los de motor_normativo.py):
    brew install tesseract ghostscript qpdf unpaper
    pip install ocrmypdf --break-system-packages
"""

import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor_normativo as motor

BASE_DIR = os.path.abspath(os.environ.get("PDF_MD_WORKDIR", os.getcwd()))
DIR_REVISION = os.path.join(BASE_DIR, "PDF", "Requiere-revision")
DIR_NO_PROCESADOS = os.path.join(BASE_DIR, "PDF", "No procesados")
NOTAS_PATH = os.path.join(DIR_REVISION, "NOTAS.md")

# Idioma(s) de OCR. Por defecto español con inglés de respaldo (sellos,
# membretes o fragmentos en inglés). Para documentos en otros idiomas,
# cámbialo con la variable de entorno PDF_MD_OCR_LANG (códigos de
# Tesseract, p. ej. "por", "fra+eng").
OCR_LANG = os.environ.get("PDF_MD_OCR_LANG", "spa+eng")


def registrar_nota(archivo: str, motivo: str, sugerencia: str):
    os.makedirs(DIR_REVISION, exist_ok=True)
    es_nuevo = not os.path.exists(NOTAS_PATH)
    with open(NOTAS_PATH, "a", encoding="utf-8") as f:
        if es_nuevo:
            f.write("# Notas de revisión manual — PDF/Requiere-revision\n\n")
        f.write(f"## {archivo}\n\n")
        f.write(f"- **Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"- **Motivo:** {motivo}\n")
        f.write(f"- **Sugerencia:** {sugerencia}\n\n")


def ocr_uno(nombre: str) -> dict:
    origen = os.path.join(DIR_REVISION, nombre)
    if not os.path.isfile(origen):
        return {"estado": "no_encontrado",
                "motivo": f"No existe '{nombre}' en PDF/Requiere-revision/."}

    salida = os.path.join(DIR_REVISION, f"_ocr_{nombre}")
    if os.path.exists(salida):
        os.remove(salida)

    resultado = subprocess.run(
        [
            "ocrmypdf", "--language", OCR_LANG, "--deskew", "--clean",
            "--optimize", "1", origen, salida,
        ],
        capture_output=True, text=True,
    )

    if resultado.returncode == 6:
        # PriorOcrFoundError: la página ya trae una capa de texto (de un OCR
        # o escaneo anterior) y ocrmypdf aborta SIN escribir `salida`, para
        # no encimar dos capas de OCR por accidente. El comentario anterior
        # ("6 = ya tenía texto") lo trataba como éxito y seguía derecho a
        # extraer texto de `salida` — pero ese archivo nunca se crea en este
        # código, así que siempre fallaba con FileNotFoundError (visto con
        # una circular escaneada). Además, "ya tenía texto" no es lo mismo que
        # "el texto es utilizable": si el PDF llegó a Requiere-revision/ es
        # justamente porque su texto (extraído o vía OCR previo) no sirvió —
        # en ese mismo caso, la capa de texto previa daba basura como
        # nombres propios sin tildes o "(cid:9)" de glifos mal mapeados. Se reintenta forzando el OCR (--force-ocr: rasteriza la
        # página ignorando el texto previo y OCRea de cero) en vez de
        # aceptar esa capa mala como si fuera buena.
        resultado = subprocess.run(
            [
                "ocrmypdf", "--language", OCR_LANG, "--deskew", "--clean",
                "--optimize", "1", "--force-ocr", origen, salida,
            ],
            capture_output=True, text=True,
        )

    if resultado.returncode != 0:
        motivo = f"ocrmypdf falló (código {resultado.returncode}): {resultado.stderr.strip()[-500:]}"
        registrar_nota(
            nombre, motivo,
            "Revisar manualmente el PDF y el mensaje de error de ocrmypdf. "
            "Puede requerir instalar una dependencia faltante o ajustar el "
            "comando (ver docstring de este script)."
        )
        if os.path.exists(salida):
            os.remove(salida)
        return {"estado": "error_ocr", "motivo": motivo}

    texto = motor.extract_pdf_text(salida)
    if not texto.strip():
        motivo = "Se aplicó OCR pero no se pudo extraer texto utilizable (escaneo ilegible o páginas en blanco)."
        registrar_nota(
            nombre, motivo,
            "Revisar visualmente la calidad del escaneo original. Puede "
            "necesitar mayor resolución de escaneo o esta herramienta no es "
            "suficiente para este documento."
        )
        os.remove(salida)
        return {"estado": "sin_texto_tras_ocr", "motivo": motivo}

    os.makedirs(DIR_NO_PROCESADOS, exist_ok=True)
    destino = os.path.join(DIR_NO_PROCESADOS, nombre)
    os.replace(salida, destino)
    os.remove(origen)

    registrar_nota(
        nombre, f"OCR exitoso (ocrmypdf, idioma {OCR_LANG}).",
        f"Movido a PDF/No procesados/{nombre}. Correr "
        "`python3 procesar_lote.py` para generar su Markdown."
    )
    return {"estado": "ok", "caracteres": len(texto)}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    for nombre in sys.argv[1:]:
        print(f"→ {nombre}")
        resultado = ocr_uno(nombre)
        estado = resultado["estado"]
        if estado == "ok":
            print(f"  ✅ OCR exitoso ({resultado['caracteres']} caracteres extraídos). "
                  f"Movido a PDF/No procesados/{nombre}.")
        elif estado == "no_encontrado":
            print(f"  ❌ {resultado['motivo']}")
        else:
            print(f"  ⚠️  {resultado['motivo']}")
        print()

    print("Siguiente paso: python3 procesar_lote.py")


if __name__ == "__main__":
    main()
