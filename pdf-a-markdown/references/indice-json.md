# Índice JSON para `guias_tecnicas.py`

`guias_tecnicas.py` no adivina la estructura de una guía/manual: la lee de un
índice JSON (uno por documento). El resto —columnas, limpieza, chunking— es
automático. Plantilla: [`../assets/plantilla.indice.json`](../assets/plantilla.indice.json).

**Lo genera `generar_indice.py`, no el usuario.** El script prueba, en orden:

| Vía | Cuándo funciona | Qué revisar |
|---|---|---|
| Marcadores del PDF | PDF exportados con marcadores (Word, InDesign) | `_revisar` avisa si el índice impreso trae secciones que faltan en los marcadores |
| Tabla de contenido impresa | Índice con puntos guía y número de página ("…… 12", "Pág. 12"), también a dos columnas y en pliegos dobles; o sin puntos ("Capítulo 3  El viaje  45") en páginas encabezadas "Contenido"/"Índice" | Títulos en MAYÚSCULAS; páginas listadas en `_revisar` (portadillas en imagen); subsecciones sin numerar que se colaron |
| Encabezado corrido | Sin índice, pero cada página abre con "Documento — Capítulo — Título", o alterna título del libro / título del capítulo | Que ninguna sección quede partida en dos |

Las tres dejan `offset_pagina_impresa: 0`. Cada sección generada desde el
índice impreso guarda `_pagina_en_indice_impreso` como referencia. Solo si el
script escribe un esqueleto (`TODO [REVISAR]`) hay que armar el índice a mano
con las reglas de abajo; en ese caso lo arma el agente leyendo el documento.

## Campos

```json
{
  "titulo": "Título completo del documento",
  "offset_pagina_impresa": 1,
  "tipo_documento": "Manual",
  "autor": "…",
  "fecha_publicacion": "AAAA-MM",
  "secciones": [
    {"nivel": 1, "numero": null, "titulo": "Introducción", "pagina_impresa_inicio": 7},
    {"nivel": 1, "numero": "1",  "titulo": "Primer capítulo", "pagina_impresa_inicio": 9}
  ]
}
```

- **Obligatorios:** `titulo`, `offset_pagina_impresa`, `secciones`.
- **Opcionales:** cualquier otra clave (`tipo_documento`, `autor`,
  `fecha_publicacion`, `version`…). No deciden qué aparece en el front-matter
  —eso lo decide `metadatos.json`—, solo aportan el valor de los campos
  marcados `"auto"` con el mismo nombre.
- Cada sección va desde su `pagina_impresa_inicio` hasta la página anterior a
  la siguiente sección; la última llega al final del PDF.
- Con `numero`, el encabezado sale como `Sección N – Título`; con `null`, solo el título.
- Las claves que empiezan por `_comentario` son documentación libre (el script las ignora).
  Úsalas para dejar constancia de cómo verificaste el offset.

## El offset (la fuente de error n.º 1)

```
pagina_pdfplumber (0-based) = pagina_impresa_inicio - offset_pagina_impresa
```

Cómo calcularlo: abre 2-3 páginas en puntos distintos del documento, lee el
número impreso en el pie y compáralo con su índice 0-based. Típicamente
`offset = 1` (la portada no lleva número), pero hay documentos con páginas
de créditos sin numerar.

**Si la numeración impresa tiene saltos** (p. ej. apéndices con una página
divisoria sin número), no busques dos offsets: usa `offset_pagina_impresa: 0`
y pon directamente el índice 0-based de pdfplumber en cada
`pagina_impresa_inicio`. Así se resolvió un reglamento técnico con
apéndices separados por páginas divisorias.

`generar_indice.py` ya hace esto (offset 0) en sus tres vías.

## Qué incluir y qué no

- **Incluye** solo secciones de primer nivel con contenido desarrollado (el
  chunk es la sección; las largas se subdividen solas).
- **Quita** entradas que no son contenido o que apuntan a la misma página
  que la siguiente sección ("Contenido", "Lista de tablas", "Figuras") —
  salvo que el usuario quiera conservar la tabla de contenido como chunk.
- Bibliografía y anexos: inclúyelos como secciones propias si aportan al
  RAG; si un anexo es un formulario en imagen, saldrá casi vacío (repórtalo).
- Las páginas de inicio deben ser **estrictamente crecientes**; si no, el
  rango de alguna sección queda vacío.
