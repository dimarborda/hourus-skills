#!/usr/bin/env bash
# install.sh — instala skills de hourus-skills para un agente de IA.
#
# Uso:
#   ./install.sh                         # todas las skills -> ~/.claude/skills (global, Claude Code)
#   ./install.sh pdf-a-markdown          # solo esa skill
#   ./install.sh --proyecto /ruta/repo   # -> /ruta/repo/.claude/skills (solo ese proyecto)
#   ./install.sh --destino /otra/carpeta # -> carpeta de skills de otro agente
#   ./install.sh --copiar                # copia en vez de enlace simbólico
#   ./install.sh --deps                  # además instala dependencias Python (requirements.txt)
#   ./install.sh --listar                # lista las skills disponibles y sale
#   ./install.sh --desinstalar [skill]   # quita los enlaces/copias del destino
#
# Por defecto crea ENLACES SIMBÓLICOS: al actualizar este repo (git pull),
# las skills instaladas se actualizan solas.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="$HOME/.claude/skills"
MODO="enlace"
DEPS=0
ACCION="instalar"
SKILLS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proyecto)    DESTINO="$2/.claude/skills"; shift 2 ;;
    --destino)     DESTINO="$2"; shift 2 ;;
    --copiar)      MODO="copia"; shift ;;
    --deps)        DEPS=1; shift ;;
    --listar)      ACCION="listar"; shift ;;
    --desinstalar) ACCION="desinstalar"; shift ;;
    -h|--help)     sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)            echo "Opción desconocida: $1" >&2; exit 1 ;;
    *)             SKILLS+=("$1"); shift ;;
  esac
done

# Una skill = carpeta de primer nivel con SKILL.md
disponibles=()
for d in "$REPO"/*/; do
  [[ -f "$d/SKILL.md" ]] && disponibles+=("$(basename "$d")")
done

if [[ "$ACCION" == "listar" ]]; then
  for s in "${disponibles[@]}"; do
    desc=$(sed -n 's/^description: //p' "$REPO/$s/SKILL.md" | head -1 | cut -c1-110)
    echo "- $s: $desc…"
  done
  exit 0
fi

[[ ${#SKILLS[@]} -eq 0 ]] && SKILLS=("${disponibles[@]}")

for s in "${SKILLS[@]}"; do
  if [[ ! -f "$REPO/$s/SKILL.md" ]]; then
    echo "❌ '$s' no es una skill de este repo. Disponibles: ${disponibles[*]}" >&2
    exit 1
  fi
done

mkdir -p "$DESTINO"

for s in "${SKILLS[@]}"; do
  objetivo="$DESTINO/$s"
  if [[ "$ACCION" == "desinstalar" ]]; then
    if [[ -L "$objetivo" ]]; then rm "$objetivo"; echo "🗑  $s (enlace) quitado de $DESTINO"
    elif [[ -d "$objetivo" ]]; then echo "⚠️  $objetivo es una copia; bórrala a mano si quieres quitarla."
    else echo "·  $s no estaba instalada en $DESTINO"; fi
    continue
  fi

  if [[ -e "$objetivo" || -L "$objetivo" ]]; then
    if [[ -L "$objetivo" ]]; then
      rm "$objetivo"
    else
      echo "⚠️  $objetivo ya existe y no es un enlace: no lo toco (muévelo o usa otro destino)." >&2
      continue
    fi
  fi

  if [[ "$MODO" == "enlace" ]]; then
    ln -s "$REPO/$s" "$objetivo"
  else
    cp -R "$REPO/$s" "$objetivo"
  fi
  echo "✅ $s -> $objetivo ($MODO)"

  if [[ "$DEPS" == 1 && -f "$REPO/$s/requirements.txt" ]]; then
    echo "   Instalando dependencias Python de $s..."
    if ! python3 -m pip install -q -r "$REPO/$s/requirements.txt"; then
      echo "   ⚠️  pip falló (¿Python gestionado por el sistema?). Opciones:" >&2
      echo "      python3 -m pip install --user -r $REPO/$s/requirements.txt" >&2
      echo "      o usar un entorno virtual (python3 -m venv .venv)." >&2
    fi
  fi
done

[[ "$ACCION" == "instalar" ]] && echo "Listo. Reinicia la sesión del agente para que detecte las skills nuevas."
