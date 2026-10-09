# Hourus Skills

Colección de **skills para agentes de IA** (Claude Code y compatibles) que
empaquetan procesos de trabajo del equipo **Hourus**: cada skill reúne
instrucciones, scripts y criterios de calidad probados en proyectos reales,
para que cualquier persona del equipo —o su agente— pueda repetir el proceso
sin redescubrirlo.

## ¿Qué es una skill?

Una carpeta con un `SKILL.md` (front-matter `name` + `description` y las
instrucciones) y, opcionalmente, recursos de apoyo:

```
<nombre-skill>/
├── SKILL.md         # cuándo se activa y qué pasos sigue el agente
├── scripts/         # código determinístico que el agente ejecuta
├── references/      # documentación que se carga solo cuando hace falta
├── assets/          # plantillas y ejemplos
└── requirements.txt # dependencias (si las hay)
```

El agente lee el `description` para decidir cuándo usarla y solo carga el
resto cuando la tarea lo requiere.

Archivos del repositorio:

| Archivo | Para quién | Qué contiene |
|---|---|---|
| `README.md` | Personas | Contexto e índice de skills |
| `AGENTS.md` / `CLAUDE.md` | Agentes | Cómo instalar, verificar, usar y crear skills |
| `skills.json` | Agentes / scripts | Registro: versión, dependencias, comando de verificación |
| `install.sh` | Ambos | Instalador (enlace o copia, global, por proyecto o destino libre) |

## Índice de skills

| Skill | Para qué sirve | Origen | Estado |
|---|---|---|---|
| [`pdf-a-markdown`](pdf-a-markdown/SKILL.md) | Convertir PDF (normas, guías, manuales, informes, escaneos) a Markdown estructurado y listo para RAG: diagnóstico automático de la ruta, front-matter con metadatos que el agente propone sin frenar la conversión (perfiles `general`, `normativo`, `minimo` + campos propios), motor por artículos, guías a columnas con índice JSON generado automáticamente (marcadores, tabla de contenido o encabezado corrido), OCR, extracción de tablas, perfiles de fuente opcionales y checklist de calidad. Agnóstica a país, portal y organización. | Pipeline de conversión de normas y guías técnicas para RAG | ✅ v1.4 |

<!-- Al agregar una skill nueva, añade una fila a esta tabla y una entrada en skills.json. -->

## Instalación

### Pídeselo a tu agente (recomendado)

Copia esto en Claude Code (u otro agente):

> Instala las skills de Hourus de https://github.com/dimarborda/hourus-skills siguiendo su `AGENTS.md`.

O clónalo tú primero:

```bash
git clone https://github.com/dimarborda/hourus-skills.git
```

Un agente que abre esta carpeta lee [`AGENTS.md`](AGENTS.md) (Claude Code
también vía [`CLAUDE.md`](CLAUDE.md)) con los pasos: elegir destino, instalar,
verificar y desinstalar. El registro legible por máquina está en
[`skills.json`](skills.json).

### A mano

```bash
./install.sh --listar                       # qué skills hay
```

```bash
./install.sh --deps                         # todas, para todas tus sesiones de Claude Code (~/.claude/skills)
```

```bash
./install.sh pdf-a-markdown --proyecto /ruta/del/proyecto   # una skill, solo para un proyecto
```

Crea enlaces simbólicos (un `git pull` aquí actualiza las skills instaladas);
`--copiar` hace copias y `--destino DIR` instala para otro agente. Reinicia la
sesión del agente después de instalar.

## Convenciones para nuevas skills

1. **Una carpeta por skill**, nombre en `kebab-case` y en español.
2. **`description` orientada a la activación**: qué hace y con qué frases
   del equipo debe dispararse.
3. **`SKILL.md` breve** (< ~250 líneas): flujo de decisión y comandos. El
   detalle va en `references/`.
4. **Rutas relativas a la skill** (`SKILL_DIR/scripts/...`) y al directorio
   de trabajo del usuario; nada de rutas absolutas de una máquina concreta.
5. **Scripts determinísticos y verificables**: preferir código a
   instrucciones cuando el paso es mecánico; documentar en el propio script
   qué hace y qué *no* hace.
6. **Registrar lecciones aprendidas** de los casos reales que motivaron cada
   decisión de diseño.
7. **Actualizar el índice** de este README y `skills.json`.

## Licencia

[MIT](LICENSE).
