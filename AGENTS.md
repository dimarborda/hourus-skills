# AGENTS.md — instrucciones para agentes de IA

Este repositorio (**hourus-skills**) contiene skills para agentes de IA del
equipo Hourus. Si eres un agente y llegaste aquí (porque un usuario te pidió
"instala la skill X", "instala las skills de Hourus" o abrió esta carpeta),
sigue estas instrucciones. El índice para personas está en [README.md](README.md);
el registro legible por máquina, en [skills.json](skills.json).

## 1. Ver qué skills hay

```bash
./install.sh --listar
```

Una skill = carpeta de primer nivel con un `SKILL.md`.

## 2. Instalar

Elige el destino según tu entorno y **confirma con el usuario** si no es obvio
(global vs. solo un proyecto):

| Agente / caso | Comando |
|---|---|
| Claude Code, para todas las sesiones del usuario | `./install.sh` (→ `~/.claude/skills/`) |
| Claude Code, solo para un proyecto | `./install.sh --proyecto /ruta/del/proyecto` (→ `.claude/skills/`) |
| Otro agente con carpeta de skills propia | `./install.sh --destino /ruta/de/skills` |
| Una skill concreta | añade su nombre: `./install.sh pdf-a-markdown` |
| Agente sin soporte de skills | No instales nada: añade al `AGENTS.md`/instrucciones del proyecto una línea como *"Para convertir PDF a Markdown, lee y sigue `<ruta>/pdf-a-markdown/SKILL.md`"* |

Detalles:
- Por defecto se crean **enlaces simbólicos**, así un `git pull` de este repo
  actualiza las skills instaladas. Usa `--copiar` si el destino no puede
  apuntar fuera (contenedores, otra máquina, repos que se publican).
- El script **no sobrescribe** carpetas existentes que no sean enlaces.
- `--deps` instala también las dependencias Python de cada skill
  (`requirements.txt`). Si `pip` falla por Python gestionado por el sistema,
  usa `--user` o un entorno virtual; **no uses `sudo`** sin que el usuario lo pida.
- Dependencias de sistema opcionales (p. ej. OCR con Homebrew) están en
  `skills.json` → `dependencias_sistema_opcionales`. Instálalas solo si el
  usuario las necesita, y pide confirmación antes.

## 3. Verificar

```bash
ls -la ~/.claude/skills/            # o el destino que usaste
python3 pdf-a-markdown/scripts/metadatos.py perfiles   # comando de skills.json → "verificacion"
```

Luego dile al usuario que **reinicie la sesión del agente** para que detecte
las skills nuevas, y cómo activarlas (en lenguaje natural, p. ej. "convierte
este PDF a markdown").

## 4. Desinstalar

```bash
./install.sh --desinstalar [skill] [--proyecto RUTA | --destino DIR]
```

## 5. Usar una skill sin instalarla

Lee `<skill>/SKILL.md` y sigue sus pasos; las rutas `SKILL_DIR/...` son
relativas a la carpeta de la skill.

## 6. Si vas a crear o modificar una skill aquí

Sigue las convenciones de [README.md](README.md#convenciones-para-nuevas-skills)
y, al terminar:
1. Añade la fila al índice de `README.md`.
2. Añade la entrada a `skills.json` (sube `version` si modificaste una existente).
3. Comprueba que `./install.sh --listar` la muestra.
