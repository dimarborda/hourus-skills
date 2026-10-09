# Formato del Markdown de salida

Todos los conversores (`motor_normativo.py`, `procesar_lote.py`,
`guias_tecnicas.py`) producen el mismo lenguaje de marcado, así que el
pipeline de indexación no necesita saber qué ruta generó cada archivo. Lo
único que varía por proyecto es **qué campos lleva el front-matter**, y eso
lo define el usuario en `metadatos.json`.

Con `--sin-chunks` (cuando solo se quiere convertir, sin RAG) se omiten las
marcas `<!-- CHUNK … -->` / `<!-- /CHUNK -->` y las líneas `**Ruta:** …`; el
resto del formato es idéntico.

## Estructura

```markdown
---
titulo: "Manual de Operaciones"
tipo_documento: "Manual de procesos"
autor: "TODO [REVISAR]"
fecha_publicacion: "2024-05"
descripcion: "TODO [REVISAR]"
idioma: "es"
etiquetas: ["procesos", "calidad"]
cliente: "Acme S.A."
archivo_origen: "manual-operaciones-2024.pdf"
fecha_conversion: "2026-10-09"
---

# Manual de Operaciones

**Ruta:** Manual de Operaciones

<!-- CHUNK id="manual-de-operaciones-introduccion" ruta="Manual de Operaciones > Introducción" -->

## Introducción

**Ruta:** Manual de Operaciones > Introducción

...texto verbatim...

<!-- /CHUNK -->
```

## Front-matter configurable (`metadatos.py`)

### Perfiles base

| Perfil | Campos |
|---|---|
| `minimo` | titulo, tipo_documento, fecha_publicacion |
| `general` *(por defecto)* | titulo, tipo_documento, autor, fecha_publicacion, descripcion, idioma (`"es"`), etiquetas (`[]`), fuente |
| `normativo` | titulo, tipo_documento, numero, anio, fecha_expedicion, descripcion, emisor, firmante, modifica, deroga, jurisdiccion, fuente, etiquetas |

Siempre se añaden `archivo_origen` y `fecha_conversion` (trazabilidad), salvo
que la spec los ponga en `false`.

### Spec (`metadatos.json`)

```json
{
  "perfil": "general",
  "campos": {
    "tipo_documento": "Manual de procesos",
    "cliente": "Acme S.A.",
    "version": null,
    "fuente": false
  },
  "documentos": {
    "manual-operaciones-2024.pdf": {"version": "3.1"}
  }
}
```

| Valor | Efecto |
|---|---|
| `"auto"` | Lo rellena el conversor si lo detecta; si no, `TODO [REVISAR]` |
| `null` | Pendiente: `TODO [REVISAR]` para completar a mano |
| `false` | El campo no se escribe |
| texto, número, lista, objeto | Se escribe literal |

Orden: primero los campos del perfil, luego los nuevos de `campos`. Los
valores de `documentos["archivo.pdf"]` tienen prioridad sobre `campos`. Si
el usuario fija `titulo`, ese título se usa también en el `#` y en las rutas
de los chunks.

### Qué detecta cada ruta (campos `"auto"`)

| Origen | Campos |
|---|---|
| Propiedades del PDF (todas las rutas) | `titulo` (Title), `autor` (Author), `fecha_creacion`, `paginas` |
| Ruta normativa (texto) | `titulo`, `tipo_documento`, `numero`, `anio`, `fecha_expedicion`, `fecha_publicacion` (= expedición), `descripcion` (el "Por el cual…"), `firmante`, `fuente` (solo si un perfil de fuente cargado con `--perfil-fuente` reconoce el texto) |
| Ruta guías (índice JSON) | Cualquier clave del índice con el mismo nombre del campo |

Lo detectado en el texto/índice tiene prioridad sobre las propiedades del PDF
(que a menudo traen títulos basura como "Microsoft Word - doc1.docx"; los
más obvios se descartan).

Los valores se escriben en sintaxis JSON (subconjunto válido de YAML): textos
entre comillas dobles con escapes correctos, listas `[...]`, números sin comillas.

### Cambiar metadatos sin reconvertir

```bash
python3 scripts/metadatos.py aplicar doc.md metadatos.json [--pdf doc.pdf]
```

Los valores ya presentes en el front-matter cuentan como "detectados" para
los campos `"auto"`. Los campos normativos que nunca estuvieron en el `.md`
solo se recuperan reconvirtiendo el PDF.

## Cuerpo

| Elemento | Para qué sirve |
|---|---|
| **Encabezados `#`–`#####`** | Reflejan la jerarquía real (Título → Capítulo → Sección → Artículo, o sección del índice en guías). |
| **`**Ruta:** A > B > C`** | Breadcrumb al inicio de cada bloque: ningún chunk pierde su contexto cuando se recupera solo. |
| **`<!-- CHUNK id="…" ruta="…" -->` … `<!-- /CHUNK -->`** | Unidad de indexación. El splitter debe cortar **exactamente** en estas marcas. Nunca parten un artículo o párrafo por la mitad. |
| **Sub-chunks `-p1`, `-p2`, "(parte i/n)"** | Bloques > `MAX_CHUNK_CHARS` (3500) se subdividen respetando numerales y párrafos. |
| **`[REVISAR: …]`** | Bloque vacío o no reconocido. |

## Cómo indexarlo

Usa el contenido entre `<!-- CHUNK -->` y `<!-- /CHUNK -->` como texto de
cada chunk; el atributo `ruta` y el front-matter como metadatos de filtrado.
