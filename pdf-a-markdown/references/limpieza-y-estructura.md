# Limpieza y estructura del Markdown

Reglas de limpieza y estructura para el `.md` generado. Aplícalas después
de la conversión, sobre el `.md` generado, **sin alterar nunca**:

1. El front-matter YAML (`--- … ---` al inicio).
2. Las marcas `<!-- CHUNK id="…" ruta="…" -->` / `<!-- /CHUNK -->`.
3. Las líneas `**Ruta:** …`.
4. Las palabras y el sentido del texto original (nada de resumir ni parafrasear).

Para cambios repetitivos sobre un documento grande, escribe un script de
reemplazos acotado a ese documento (regex con patrones literales del
membrete real) en vez de editar a mano; guárdalo junto al `.md` si el
documento se va a reprocesar.

## 1. Ruido de página

- Elimina encabezados y pies repetidos en cada página: nombre de la entidad,
  lemas institucionales, códigos de formato (`TdR - 014`), avisos legales del
  portal, URLs del pie, números de página sueltos.
  El motor normativo ya quita los genéricos (`FOOTER_HEADER_PATTERNS` en
  `motor_normativo.py`: números de página, "Página N de M", "Hoja N de M").
  Los de un portal o publicador concreto van en un **perfil de fuente**
  (`--perfil-fuente`, ver [perfiles-fuente.md](perfiles-fuente.md)), no en
  el código.
- Elimina encabezados falsos que el OCR crea a partir de ruido
  (`## 18 AUTOR. 2004.`, `## 3 SIGLA-ENTIDAD`).
- Reunifica oraciones cortadas por salto de página.

## 2. Llamadas a nota al pie

Quita llamadas numéricas coladas en el cuerpo (`[12]`, `I5l`, `18)`, `°`
sueltos) **solo cuando son llamadas**, no cifras reales: revisa el contexto
— un regex ciego borra números legítimos ("18) años", "artículo 12]").
Notas sustantivas: intégralas entre paréntesis o al final de la sección.

## 3. Jerarquía de encabezados

| Markdown | Nivel | Ejemplo |
|---|---|---|
| `#` | Documento | `# TÍTULO A — Requisitos generales…` |
| `##` | Capítulo | `## Capítulo A.1 — Introducción` |
| `###` | Sección / artículo principal | `### A.1.1 — Normas sismo resistentes` |
| `####` | Subsección | `#### A.1.1.1 — Requisitos mínimos` |
| `#####` | Numeral de detalle | `##### A.1.2.2.1 — Reducción del riesgo…` |

- Espacio obligatorio tras `#`, y `—` entre código y nombre.
- Elimina títulos duplicados en mayúsculas sueltas si ya están como encabezado o en la `**Ruta:**`.
- Numerales de detalle sin título propio: `**A.1.2.2.1** — texto…` en vez de encabezado.

## 4. Listas e incisos

```markdown
El diseño debe someterse a:

- (a) La Ley 100 de 1997,
- (b) La Ley 200 de 2008,
  - (1) Modificaciones posteriores
  - (2) Reglamentaciones adicionales
```

- Línea en blanco antes del primer ítem.
- Sub-incisos con 2 espacios de sangría.
- En glosarios o listas largas de conceptos, viñetas con línea en blanco entre
  ítems para que cada concepto quede como párrafo independiente.

## 5. Separadores

Las líneas `---` en el cuerpo pueden eliminarse: los límites semánticos ya
están en las marcas CHUNK. Solo el `---` del front-matter es obligatorio.

## 6. Tablas

Tablas Markdown reales (`| a | b |` + `|---|---|`), **100 % verbatim**:
mismos encabezados, unidades, celdas vacías y marcas `X`. No agregues,
supongas, combines ni omitas filas. Ver §6 del SKILL.md para extraerlas y
verificarlas.
