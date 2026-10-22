#!/usr/bin/env python3
"""
auditar.py
==========
Utilidades determinísticas de la skill auditoria-express-de-apps.
Solo usa la biblioteca estándar de Python 3 (>= 3.8).

SUBCOMANDOS
-----------
  iniciar --proyecto RUTA [--fecha AAAA-MM-DD] [--nombre "X"]
        Crea docs/auditoria/FECHA/plan.md y docs/06-lecciones-aprendidas.md (si
        no existen) y añade al CLAUDE.md del proyecto la regla de leer las
        lecciones. NO sobrescribe nada.
  escanear --proyecto RUTA [--fecha F] [--incluir-build] [--sin-historial] [--ci]
        Barrido estático: secretos por patrón (enmascarados), JWT service_role,
        .env versionados o no ignorados, NEXT_PUBLIC_ con nombre de secreto,
        tablas sin RLS, políticas abiertas, user_metadata en políticas,
        SECURITY DEFINER sin search_path, getSession() en servidor, Server
        Actions sin verificación visible, webhooks sin firma, source maps, canales
        Realtime públicos, subidas sin validar, endpoints costosos sin límite, permisos
        del agente, tokens en .mcp.json, CI/pruebas/runbook ausentes y la estructura
        del método; además, secretos en el CONTENIDO de todos los commits
        (--sin-historial lo omite). --incluir-build revisa también .next/static.
        Escribe docs/auditoria/FECHA/hallazgos-estatico.json. Con --ci no escribe
        nada y sale con 1 si hay críticos/altos no marcados aceptado/descartado.
  consolidar --proyecto RUTA [--fecha F]
        Valida los hallazgos-*.json de los equipos contra el esquema, fusiona
        duplicados (misma huella o 'relacionados'), compara con la auditoría
        anterior y con las lecciones (nuevo / reincidente / no reaparece) y
        escribe hallazgos.json e informe.md. Sale con 1 si hay errores de esquema.
  casos --proyecto RUTA [--fecha F] [--anexar] [--incluir-posibles]
        Convierte los hallazgos abiertos en casos UC-SEC / UC-CAL (casos-de-mejora.md,
        con el formato de docs/05) y UC-MET (casos-metodo.md). --anexar inserta la
        etapa de endurecimiento en docs/05-casos-de-uso.md si aún no está.
  lecciones --proyecto RUTA [--fecha F]
        Pasa el campo 'leccion' de los hallazgos no descartados a
        docs/06-lecciones-aprendidas.md, sin duplicar (las repetidas suman 'Veces').
  automatizar --proyecto RUTA [--escribir] [--publicas t1,t2]
        Para que las lecciones se cumplan solas: supabase/tests/00_auditoria_rls.test.sql
        (pgTAP: RLS en todas las tablas, search_path, security_invoker y acceso de anon
        y de un usuario ajeno por tabla), .github/workflows/auditoria.yml (barrido --ci,
        npm audit y supabase test db), .github/dependabot.yml, docs/incidentes/
        llave-filtrada.md y una copia de este script en scripts/auditoria/. Sin
        --escribir solo muestra qué haría. Solo regenera la prueba y la copia del script.
  estado --proyecto RUTA
        Historial de auditorías, abiertos por severidad y lecciones registradas.

QUÉ NO HACE
-----------
No modifica código, no llama a Vercel ni a Supabase, no hace peticiones de red
y nunca imprime un secreto completo. Sus reglas son heurísticas: los hallazgos
'posible' deben confirmarlos los equipos de agentes.
"""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PLANTILLAS = SKILL_DIR / "assets" / "plantillas"

SEVERIDADES = ["critica", "alta", "media", "baja", "info"]
CONFIANZAS = ["confirmado", "probable", "posible"]
ESTADOS = ["abierto", "descartado", "aceptado", "corregido"]
ALCANCES = ["proyecto", "metodo"]
CATEGORIAS_SEC = ["secretos", "rls", "auth", "entradas", "abuso", "configuracion", "despliegue",
                  "navegador", "proveedor", "dependencias", "privacidad", "cuentas", "agente"]
CATEGORIAS_CAL = ["metodologia", "buenas-practicas", "rendimiento", "operacion", "accesibilidad"]
CATEGORIAS = CATEGORIAS_SEC + CATEGORIAS_CAL
FIBONACCI = {1, 2, 3, 5, 8, 13}
ICONO = {"critica": "🟥", "alta": "🟧", "media": "🟨", "baja": "🟩", "info": "⬜"}
PRIORIDAD = {"critica": "🟥", "alta": "🟥", "media": "🟨", "baja": "🟩"}
DOCS_METODO = ["00-decisiones.md", "01-referente-conceptual.md", "02-referente-casos-de-uso.md",
               "03-diseno-visual.md", "04-conceptual.md", "05-casos-de-uso.md"]

EXCLUIR_DIRS = {"node_modules", ".git", ".next", ".vercel", "dist", "build", "out", "coverage",
                ".turbo", ".cache", "__pycache__", ".venv", "venv", ".temp", ".branches"}
EXT_CODIGO = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
EXT_TEXTO = EXT_CODIGO | {".json", ".sql", ".toml", ".yml", ".yaml", ".md", ".html", ".txt",
                          ".sh", ".py", ".env", ".example"}
OMITIR_ARCHIVOS = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"}
RE_ENV = re.compile(r"^\.env(\..+)?$")
RE_ENV_EJEMPLO = re.compile(r"\.(example|sample|template|dist)$")

# ------------------------------------------------------------------ reglas
# Metadatos fijos de cada regla; la detección solo aporta ubicación y extracto.
REGLAS = {
    "SEC-ENV-VERSIONADO": dict(
        severidad="critica", confianza="confirmado", categoria="secretos",
        titulo="Archivo .env versionado en git",
        impacto="Quien tenga acceso al repositorio (o a su historial) obtiene las llaves.",
        propuesta="git rm --cached del archivo, añadir .env* a .gitignore y ROTAR todas las llaves que contenía (borrar no basta: siguen en el historial).",
        leccion="Ningún .env* se versiona salvo .env.example sin valores; toda llave que pasó por git se rota.",
        esfuerzo=2, referencia="OWASP A02:2021"),
    "SEC-ENV-HISTORIAL": dict(
        severidad="critica", confianza="probable", categoria="secretos",
        titulo="Un archivo .env pasó por el historial de git",
        impacto="Las llaves de ese archivo siguen disponibles en commits anteriores.",
        propuesta="Rotar las llaves que contenía (Supabase, Vercel, pasarela, IA). Reescribir el historial es opcional y no sustituye la rotación.",
        leccion="Toda llave que pasó por git se rota, aunque el archivo ya no exista.",
        esfuerzo=2, referencia="OWASP A02:2021"),
    "SEC-ENV-NO-IGNORADO": dict(
        severidad="alta", confianza="confirmado", categoria="secretos",
        titulo=".env.local no está cubierto por .gitignore",
        impacto="El próximo 'git add .' sube las llaves al repositorio.",
        propuesta="Añadir '.env*' y '!.env.example' a .gitignore.",
        leccion=".gitignore cubre .env*, .vercel y supabase/.temp desde el primer commit.",
        esfuerzo=1, referencia="OWASP A05:2021"),
    "SEC-VERCEL-NO-IGNORADO": dict(
        severidad="media", confianza="confirmado", categoria="secretos",
        titulo=".vercel/ no está cubierto por .gitignore",
        impacto="'vercel pull' guarda variables de entorno en .vercel/; podrían versionarse.",
        propuesta="Añadir '.vercel' a .gitignore.",
        leccion=".gitignore cubre .env*, .vercel y supabase/.temp desde el primer commit.",
        esfuerzo=1, referencia="OWASP A05:2021"),
    "SEC-NEXT-PUBLIC": dict(
        severidad="critica", confianza="probable", categoria="secretos",
        titulo="Variable NEXT_PUBLIC_ con nombre de secreto",
        impacto="Todo NEXT_PUBLIC_ se incrusta en el JavaScript que descarga cualquier visitante.",
        propuesta="Renombrar sin prefijo NEXT_PUBLIC_, leerla solo en el servidor (Route Handler / Server Action con import 'server-only'), actualizarla en Vercel y rotar su valor.",
        leccion="Solo son NEXT_PUBLIC_ la URL de Supabase, la clave anon/publishable y claves públicas de terceros; todo lo demás vive en el servidor.",
        esfuerzo=2, referencia="OWASP A02:2021"),
    "SEC-PATRON": dict(
        severidad="critica", confianza="probable", categoria="secretos",
        titulo="Secreto escrito en un archivo del proyecto",
        impacto="La llave queda en el repositorio y, si el archivo llega al cliente, en el navegador.",
        propuesta="Mover el valor a una variable de entorno de servidor en Vercel, quitarlo del archivo y ROTAR la llave.",
        leccion="Ningún secreto se escribe en el código: va en variables de entorno del servidor.",
        esfuerzo=2, referencia="OWASP A02:2021"),
    "SEC-BUNDLE": dict(
        severidad="critica", confianza="confirmado", categoria="navegador",
        titulo="Secreto dentro del JavaScript que descarga el navegador",
        impacto="Cualquier visitante puede leer la llave desde las herramientas del navegador.",
        propuesta="ROTAR la llave ya; luego quitarla del código cliente o del prefijo NEXT_PUBLIC_ y redesplegar.",
        leccion="Antes de cada salida a producción se revisa el build (.next/static) en busca de secretos.",
        esfuerzo=2, referencia="OWASP A02:2021"),
    "SEC-JWT-SERVICE": dict(
        severidad="critica", confianza="confirmado", categoria="secretos",
        titulo="JWT con rol service_role escrito en un archivo",
        impacto="La service_role salta todas las políticas RLS: acceso total a la base de datos.",
        propuesta="Rotar la llave en Supabase (Settings → API keys), quitarla del archivo y usarla solo como variable de servidor.",
        leccion="La service_role nunca se escribe en archivos ni en variables públicas.",
        esfuerzo=2, referencia="OWASP A02:2021"),
    "SEC-JWT-ANON": dict(
        severidad="baja", confianza="probable", categoria="buenas-practicas",
        titulo="Clave anon de Supabase escrita en el código",
        impacto="No es secreta, pero cambiarla obliga a editar código y mezcla entornos.",
        propuesta="Leerla de NEXT_PUBLIC_SUPABASE_ANON_KEY (o PUBLISHABLE_KEY).",
        leccion="La configuración por entorno se lee de variables, nunca se escribe en el código.",
        esfuerzo=1, referencia=""),
    "SEC-LITERAL": dict(
        severidad="alta", confianza="posible", categoria="secretos",
        titulo="Valor literal asignado a una variable con nombre de secreto",
        impacto="Si es una llave real, queda en el repositorio.",
        propuesta="Confirmar si es real; si lo es, moverla a una variable de entorno de servidor y rotarla.",
        leccion="Ningún secreto se escribe en el código: va en variables de entorno del servidor.",
        esfuerzo=1, referencia="OWASP A02:2021"),
    "SEC-SERVICE-CLIENTE": dict(
        severidad="alta", confianza="probable", categoria="secretos",
        titulo="Componente cliente ('use client') referencia la llave secreta de Supabase",
        impacto="Si la variable llegara al bundle, saltaría RLS; además indica lógica privilegiada en el navegador.",
        propuesta="Mover esa lógica a una Server Action o Route Handler con import 'server-only' y verificación de sesión.",
        leccion="La service_role solo se usa en módulos de servidor marcados con import 'server-only'.",
        esfuerzo=3, referencia="OWASP A01:2021"),
    "SEC-SIN-SERVER-ONLY": dict(
        severidad="baja", confianza="posible", categoria="secretos",
        titulo="Módulo que usa la llave secreta sin import 'server-only'",
        impacto="Un componente cliente podría importarlo por error.",
        propuesta="Añadir import 'server-only' al inicio del módulo.",
        leccion="La service_role solo se usa en módulos de servidor marcados con import 'server-only'.",
        esfuerzo=1, referencia=""),
    "RLS-SIN-RLS": dict(
        severidad="critica", confianza="probable", categoria="rls",
        titulo="Tabla de public sin enable row level security en ninguna migración",
        impacto="Con la clave pública (que está en el navegador) cualquiera lee y modifica la tabla.",
        propuesta="Nueva migración: alter table <tabla> enable row level security; y políticas según la columna 'qué NO puede hacer' de los actores. Confirmar en remoto (consulta 1 de B2).",
        leccion="Toda tabla nueva lleva enable row level security en la misma migración que la crea.",
        esfuerzo=3, referencia="OWASP A01:2021"),
    "RLS-OTRA-MIGRACION": dict(
        severidad="baja", confianza="probable", categoria="metodologia",
        titulo="RLS activado en una migración distinta a la que crea la tabla",
        impacto="Entre una migración y otra la tabla existe sin RLS; el método exige la misma migración.",
        propuesta="En tablas nuevas, activar RLS en la misma migración. Para esta, basta con verificar que el remoto tiene RLS.",
        leccion="Toda tabla nueva lleva enable row level security en la misma migración que la crea.",
        esfuerzo=1, referencia=""),
    "RLS-DESACTIVADO": dict(
        severidad="critica", confianza="probable", categoria="rls",
        titulo="Migración que desactiva RLS",
        impacto="La tabla queda abierta a cualquiera con la clave pública.",
        propuesta="Nueva migración que vuelva a activar RLS y cree las políticas que faltaban.",
        leccion="RLS no se desactiva nunca, ni 'para probar': si algo falla, falta una política.",
        esfuerzo=2, referencia="OWASP A01:2021"),
    "RLS-POLITICA-ABIERTA": dict(
        severidad="media", confianza="posible", categoria="rls",
        titulo="Política con using (true) o with check (true)",
        impacto="Permite la operación a todos los roles de la política; aceptable solo en catálogos públicos.",
        propuesta="Restringir por auth.uid() o por membresía; si es un catálogo público, documentarlo en 04-conceptual.md.",
        leccion="Cada política dice quién puede, no 'todos'; las excepciones públicas se documentan.",
        esfuerzo=2, referencia="OWASP A01:2021"),
    "RLS-USER-METADATA": dict(
        severidad="alta", confianza="probable", categoria="rls",
        titulo="Política o función que confía en user_metadata",
        impacto="El usuario puede editar su propio user_metadata y darse permisos.",
        propuesta="Tomar roles de la tabla membresias o de app_metadata.",
        leccion="Los permisos nunca salen de user_metadata: salen de membresias o app_metadata.",
        esfuerzo=3, referencia="OWASP A01:2021"),
    "RLS-DEFINER-SEARCH-PATH": dict(
        severidad="media", confianza="probable", categoria="rls",
        titulo="Función SECURITY DEFINER sin search_path fijo",
        impacto="Puede ejecutarse con objetos suplantados en otro esquema; si está en public, es invocable por RPC.",
        propuesta="Añadir 'set search_path = ''' (y calificar los objetos con su esquema); revocar execute a anon si no la necesita.",
        leccion="Toda función security definer lleva set search_path = '' y permisos de ejecución explícitos.",
        esfuerzo=1, referencia="OWASP A05:2021"),
    "RLS-VISTA-SIN-INVOKER": dict(
        severidad="media", confianza="posible", categoria="rls",
        titulo="Vista en public sin security_invoker",
        impacto="La vista se ejecuta con los permisos de su dueño y puede saltar RLS.",
        propuesta="create view ... with (security_invoker = true), o moverla fuera de public.",
        leccion="Las vistas de public se crean con security_invoker = true.",
        esfuerzo=1, referencia="OWASP A01:2021"),
    "RLS-BUCKET-PUBLICO": dict(
        severidad="media", confianza="posible", categoria="rls",
        titulo="Bucket de Storage posiblemente público",
        impacto="Cualquiera con la URL descarga los archivos del bucket.",
        propuesta="Confirmar que es intencional (imágenes públicas); si no, bucket privado y URLs firmadas.",
        leccion="Los buckets son privados salvo los documentados como públicos.",
        esfuerzo=2, referencia="OWASP A01:2021"),
    "RLS-GRANT-ANON": dict(
        severidad="media", confianza="posible", categoria="rls",
        titulo="Permiso explícito al rol anon",
        impacto="Amplía lo que puede hacer un visitante sin sesión.",
        propuesta="Confirmar que es intencional y que RLS lo acota.",
        leccion="Los permisos a anon se otorgan uno por uno y se documentan.",
        esfuerzo=1, referencia="OWASP A01:2021"),
    "RLS-AUTH-UID-SIN-SELECT": dict(
        severidad="baja", confianza="probable", categoria="rendimiento",
        titulo="auth.uid() en políticas sin envolver en (select …)",
        impacto="Se evalúa por cada fila; en tablas grandes las consultas se vuelven lentas.",
        propuesta="Usar (select auth.uid()) en las políticas e indexar las columnas filtradas.",
        leccion="En políticas se usa (select auth.uid()) y se indexan las columnas que filtran.",
        esfuerzo=1, referencia=""),
    "AUT-GETSESSION": dict(
        severidad="media", confianza="probable", categoria="auth",
        titulo="getSession() usado en código de servidor",
        impacto="getSession() no valida el token: el servidor podría confiar en una sesión falsificada.",
        propuesta="En el servidor usar supabase.auth.getUser() (o getClaims()).",
        leccion="En el servidor la identidad sale de getUser()/getClaims(), nunca de getSession().",
        esfuerzo=1, referencia="OWASP A07:2021"),
    "AUT-ACTION-SIN-SESION": dict(
        severidad="media", confianza="posible", categoria="auth",
        titulo="Archivo de Server Actions sin verificación de sesión visible",
        impacto="Una Server Action es un endpoint público: sin verificación, cualquiera la invoca.",
        propuesta="Al inicio de cada acción: obtener el usuario con getUser(), rechazar si no hay, y comprobar que el recurso le pertenece.",
        leccion="Cada Server Action y Route Handler verifica sesión y pertenencia del recurso dentro de sí mismo.",
        esfuerzo=2, referencia="OWASP A01:2021"),
    "ENT-WEBHOOK-SIN-FIRMA": dict(
        severidad="alta", confianza="probable", categoria="entradas",
        titulo="Webhook sin verificación de firma visible",
        impacto="Cualquiera puede enviar eventos falsos (p. ej. marcar un pago como aprobado).",
        propuesta="Verificar la firma del proveedor sobre el cuerpo crudo, procesar idempotentemente por ID de evento y tomar montos de la base de datos.",
        leccion="Todo webhook verifica la firma, es idempotente y no confía en montos del cuerpo.",
        esfuerzo=3, referencia="OWASP A08:2021"),
    "ENT-CRON-SIN-SECRETO": dict(
        severidad="media", confianza="probable", categoria="entradas",
        titulo="Ruta de Cron sin verificación de CRON_SECRET",
        impacto="Cualquiera puede disparar la tarea programada.",
        propuesta="Exigir Authorization: Bearer ${process.env.CRON_SECRET} y responder 401 si no coincide.",
        leccion="Las rutas de Cron exigen CRON_SECRET.",
        esfuerzo=1, referencia="OWASP A01:2021"),
    "ENT-HTML-PELIGROSO": dict(
        severidad="media", confianza="posible", categoria="entradas",
        titulo="dangerouslySetInnerHTML sin sanitización visible",
        impacto="Si el HTML viene del usuario o de la IA, permite XSS.",
        propuesta="Sanitizar (DOMPurify o equivalente) o renderizar como texto/Markdown seguro.",
        leccion="Todo HTML que viene del usuario o de la IA se sanitiza antes de mostrarse.",
        esfuerzo=2, referencia="OWASP A03:2021"),
    "ENT-EVAL": dict(
        severidad="media", confianza="posible", categoria="entradas",
        titulo="eval() o new Function() en el código",
        impacto="Ejecuta texto como código; con entradas externas es inyección.",
        propuesta="Reemplazar por lógica explícita.",
        leccion="No se ejecuta texto como código.",
        esfuerzo=2, referencia="OWASP A03:2021"),
    "ENT-REDIRECT": dict(
        severidad="media", confianza="posible", categoria="entradas",
        titulo="Redirección con un parámetro de la URL",
        impacto="Open redirect: un enlace del dominio propio lleva a un sitio de phishing.",
        propuesta="Aceptar solo rutas relativas propias (empiezan por '/' y no por '//').",
        leccion="Los parámetros next/redirectTo solo aceptan rutas propias.",
        esfuerzo=1, referencia="OWASP A01:2021"),
    "ENT-LOG-SENSIBLE": dict(
        severidad="baja", confianza="posible", categoria="privacidad",
        titulo="console.log con datos que parecen sensibles",
        impacto="Tokens o datos personales quedan en los logs de Vercel.",
        propuesta="Quitar el log o registrar solo identificadores no sensibles.",
        leccion="Los logs no llevan tokens, contraseñas ni datos personales.",
        esfuerzo=1, referencia="OWASP A09:2021"),
    "NAV-SELECT-ASTERISCO": dict(
        severidad="baja", confianza="posible", categoria="navegador",
        titulo="Consulta select('*') desde un componente cliente",
        impacto="El navegador recibe todas las columnas que RLS permita, aunque la pantalla use pocas.",
        propuesta="Seleccionar solo las columnas necesarias o servir los datos desde el servidor.",
        leccion="Desde el cliente se piden solo las columnas que la pantalla usa.",
        esfuerzo=1, referencia="OWASP A01:2021"),
    "CFG-SOURCEMAPS": dict(
        severidad="media", confianza="probable", categoria="configuracion",
        titulo="Source maps públicos en producción",
        impacto="Cualquiera reconstruye el código fuente del cliente.",
        propuesta="Quitar productionBrowserSourceMaps (o subirlos solo a la herramienta de errores).",
        leccion="Los source maps no se publican en producción.",
        esfuerzo=1, referencia="OWASP A05:2021"),
    "CFG-IGNORA-ERRORES": dict(
        severidad="baja", confianza="probable", categoria="buenas-practicas",
        titulo="El build ignora errores de TypeScript o ESLint",
        impacto="Errores reales llegan a producción sin que nadie los vea.",
        propuesta="Quitar ignoreBuildErrors / ignoreDuringBuilds y corregir los errores.",
        leccion="npm run build pasa sin ignorar errores de tipos ni de lint.",
        esfuerzo=2, referencia=""),
    "CFG-IMAGENES-COMODIN": dict(
        severidad="baja", confianza="posible", categoria="configuracion",
        titulo="next/image acepta imágenes de cualquier dominio",
        impacto="El optimizador de imágenes puede usarse como proxy y consume la cuota del plan.",
        propuesta="Listar en remotePatterns solo los dominios propios (p. ej. el de Supabase Storage).",
        leccion="remotePatterns lista dominios concretos, nunca '**'.",
        esfuerzo=1, referencia="OWASP A05:2021"),
    "CFG-SIN-CABECERAS": dict(
        severidad="media", confianza="posible", categoria="configuracion",
        titulo="No se encontró configuración de cabeceras de seguridad",
        impacto="Sin CSP ni frame-ancestors la app es más expuesta a XSS y clickjacking.",
        propuesta="Definir headers() en next.config o en vercel.json: CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, frame-ancestors. Confirmar con C1 (curl -sI).",
        leccion="Las cabeceras de seguridad se configuran en E0, junto con el primer despliegue.",
        esfuerzo=2, referencia="OWASP A05:2021"),
    "CFG-AUTH-SIN-CONFIRMACION": dict(
        severidad="media", confianza="posible", categoria="configuracion",
        titulo="Confirmación de correo desactivada en supabase/config.toml",
        impacto="Se pueden crear cuentas con correos ajenos.",
        propuesta="enable_confirmations = true (y verificar lo mismo en el dashboard de producción).",
        leccion="La confirmación de correo está activa en todo entorno con usuarios reales.",
        esfuerzo=1, referencia="OWASP A07:2021"),
    "CFG-AUTH-REDIRECT-COMODIN": dict(
        severidad="media", confianza="posible", categoria="configuracion",
        titulo="URL de redirección de Auth con comodín",
        impacto="Otra app que coincida con el comodín puede recibir tokens de inicio de sesión.",
        propuesta="Listar URL exactas (producción, localhost y, si hace falta, el patrón del equipo en Vercel).",
        leccion="Las URL de redirección de Auth son exactas, sin comodines amplios.",
        esfuerzo=1, referencia="OWASP A07:2021"),
    "SEC-HISTORIAL-CONTENIDO": dict(
        severidad="critica", confianza="probable", categoria="secretos",
        titulo="Secreto en un commit anterior (ya no está en los archivos actuales)",
        impacto="Cualquiera con acceso al repositorio lo recupera del historial de git.",
        propuesta="ROTAR la llave. Si ya se rotó, marcar el hallazgo como 'aceptado' con la fecha de rotación; reescribir el historial es opcional.",
        leccion="Toda llave que pasó por git se rota, aunque el archivo ya no exista.",
        esfuerzo=2, referencia="OWASP A02:2021"),
    "RLS-REALTIME": dict(
        severidad="media", confianza="posible", categoria="rls",
        titulo="Canal de Realtime posiblemente público",
        impacto="Los mensajes de broadcast/presence de un canal no privado los recibe cualquiera que conozca su nombre.",
        propuesta="Crear el canal con { config: { private: true } } y políticas sobre realtime.messages por organización.",
        leccion="Los canales de Realtime son privados y tienen políticas sobre realtime.messages.",
        esfuerzo=2, referencia="OWASP A01:2021"),
    "RLS-BUCKET-SIN-LIMITES": dict(
        severidad="baja", confianza="posible", categoria="abuso",
        titulo="Bucket creado sin límite de tamaño ni tipos de archivo",
        impacto="Se pueden subir archivos enormes o ejecutables (costo de Storage y riesgo para quien los descarga).",
        propuesta="Definir file_size_limit y allowed_mime_types en el bucket.",
        leccion="Todo bucket define file_size_limit y allowed_mime_types.",
        esfuerzo=1, referencia="OWASP A04:2021"),
    "ENT-SUBIDA-SIN-VALIDAR": dict(
        severidad="baja", confianza="posible", categoria="entradas",
        titulo="Subida de archivos desde el cliente sin validación visible de tipo o tamaño",
        impacto="Archivos no esperados llegan a Storage; si se sirven desde el dominio propio, posible XSS.",
        propuesta="Validar tipo y tamaño antes de subir y, sobre todo, en el bucket (allowed_mime_types, file_size_limit); rutas {org_id}/{uuid}.",
        leccion="Todo bucket define file_size_limit y allowed_mime_types.",
        esfuerzo=1, referencia="OWASP A04:2021"),
    "ABU-SIN-LIMITE": dict(
        severidad="media", confianza="posible", categoria="abuso",
        titulo="Endpoint costoso (IA o correo) sin límite de tasa visible",
        impacto="Un usuario o un bot puede llamarlo en bucle y disparar la factura del proveedor.",
        propuesta="Límite por usuario e IP (p. ej. @upstash/ratelimit o una tabla de cuotas) y tope diario; alerta de gasto en el proveedor.",
        leccion="Todo endpoint que cuesta dinero tiene límite de tasa por usuario y tope diario.",
        esfuerzo=2, referencia="OWASP A04:2021"),
    "AGT-PERMISOS": dict(
        severidad="media", confianza="probable", categoria="agente",
        titulo="Permisos amplios del agente en .claude/settings",
        impacto="El agente puede desplegar, borrar o empujar sin pedir confirmación.",
        propuesta="Quitar comodines como Bash(*) y los permisos permanentes para comandos que despliegan, migran o empujan; dejar que pidan confirmación.",
        leccion="El agente pide confirmación para todo lo que despliega, migra, borra o empuja.",
        esfuerzo=1, referencia=""),
    "AGT-MCP-TOKEN": dict(
        severidad="alta", confianza="probable", categoria="agente",
        titulo="Token escrito en la configuración de MCP",
        impacto="El token queda en el repositorio y da acceso al servicio conectado.",
        propuesta="Mover el valor a una variable de entorno (\"${NOMBRE}\") y rotar el token.",
        leccion="La configuración de MCP referencia variables de entorno, nunca tokens escritos.",
        esfuerzo=1, referencia="OWASP A02:2021"),
    "MET-SIN-PRUEBAS-RLS": dict(
        severidad="media", confianza="confirmado", categoria="metodologia",
        titulo="No hay pruebas automáticas de RLS (supabase/tests)",
        impacto="Una migración nueva puede abrir una tabla sin que nadie lo note hasta la próxima auditoría.",
        propuesta="auditar.py automatizar --escribir genera supabase/tests/00_auditoria_rls.test.sql; añadir pruebas de aislamiento entre organizaciones.",
        leccion="Las reglas de RLS se prueban con pgTAP (supabase test db) en cada PR.",
        esfuerzo=3, referencia=""),
    "MET-SIN-CI": dict(
        severidad="baja", confianza="confirmado", categoria="metodologia",
        titulo="No hay workflow de CI que ejecute el barrido de auditoría",
        impacto="Las lecciones solo se cumplen si alguien se acuerda de revisarlas.",
        propuesta="auditar.py automatizar --escribir crea .github/workflows/auditoria.yml.",
        leccion="Cada PR corre el barrido de auditoría y las pruebas de RLS.",
        esfuerzo=1, referencia=""),
    "MET-SIN-DEPENDABOT": dict(
        severidad="baja", confianza="confirmado", categoria="dependencias",
        titulo="Dependabot no está configurado",
        impacto="Las vulnerabilidades de dependencias se descubren tarde.",
        propuesta="auditar.py automatizar --escribir crea .github/dependabot.yml.",
        leccion="", esfuerzo=1, referencia="OWASP A06:2021"),
    "OPE-SIN-RUNBOOK": dict(
        severidad="baja", confianza="confirmado", categoria="operacion",
        titulo="No hay procedimiento escrito para una llave filtrada",
        impacto="En un incidente se pierde tiempo decidiendo qué rotar y en qué orden.",
        propuesta="auditar.py automatizar --escribir crea docs/incidentes/llave-filtrada.md; completar los contactos.",
        leccion="", esfuerzo=1, referencia=""),
    "OPE-SIN-MONITOREO": dict(
        severidad="baja", confianza="posible", categoria="operacion",
        titulo="No se ve una herramienta de monitoreo de errores",
        impacto="Los errores de producción se descubren cuando un usuario se queja.",
        propuesta="Integrar Sentry (o equivalente) con alertas a una persona y sin datos personales en los eventos.",
        leccion="", esfuerzo=2, referencia="OWASP A09:2021"),
    "MET-DOCS": dict(
        severidad="info", confianza="confirmado", categoria="metodologia",
        titulo="Faltan documentos del método en docs/",
        impacto="Sin la especificación, la auditoría no puede contrastar roles ni casos.",
        propuesta="Completar docs/ con diseno-express-de-apps (expres.py iniciar / validar).",
        leccion="", esfuerzo=3, referencia=""),
    "MET-CLAUDE": dict(
        severidad="baja", confianza="confirmado", categoria="metodologia",
        titulo="No hay CLAUDE.md en el proyecto",
        impacto="El agente no conoce las reglas del proyecto al empezar cada sesión.",
        propuesta="Crear CLAUDE.md con expres.py iniciar y volver a correr auditar.py iniciar.",
        leccion="", esfuerzo=1, referencia=""),
    "MET-SIN-MIGRACIONES": dict(
        severidad="media", confianza="probable", categoria="metodologia",
        titulo="Se usa Supabase pero no hay supabase/migrations",
        impacto="El esquema se cambió a mano en el dashboard: sin historia, sin RLS verificable.",
        propuesta="npx supabase db pull para capturar el esquema remoto como migración y trabajar solo con migraciones.",
        leccion="El esquema solo cambia por migraciones versionadas, nunca a mano en el dashboard.",
        esfuerzo=3, referencia=""),
    "MET-SIN-PROXY": dict(
        severidad="media", confianza="probable", categoria="auth",
        titulo="No hay proxy.ts ni middleware.ts que refresque la sesión de Supabase",
        impacto="Las sesiones expiran de forma impredecible y las rutas dependen solo de cada página.",
        propuesta="Crear src/proxy.ts (Next 16) o middleware.ts con updateSession de @supabase/ssr.",
        leccion="", esfuerzo=2, referencia=""),
    "MET-ESTRUCTURA": dict(
        severidad="baja", confianza="confirmado", categoria="metodologia",
        titulo="Falta un archivo de la estructura del método",
        impacto="Se desvía de las convenciones que los agentes esperan encontrar.",
        propuesta="Crear el archivo según references/construccion.md de diseno-express-de-apps.",
        leccion="", esfuerzo=1, referencia=""),
}

PATRONES_SECRETO = [
    ("Llave privada", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("Llave secreta de Stripe (live)", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}")),
    ("Llave secreta de Supabase", re.compile(r"\bsb_secret_[0-9A-Za-z_-]{16,}")),
    ("Llave de Anthropic", re.compile(r"\bsk-ant-[0-9A-Za-z_-]{20,}")),
    ("Llave de OpenAI", re.compile(r"\bsk-(?!ant-)(?:proj-)?[0-9A-Za-z_-]{32,}")),
    ("Token de GitHub", re.compile(r"\b(?:gh[pousr]_[0-9A-Za-z]{36,}|github_pat_[0-9A-Za-z_]{40,})")),
    ("Llave de AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Llave privada de Wompi (producción)", re.compile(r"\bprv_prod_[0-9A-Za-z]{16,}")),
    ("URL de Postgres con contraseña", re.compile(r"postgres(?:ql)?://[^:\s/'\"]+:([^@\s'\"]{6,})@([^\s'\"/:]+)")),
]
RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}")
RE_LITERAL = re.compile(
    r"\b([A-Za-z0-9_]*(?:SECRET|TOKEN|API_KEY|APIKEY|PASSWORD|PRIVATE_KEY)[A-Za-z0-9_]*)\b\s*[:=]\s*['\"]([^'\"\s]{16,})['\"]",
    re.I)
RE_PLACEHOLDER = re.compile(r"xxx|your|tu[-_]|<|\.\.\.|example|ejemplo|changeme|placeholder|process\.env|\$\{", re.I)
RE_NEXT_PUBLIC = re.compile(r"\bNEXT_PUBLIC_[A-Z0-9_]+")
RE_NEXT_PUBLIC_SECRETO = re.compile(r"SECRET|SERVICE_ROLE|SERVICE_KEY|PRIVATE|PASSWORD|TOKEN")
RE_USA_SECRETA = re.compile(r"SUPABASE_SERVICE_ROLE|SERVICE_ROLE_KEY|SUPABASE_SECRET_KEY|sb_secret_")
RE_DIRECTIVA = re.compile(r"^\s*(?:(?://[^\n]*|/\*[\s\S]*?\*/)\s*)*['\"]use (client|server)['\"]")
RE_VERIFICA_SESION = re.compile(
    r"getUser|getClaims|requireUser|requireAuth|requerirUsuario|obtenerUsuario|verificarSesion|currentUser|\bauth\(\)")


# ------------------------------------------------------------------ utilidades
def enmascarar(valor):
    if len(valor) <= 8:
        return "…" * 3 + f" (largo {len(valor)})"
    return f"{valor[:4]}…{valor[-2:]} (largo {len(valor)})"


def _huella_valor(valor):
    return hashlib.sha1(valor.encode("utf-8")).hexdigest()[:12]


def limpiar_linea(linea):
    """Extracto seguro: recorta y enmascara todo lo que parezca secreto."""
    t = linea.strip()
    for _, rx in PATRONES_SECRETO:
        t = rx.sub(lambda m: enmascarar(m.group(0)), t)
    t = RE_JWT.sub(lambda m: enmascarar(m.group(0)), t)
    t = RE_LITERAL.sub(lambda m: f"{m.group(1)}=\"{enmascarar(m.group(2))}\"", t)
    return t[:140]


def rol_jwt(token):
    try:
        carga = token.split(".")[1]
        carga += "=" * (-len(carga) % 4)
        return json.loads(base64.urlsafe_b64decode(carga)).get("role")
    except (ValueError, IndexError, json.JSONDecodeError, AttributeError):
        return None


def linea_de(texto, pos):
    return texto.count("\n", 0, pos) + 1


def git(raiz, *args):
    try:
        r = subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""


def dir_auditoria(raiz, fecha=None, crear=False):
    base = raiz / "docs" / "auditoria"
    if fecha:
        d = base / fecha
    else:
        hoy = base / date.today().isoformat()
        previas = sorted(p for p in base.glob("????-??-??") if p.is_dir()) if base.exists() else []
        d = hoy if (hoy.exists() or crear or not previas) else previas[-1]
    if crear:
        d.mkdir(parents=True, exist_ok=True)
    return d


def leer_json(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def raiz_de(args):
    raiz = Path(args.proyecto).expanduser().resolve()
    if not raiz.is_dir():
        sys.exit(f"❌ No existe el proyecto: {raiz}")
    return raiz


def plantilla(nombre, reemplazos):
    texto = (PLANTILLAS / nombre).read_text(encoding="utf-8")
    for k, v in reemplazos.items():
        texto = texto.replace(k, v)
    return texto


# ------------------------------------------------------------------ iniciar
BLOQUE_CLAUDE = """
## Lecciones aprendidas y auditoría

- Antes de empezar cada etapa, lee `docs/06-lecciones-aprendidas.md` y cumple
  sus reglas: una lección incumplida es un error reincidente.
- Al cerrar cada etapa, antes del merge a `main`, corre una auditoría rápida
  (skill `auditoria-express-de-apps`). Los informes quedan en `docs/auditoria/`.
"""


def cmd_iniciar(args):
    raiz = raiz_de(args)
    fecha = args.fecha or date.today().isoformat()
    nombre = args.nombre or raiz.name
    reemplazos = {"{{PROYECTO}}": nombre, "{{FECHA}}": fecha}
    d = dir_auditoria(raiz, fecha, crear=True)
    for origen, destino in [("plan.md", d / "plan.md"),
                            ("06-lecciones-aprendidas.md", raiz / "docs" / "06-lecciones-aprendidas.md")]:
        if destino.exists():
            print(f"⏭️  omitido (ya existe): {destino}")
        else:
            destino.write_text(plantilla(origen, reemplazos), encoding="utf-8")
            print(f"✅ creado: {destino}")

    claude = raiz / "CLAUDE.md"
    if not claude.exists():
        print("⚠️  No hay CLAUDE.md: créalo con diseno-express-de-apps (expres.py iniciar) y repite este paso.")
    elif "06-lecciones-aprendidas" in claude.read_text(encoding="utf-8"):
        print("⏭️  CLAUDE.md ya menciona las lecciones aprendidas")
    else:
        with claude.open("a", encoding="utf-8") as f:
            f.write(BLOQUE_CLAUDE)
        print("✅ CLAUDE.md: añadida la regla de lecciones aprendidas y auditoría")

    codigo, _ = git(raiz, "check-ignore", "-q", "docs/auditoria/x")
    try:
        r = subprocess.run(["gh", "repo", "view", "--json", "visibility", "-q", ".visibility"],
                           cwd=raiz, capture_output=True, text=True, timeout=20)
        visibilidad = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        visibilidad = ""
    if visibilidad == "PUBLIC" and codigo != 0:
        print("🟥 El repositorio es PÚBLICO: añade 'docs/auditoria/' a .gitignore antes de escribir hallazgos.")
    elif not visibilidad:
        print("ℹ️  No se pudo saber si el repositorio es público; si lo es, ignora docs/auditoria/.")
    print(f"\nSiguiente: llena {d / 'plan.md'} y corre `auditar.py escanear --proyecto {raiz}`")
    return 0


# ------------------------------------------------------------------ escanear
class Escaner:
    def __init__(self, raiz, incluir_build=False, historial=True):
        self.raiz = raiz
        self.incluir_build = incluir_build
        self.historial = historial
        self.hallazgos = []
        self.vistos = set()
        self.valores = set()   # huellas de secretos ya vistos en los archivos actuales (nunca el valor)

    def agregar(self, regla, archivo=None, linea=None, extracto=None, clave=None, **cambios):
        rel = str(archivo.relative_to(self.raiz)) if isinstance(archivo, Path) else archivo
        llave = (regla, rel, clave or linea)
        if llave in self.vistos:
            return
        self.vistos.add(llave)
        h = dict(REGLAS[regla])
        h.update(cambios)
        h.update({
            "id": f"EST-{len(self.hallazgos) + 1:03d}", "equipo": "EST", "regla": regla,
            "estado": "abierto", "alcance": "proyecto",
            "evidencia": {"archivo": rel, "linea": linea, "url": None,
                          "comando": "auditar.py escanear", "extracto": extracto},
        })
        if clave:
            h["clave"] = clave
        self.hallazgos.append(h)

    def archivos(self):
        for p in sorted(self.raiz.rglob("*")):
            partes = p.relative_to(self.raiz).parts
            if any(x in EXCLUIR_DIRS for x in partes[:-1]) or partes[:2] == ("docs", "auditoria"):
                continue
            if p.is_file() and p.name not in OMITIR_ARCHIVOS:
                yield p

    @staticmethod
    def leer(p, limite=1_500_000):
        try:
            if p.stat().st_size > limite:
                return None
            return p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None

    # -- secretos en contenido
    @staticmethod
    def _secretos_en(texto):
        """[(nombre, match)] de secretos por patrón, sin URL de Postgres de ejemplo o locales."""
        for nombre, rx in PATRONES_SECRETO:
            for m in rx.finditer(texto):
                if nombre.startswith("URL de Postgres"):
                    clave, host = m.group(1), m.group(2)
                    if host in ("localhost", "127.0.0.1", "db") or RE_PLACEHOLDER.search(clave) \
                            or clave in ("postgres", "password", "contrasena"):
                        continue
                yield nombre, m

    def buscar_secretos(self, p, texto, en_bundle=False):
        regla = "SEC-BUNDLE" if en_bundle else "SEC-PATRON"
        for nombre, m in self._secretos_en(texto):
            self.valores.add(_huella_valor(m.group(0)))
            ln = linea_de(texto, m.start())
            self.agregar(regla, p, ln, limpiar_linea(texto.splitlines()[ln - 1])[:140],
                         clave=f"{nombre}:{ln}", titulo=f"{REGLAS[regla]['titulo']}: {nombre}")
        for m in RE_JWT.finditer(texto):
            rol = rol_jwt(m.group(0))
            ln = linea_de(texto, m.start())
            extracto = limpiar_linea(texto.splitlines()[ln - 1]) if not en_bundle else enmascarar(m.group(0))
            if rol == "service_role":
                self.valores.add(_huella_valor(m.group(0)))
                self.agregar("SEC-BUNDLE" if en_bundle else "SEC-JWT-SERVICE", p, ln, extracto,
                             clave=f"jwt:{ln}", titulo="JWT con rol service_role" +
                             (" dentro del JavaScript del navegador" if en_bundle else " escrito en un archivo"))
            elif rol == "anon" and not en_bundle and p.suffix in EXT_CODIGO:
                self.agregar("SEC-JWT-ANON", p, ln, extracto, clave=f"jwt:{ln}")

    def revisar_historial(self):
        """Busca secretos en el contenido de todos los commits; reporta los que ya no están en los archivos."""
        if not (self.raiz / ".git").exists():
            return
        try:
            r = subprocess.run(["git", "-C", str(self.raiz), "log", "--all", "-p", "--no-color", "-U0",
                                "--format=commit %h"], capture_output=True, text=True, errors="replace", timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            print("⚠️  No se pudo revisar el historial de git (tiempo agotado); usa gitleaks o trufflehog.")
            return
        commit = archivo = None
        for linea in r.stdout.splitlines():
            if linea.startswith("commit "):
                commit = linea[7:].strip()
            elif linea.startswith("+++ "):
                archivo = linea[6:] if linea.startswith("+++ b/") else None
            elif linea.startswith("+") and archivo and not archivo.startswith("docs/auditoria/") \
                    and Path(archivo).name not in OMITIR_ARCHIVOS:
                encontrados = [(n, m.group(0)) for n, m in self._secretos_en(linea)]
                encontrados += [("JWT service_role", m.group(0)) for m in RE_JWT.finditer(linea)
                                if rol_jwt(m.group(0)) == "service_role"]
                for nombre, valor in encontrados:
                    hv = _huella_valor(valor)
                    if hv in self.valores:
                        continue   # sigue en los archivos actuales: ya lo reporta SEC-PATRON
                    self.agregar("SEC-HISTORIAL-CONTENIDO", archivo, None, f"commit {commit}: {enmascarar(valor)}",
                                 clave=hv, titulo=f"{REGLAS['SEC-HISTORIAL-CONTENIDO']['titulo']}: {nombre}")

    def buscar_literales(self, p, texto):
        for m in RE_LITERAL.finditer(texto):
            if RE_PLACEHOLDER.search(m.group(2)) or m.group(2).startswith(("NEXT_PUBLIC_", "sb_publishable_")) \
                    or any(rx.search(m.group(2)) for _, rx in PATRONES_SECRETO) or RE_JWT.search(m.group(2)):
                continue   # ya lo reporta buscar_secretos con una regla más precisa
            ln = linea_de(texto, m.start())
            self.agregar("SEC-LITERAL", p, ln, limpiar_linea(texto.splitlines()[ln - 1]), clave=m.group(1))

    # -- .env y gitignore
    def revisar_env(self, versionados):
        es_repo = (self.raiz / ".git").exists()
        for rel in versionados:
            nombre = Path(rel).name
            if RE_ENV.match(nombre) and not RE_ENV_EJEMPLO.search(nombre):
                self.agregar("SEC-ENV-VERSIONADO", rel, None, f"{rel} (contenido no mostrado)", clave=rel)
        if es_repo:
            _, salida = git(self.raiz, "log", "--all", "--diff-filter=A", "--name-only", "--format=")
            for rel in sorted(set(salida.split())):
                nombre = Path(rel).name
                if RE_ENV.match(nombre) and not RE_ENV_EJEMPLO.search(nombre) and rel not in versionados:
                    self.agregar("SEC-ENV-HISTORIAL", rel, None, f"{rel} existió en algún commit", clave=rel)
            if git(self.raiz, "check-ignore", "-q", ".env.local")[0] == 1:
                self.agregar("SEC-ENV-NO-IGNORADO", ".gitignore")
            if git(self.raiz, "check-ignore", "-q", ".vercel/project.json")[0] == 1:
                self.agregar("SEC-VERCEL-NO-IGNORADO", ".gitignore")

    def revisar_next_public(self, p, texto, es_env):
        for i, linea in enumerate(texto.splitlines(), 1):
            if es_env and not re.match(r"^\s*(export\s+)?NEXT_PUBLIC_", linea):
                continue
            for m in RE_NEXT_PUBLIC.finditer(linea):
                var = m.group(0)
                if not RE_NEXT_PUBLIC_SECRETO.search(var[len("NEXT_PUBLIC_"):]):
                    continue
                grave = re.search(r"SECRET|SERVICE_ROLE|SERVICE_KEY", var)
                self.agregar("SEC-NEXT-PUBLIC", p, i, var + (" = (valor no mostrado)" if es_env else ""),
                             clave=var, titulo=f"Variable pública con nombre de secreto: {var}",
                             severidad="critica" if grave else "alta",
                             confianza="probable" if grave else "posible")

    # -- SQL
    def revisar_sql(self, archivos_sql):
        sin_com = {}
        for p in archivos_sql:
            t = self.leer(p) or ""
            t = re.sub(r"/\*[\s\S]*?\*/", lambda m: "\n" * m.group(0).count("\n"), t)
            sin_com[p] = re.sub(r"--[^\n]*", "", t)

        rx_crear = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:\"?(\w+)\"?\.)?\"?(\w+)\"?", re.I)
        rx_rls = re.compile(r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:\"?(\w+)\"?\.)?\"?(\w+)\"?"
                            r"\s+enable\s+row\s+level\s+security", re.I)
        rx_borrar = re.compile(r"drop\s+table\s+(?:if\s+exists\s+)?(?:\"?(\w+)\"?\.)?\"?(\w+)\"?", re.I)
        rls_global, borradas = set(), set()
        for t in sin_com.values():
            rls_global |= {((m.group(1) or "public").lower(), m.group(2).lower()) for m in rx_rls.finditer(t)}
            borradas |= {((m.group(1) or "public").lower(), m.group(2).lower()) for m in rx_borrar.finditer(t)}

        for p, t in sin_com.items():
            rls_local = {((m.group(1) or "public").lower(), m.group(2).lower()) for m in rx_rls.finditer(t)}
            for m in rx_crear.finditer(t):
                tabla = ((m.group(1) or "public").lower(), m.group(2).lower())
                if tabla[0] != "public" or tabla in rls_local or tabla in borradas:
                    continue
                ln = linea_de(t, m.start())
                regla = "RLS-OTRA-MIGRACION" if tabla in rls_global else "RLS-SIN-RLS"
                self.agregar(regla, p, ln, m.group(0).strip()[:140], clave=tabla[1],
                             titulo=f"{REGLAS[regla]['titulo']}: {tabla[1]}")
            for m in re.finditer(r"alter\s+table\s+[^;]*?disable\s+row\s+level\s+security", t, re.I):
                self.agregar("RLS-DESACTIVADO", p, linea_de(t, m.start()), " ".join(m.group(0).split())[:140])

            for m in re.finditer(r"create\s+policy\s+(\"[^\"]+\"|\w+)\s+on\s+([\w\".]+)([\s\S]*?);", t, re.I):
                cuerpo, ln = m.group(3), linea_de(t, m.start())
                nombre = f"{m.group(1).strip(chr(34))} en {m.group(2)}"
                if re.search(r"(using|with\s+check)\s*\(\s*true\s*\)", cuerpo, re.I):
                    escribe = re.search(r"\bfor\s+(insert|update|delete|all)\b", cuerpo, re.I) or \
                        not re.search(r"\bfor\s+select\b", cuerpo, re.I)
                    self.agregar("RLS-POLITICA-ABIERTA", p, ln, nombre, clave=nombre,
                                 severidad="alta" if escribe else "media",
                                 confianza="probable" if escribe else "posible")
                if re.search(r"user_metadata|raw_user_meta_data", cuerpo, re.I):
                    self.agregar("RLS-USER-METADATA", p, ln, nombre, clave=nombre)
            total = len(re.findall(r"auth\.uid\(\)", t))
            envueltas = len(re.findall(r"\(\s*select\s+auth\.uid\(\)\s*\)", t, re.I))
            if total > envueltas and "create policy" in t.lower():
                self.agregar("RLS-AUTH-UID-SIN-SELECT", p, None, f"{total - envueltas} usos sin (select …)")

            for m in re.finditer(r"create\s+(?:or\s+replace\s+)?function\s+([\w\".]+)", t, re.I):
                apertura = re.compile(r"\$(\w*)\$").search(t, m.end())
                if not apertura:
                    continue
                cierre = t.find(apertura.group(0), apertura.end())
                fin = t.find(";", cierre if cierre != -1 else apertura.end())
                cabeza = t[m.end():apertura.start()] + (t[cierre:fin] if cierre != -1 else "")
                if re.search(r"security\s+definer", cabeza, re.I):
                    if re.search(r"user_metadata|raw_user_meta_data", t[apertura.end():cierre], re.I):
                        self.agregar("RLS-USER-METADATA", p, linea_de(t, m.start()), m.group(1),
                                     clave=m.group(1), titulo=f"Función {m.group(1)} confía en user_metadata")
                    if not re.search(r"search_path", cabeza, re.I):
                        self.agregar("RLS-DEFINER-SEARCH-PATH", p, linea_de(t, m.start()), m.group(1),
                                     clave=m.group(1), titulo=f"{REGLAS['RLS-DEFINER-SEARCH-PATH']['titulo']}: {m.group(1)}")

            for m in re.finditer(r"create\s+(?:or\s+replace\s+)?view\s+(?:\"?(\w+)\"?\.)?\"?(\w+)\"?([^;]*);", t, re.I):
                if (m.group(1) or "public").lower() == "public" and "security_invoker" not in m.group(3).lower():
                    self.agregar("RLS-VISTA-SIN-INVOKER", p, linea_de(t, m.start()), m.group(2), clave=m.group(2))
            for m in re.finditer(r"(insert\s+into\s+storage\.buckets[^;]*;|update\s+storage\.buckets[^;]*;)", t, re.I):
                if re.search(r"\btrue\b", m.group(0), re.I):
                    self.agregar("RLS-BUCKET-PUBLICO", p, linea_de(t, m.start()), " ".join(m.group(0).split())[:140])
                if m.group(0).lower().startswith("insert") and "file_size_limit" not in m.group(0).lower():
                    self.agregar("RLS-BUCKET-SIN-LIMITES", p, linea_de(t, m.start()), " ".join(m.group(0).split())[:140])
            for m in re.finditer(r"grant\s+[^;]*?\bto\s+(?:[\w, ]*\b)?anon\b[^;]*;", t, re.I):
                self.agregar("RLS-GRANT-ANON", p, linea_de(t, m.start()), " ".join(m.group(0).split())[:140])

    # -- código
    def revisar_codigo(self, p, texto):
        rel = p.relative_to(self.raiz).as_posix()
        d = RE_DIRECTIVA.match(texto)
        directiva = d.group(1) if d else None
        lineas = texto.splitlines()

        def primera(rx, flags=0):
            m = re.search(rx, texto, flags)
            return (linea_de(texto, m.start()), lineas[linea_de(texto, m.start()) - 1].strip()[:140]) if m else (None, None)

        if directiva == "client":
            ln, ex = primera(RE_USA_SECRETA.pattern)
            if ln:
                self.agregar("SEC-SERVICE-CLIENTE", p, ln, limpiar_linea(ex))
            ln, ex = primera(r"\.select\(\s*(['\"]\*['\"])?\s*\)")
            if ln:
                self.agregar("NAV-SELECT-ASTERISCO", p, ln, ex)
        else:
            ln, ex = primera(r"auth\.getSession\(")
            if ln:
                self.agregar("AUT-GETSESSION", p, ln, ex)
            es_ruta = p.stem == "route"
            if RE_USA_SECRETA.search(texto) and "server-only" not in texto and directiva != "server" \
                    and not es_ruta and "supabase/functions" not in rel:
                ln, ex = primera(RE_USA_SECRETA.pattern)
                self.agregar("SEC-SIN-SERVER-ONLY", p, ln, limpiar_linea(ex))

        if ".channel(" in texto and not re.search(r"private\s*:\s*true", texto):
            self.agregar("RLS-REALTIME", p, *primera(r"\.channel\("))
        if directiva == "client" and ".upload(" in texto and \
                not re.search(r"\.size\b|\.type\b|mime|maxSize|accept", texto, re.I):
            self.agregar("ENT-SUBIDA-SIN-VALIDAR", p, *primera(r"\.upload\("))
        if (p.stem == "route" or directiva == "server") and re.search(
                r"generateText|streamText|generateObject|messages\.create|chat\.completions|emails\.send|sendEmail|resend\.", texto) \
                and not re.search(r"ratelimit|rate_limit|rateLimit|limite|cuota|quota", texto, re.I):
            self.agregar("ABU-SIN-LIMITE", p, None, rel)

        if directiva == "server" and re.search(r"export\s+(async\s+)?(function|const)", texto) \
                and not RE_VERIFICA_SESION.search(texto):
            self.agregar("AUT-ACTION-SIN-SESION", p, None, "export sin getUser()/getClaims() en el archivo")

        if p.stem == "route" and "/app/" in f"/{rel}":
            if "webhook" in rel.lower() and not re.search(
                    r"signature|firma|constructEvent|verify|hmac|timingSafeEqual", texto, re.I):
                self.agregar("ENT-WEBHOOK-SIN-FIRMA", p, None, rel)
            if "cron" in rel.lower() and "CRON_SECRET" not in texto:
                self.agregar("ENT-CRON-SIN-SECRETO", p, None, rel)

        if "dangerouslySetInnerHTML" in texto and not re.search(r"sanitiz|DOMPurify", texto, re.I):
            self.agregar("ENT-HTML-PELIGROSO", p, *primera(r"dangerouslySetInnerHTML"))
        ln, ex = primera(r"(?<![\w.])eval\s*\(|new\s+Function\s*\(")
        if ln:
            self.agregar("ENT-EVAL", p, ln, ex)
        ln, ex = primera(r"redirect\s*\([^)\n]*(searchParams|params)\b")
        if ln:
            self.agregar("ENT-REDIRECT", p, ln, ex)
        ln, ex = primera(r"console\.(log|info|debug)\([^)\n]*\b(token|password|contrase\w*|secret|session|apikey|api_key)\b", re.I)
        if ln:
            self.agregar("ENT-LOG-SENSIBLE", p, ln, limpiar_linea(ex))

    # -- configuración y método
    def revisar_config(self, versionados):
        r = self.raiz
        configs = [r / n for n in ("next.config.js", "next.config.mjs", "next.config.ts") if (r / n).exists()]
        cabeceras = False
        for p in configs:
            t = self.leer(p) or ""
            for regla, rx in (("CFG-SOURCEMAPS", r"productionBrowserSourceMaps\s*:\s*true"),
                              ("CFG-IGNORA-ERRORES", r"ignore(BuildErrors|DuringBuilds)\s*:\s*true"),
                              ("CFG-IMAGENES-COMODIN", r"hostname\s*:\s*['\"]\*\*['\"]")):
                m = re.search(rx, t)
                if m:
                    self.agregar(regla, p, linea_de(t, m.start()), m.group(0))
            cabeceras |= bool(re.search(r"headers\s*\(|headers\s*:", t))
        vj = r / "vercel.json"
        if vj.exists():
            cabeceras |= '"headers"' in (self.leer(vj) or "")
        for n in ("src/proxy.ts", "proxy.ts", "src/middleware.ts", "middleware.ts"):
            if (r / n).exists():
                cabeceras |= "Content-Security-Policy" in (self.leer(r / n) or "")
        if (r / "package.json").exists() and not cabeceras:
            self.agregar("CFG-SIN-CABECERAS", "next.config / vercel.json")

        toml = r / "supabase" / "config.toml"
        if toml.exists():
            t = self.leer(toml) or ""
            bloque = re.search(r"^\[auth\.email\]([\s\S]*?)(?=^\[|\Z)", t, re.M)
            if bloque and re.search(r"enable_confirmations\s*=\s*false", bloque.group(1)):
                self.agregar("CFG-AUTH-SIN-CONFIRMACION", toml, None, "enable_confirmations = false")
            m = re.search(r"additional_redirect_urls\s*=\s*\[([^\]]*)\]", t)
            if m and "*" in m.group(1):
                self.agregar("CFG-AUTH-REDIRECT-COMODIN", toml, linea_de(t, m.start()), m.group(0)[:140])

        faltan = [d for d in DOCS_METODO if not (r / "docs" / d).exists()]
        if faltan:
            self.agregar("MET-DOCS", "docs/", None, "faltan: " + ", ".join(faltan))
        if not (r / "CLAUDE.md").exists():
            self.agregar("MET-CLAUDE", "CLAUDE.md")
        pkg = self.leer(r / "package.json") if (r / "package.json").exists() else ""
        usa_supabase = "@supabase/" in (pkg or "")
        mig = r / "supabase" / "migrations"
        if usa_supabase and not (mig.exists() and any(mig.glob("*.sql"))):
            self.agregar("MET-SIN-MIGRACIONES", "supabase/migrations")
        if usa_supabase:
            if not any((r / n).exists() for n in ("src/proxy.ts", "proxy.ts", "src/middleware.ts", "middleware.ts")):
                self.agregar("MET-SIN-PROXY", "src/proxy.ts")
            for n in ("src/lib/supabase/server.ts", "src/lib/supabase/client.ts", "src/lib/database.types.ts"):
                if not (r / n).exists():
                    self.agregar("MET-ESTRUCTURA", n, None, None, clave=n, titulo=f"Falta {n}")
        if pkg and "package-lock.json" not in versionados and (r / ".git").exists():
            self.agregar("MET-ESTRUCTURA", "package-lock.json", None, None, clave="lock",
                         titulo="package-lock.json no está versionado", categoria="buenas-practicas")
        if pkg and not any((r / n).exists() for n in (".env.example", ".env.sample")):
            self.agregar("MET-ESTRUCTURA", ".env.example", None, None, clave="envex",
                         titulo="No hay .env.example con los nombres de las variables")

        # automatización y operación
        if usa_supabase and not any((r / "supabase" / "tests").rglob("*.sql")):
            self.agregar("MET-SIN-PRUEBAS-RLS", "supabase/tests")
        if pkg:
            flujos = list((r / ".github" / "workflows").glob("*.y*ml"))
            if not any("auditar.py" in (self.leer(f) or "") for f in flujos):
                self.agregar("MET-SIN-CI", ".github/workflows")
            if not any((r / ".github" / n).exists() for n in ("dependabot.yml", "dependabot.yaml")):
                self.agregar("MET-SIN-DEPENDABOT", ".github/dependabot.yml")
            if not (r / "docs" / "incidentes" / "llave-filtrada.md").exists():
                self.agregar("OPE-SIN-RUNBOOK", "docs/incidentes/llave-filtrada.md")
            if not re.search(r"@sentry/|@highlight-run|@logtail|@axiomhq|@bugsnag|@datadog|@vercel/otel|posthog", pkg):
                self.agregar("OPE-SIN-MONITOREO", "package.json")

        # agente
        for n in (".claude/settings.json", ".claude/settings.local.json"):
            try:
                cfg = json.loads(self.leer(r / n) or "{}") if (r / n).exists() else {}
            except json.JSONDecodeError:
                continue
            permisos = cfg.get("permissions") or {}
            riesgosos = [a for a in permisos.get("allow") or [] if isinstance(a, str) and (
                a in ("Bash", "Bash(*)", "Bash(:*)") or re.search(
                    r"vercel.*(--prod|deploy|promote|env (add|rm|pull))|supabase.*(db (push|reset)|migration repair|secrets set)"
                    r"|git push|rm -rf", a))]
            if permisos.get("defaultMode") == "bypassPermissions":
                riesgosos.append("defaultMode: bypassPermissions")
            if riesgosos:
                self.agregar("AGT-PERMISOS", n, None, ", ".join(riesgosos)[:140], clave=n)
        mcp = r / ".mcp.json"
        if mcp.exists():
            try:
                servidores = (json.loads(self.leer(mcp) or "{}").get("mcpServers") or {})
            except json.JSONDecodeError:
                servidores = {}
            for nombre, s in servidores.items():
                pares = list((s.get("env") or {}).items()) + list((s.get("headers") or {}).items())
                for k, v in pares:
                    if isinstance(v, str) and v and "${" not in v and \
                            re.search(r"KEY|TOKEN|SECRET|PASSWORD|AUTHORIZATION", k.upper()):
                        self.agregar("AGT-MCP-TOKEN", mcp, None, f"{nombre}.{k} = {enmascarar(v)}", clave=f"{nombre}.{k}")

    def correr(self):
        codigo, salida = git(self.raiz, "ls-files")
        versionados = set(salida.split("\n")) - {""} if codigo == 0 else set()
        self.revisar_env(versionados)
        sql = []
        for p in self.archivos():
            nombre, ext = p.name, p.suffix.lower()
            es_env = bool(RE_ENV.match(nombre))
            if es_env:
                texto = self.leer(p)
                if texto is not None and not RE_ENV_EJEMPLO.search(nombre):
                    self.revisar_next_public(p, texto, es_env=True)   # solo nombres, nunca valores
                elif texto is not None:
                    self.buscar_secretos(p, texto)
                continue
            if ext not in EXT_TEXTO:
                continue
            texto = self.leer(p)
            if texto is None:
                continue
            self.buscar_secretos(p, texto)
            if ext == ".sql":
                sql.append(p)
            if ext in EXT_CODIGO:
                self.buscar_literales(p, texto)
                self.revisar_next_public(p, texto, es_env=False)
                self.revisar_codigo(p, texto)
        self.revisar_sql(sql)
        self.revisar_config(versionados)
        if self.historial:
            self.revisar_historial()
        if self.incluir_build:
            static = self.raiz / ".next" / "static"
            if not static.exists():
                print("⚠️  No existe .next/static: corre `npm run build` antes de --incluir-build.")
            for p in sorted(static.rglob("*.js")) if static.exists() else []:
                texto = self.leer(p, limite=8_000_000)
                if texto:
                    self.buscar_secretos(p, texto, en_bundle=True)
            for p in sorted(static.rglob("*.js.map")) if static.exists() else []:
                self.agregar("CFG-SOURCEMAPS", p, None, "source map generado en el build", clave="map")
                break
        orden = {s: i for i, s in enumerate(SEVERIDADES)}
        self.hallazgos.sort(key=lambda h: (orden[h["severidad"]], h["regla"]))
        for i, h in enumerate(self.hallazgos, 1):
            h["id"] = f"EST-{i:03d}"
        return self.hallazgos


def _aceptados(raiz):
    """Huellas marcadas aceptado/descartado en la última auditoría consolidada."""
    base = raiz / "docs" / "auditoria"
    for d in sorted(base.glob("????-??-??"), reverse=True) if base.exists() else []:
        if (d / "hallazgos.json").exists():
            return {x for h in leer_json(d / "hallazgos.json") if h.get("estado") in ("aceptado", "descartado")
                    for x in h.get("huellas") or [h["huella"]]}
    return set()


def cmd_escanear(args):
    raiz = raiz_de(args)
    hallazgos = Escaner(raiz, args.incluir_build, historial=not args.sin_historial).correr()
    if args.ci:
        aceptados = _aceptados(raiz)
        bloquean = [h for h in hallazgos if h["severidad"] in ("critica", "alta")
                    and h["confianza"] != "posible" and huella(h) not in aceptados]
        for h in bloquean:
            ev = h["evidencia"]
            print(f"{ICONO[h['severidad']]} {h['titulo']} — {ev['archivo']}" + (f":{ev['linea']}" if ev.get("linea") else ""))
            print(f"   → {h['propuesta']}")
        print(f"\n{len(bloquean)} hallazgos críticos/altos bloquean ({len(hallazgos)} en total). "
              "Para aceptar un riesgo, márcalo 'aceptado' en la auditoría consolidada.")
        return 1 if bloquean else 0
    d = dir_auditoria(raiz, args.fecha, crear=True)
    destino = d / "hallazgos-estatico.json"
    escribir_json(destino, hallazgos)
    conteo = {s: sum(1 for h in hallazgos if h["severidad"] == s) for s in SEVERIDADES}
    print("Barrido estático: " + " · ".join(f"{ICONO[s]} {s} {n}" for s, n in conteo.items()))
    for h in hallazgos:
        ev = h["evidencia"]
        donde = ev["archivo"] + (f":{ev['linea']}" if ev.get("linea") else "")
        print(f"  {ICONO[h['severidad']]} {h['id']} [{h['confianza']}] {h['titulo']} — {donde}")
    print(f"\n✅ {destino}")
    print("Los 'posible' son pistas: los equipos A/B/C los confirman o descartan.")
    return 0


# ------------------------------------------------------------------ consolidar
OBLIGATORIOS = ["id", "equipo", "categoria", "severidad", "confianza", "titulo", "evidencia", "propuesta"]


def validar_hallazgo(h, origen):
    errores = []
    pref = f"{origen} · {h.get('id', '¿sin id?')}"
    for c in OBLIGATORIOS:
        if not h.get(c):
            errores.append(f"{pref}: falta '{c}'")
    for campo, valores in (("severidad", SEVERIDADES), ("confianza", CONFIANZAS), ("categoria", CATEGORIAS),
                           ("estado", ESTADOS), ("alcance", ALCANCES)):
        if h.get(campo) and h[campo] not in valores:
            errores.append(f"{pref}: {campo} '{h[campo]}' no es uno de {valores}")
    ev = h.get("evidencia")
    if ev is not None and (not isinstance(ev, dict) or not any(ev.get(k) for k in ("archivo", "url", "comando"))):
        errores.append(f"{pref}: evidencia necesita archivo, url o comando")
    if h.get("esfuerzo") is not None and h["esfuerzo"] not in FIBONACCI:
        errores.append(f"{pref}: esfuerzo {h['esfuerzo']} no es Fibonacci 1-13")
    return errores


def huella(h):
    ev = h.get("evidencia") or {}
    lugar = ev.get("archivo") or ev.get("url") or ""
    extra = h.get("clave") or ("" if h.get("regla") else re.sub(r"\W+", " ", h.get("titulo", "").lower()).strip())
    base = f"{h.get('regla') or h.get('categoria')}|{lugar}|{extra}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def subir(valor, escala, pasos=1):
    return escala[max(0, escala.index(valor) - pasos)]


def leer_lecciones(raiz):
    p = raiz / "docs" / "06-lecciones-aprendidas.md"
    if not p.exists():
        return p, None, []
    t = p.read_text(encoding="utf-8")
    m = re.search(r"<!-- LECCIONES:INICIO -->\n([\s\S]*?)<!-- LECCIONES:FIN -->", t)
    filas = []
    if m:
        for linea in m.group(1).splitlines():
            c = [x.strip() for x in linea.strip().strip("|").split("|")]
            if len(c) >= 6 and re.match(r"LA-\d+", c[0]):
                filas.append({"id": c[0], "leccion": c[1], "categoria": c[2], "origen": c[3],
                              "primera": c[4], "veces": int(c[5]) if c[5].isdigit() else 1})
    return p, t, filas


def cmd_consolidar(args):
    raiz = raiz_de(args)
    d = dir_auditoria(raiz, args.fecha)
    archivos = sorted(d.glob("hallazgos-*.json")) if d.exists() else []
    if not archivos:
        print(f"❌ No hay hallazgos-*.json en {d}")
        return 1
    todos, errores = [], []
    for a in archivos:
        try:
            lista = leer_json(a)
        except json.JSONDecodeError as e:
            errores.append(f"{a.name}: JSON inválido ({e})")
            continue
        if not isinstance(lista, list):
            errores.append(f"{a.name}: debe ser una lista de hallazgos")
            continue
        for h in lista:
            errores += validar_hallazgo(h, a.name)
            h.setdefault("estado", "abierto")
            h.setdefault("alcance", "proyecto")
            h["_archivo"] = a.name
            todos.append(h)
    ids = [h.get("id") for h in todos]
    errores += [f"ID repetido: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if errores:
        for e in errores:
            print(f"❌ {e}")
        print("\nCorrige los archivos y vuelve a consolidar.")
        return 1

    # Fusión: misma huella o vínculo explícito en 'relacionados' (unión-búsqueda).
    for h in todos:
        h["huella"] = h.get("huella") or huella(h)
    padre = {h["id"]: h["id"] for h in todos}

    def raiz_uf(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    por_huella = {}
    for h in todos:
        if h["huella"] in por_huella:
            padre[raiz_uf(h["id"])] = raiz_uf(por_huella[h["huella"]])
        por_huella.setdefault(h["huella"], h["id"])
        for r in h.get("relacionados") or []:
            if r in padre:
                padre[raiz_uf(r)] = raiz_uf(h["id"])
    grupos = {}
    for h in todos:
        grupos.setdefault(raiz_uf(h["id"]), []).append(h)

    sev_i = {s: i for i, s in enumerate(SEVERIDADES)}
    conf_i = {c: i for i, c in enumerate(CONFIANZAS)}

    anteriores = sorted(p for p in d.parent.glob("????-??-??") if p.is_dir() and p.name < d.name
                        and (p / "hallazgos.json").exists())
    lista_previa = leer_json(anteriores[-1] / "hallazgos.json") if anteriores else []
    previos = {x: h for h in lista_previa for x in h.get("huellas") or [h["huella"]]}
    # Orígenes de lecciones de auditorías ANTERIORES: (id lección, regla, huella).
    _, _, lecciones = leer_lecciones(raiz)
    origenes = []
    for l in lecciones:
        for seg in l["origen"].split(";"):
            m = re.match(r"\s*(\d{4}-\d{2}-\d{2})\b(.*)", seg)
            if m and m.group(1) < d.name:
                r_, h_ = re.search(r"\br:(\S+)", m.group(2)), re.search(r"\bh:(\w+)", m.group(2))
                origenes.append((l["id"], r_.group(1) if r_ else None, h_.group(1) if h_ else None))

    finales = []
    for miembros in grupos.values():
        vivos = [m for m in miembros if m["estado"] != "descartado"] or miembros
        vivos.sort(key=lambda m: (sev_i[m["severidad"]], conf_i[m["confianza"]]))
        h = {k: v for k, v in vivos[0].items() if k != "_archivo"}
        equipos = sorted({m["equipo"] for m in miembros})
        h["equipos"] = equipos
        h["fusionados"] = sorted(m["id"] for m in miembros if m["id"] != h["id"])
        h["confianza"] = min((m["confianza"] for m in miembros), key=conf_i.get)
        if len({e[0] for e in equipos}) >= 2 and h["confianza"] != "confirmado":
            h["confianza"] = subir(h["confianza"], CONFIANZAS)
        huellas = {m["huella"] for m in miembros}
        reglas = {m["regla"] for m in miembros if m.get("regla")}
        h["huellas"] = sorted(huellas)
        if reglas:
            h["reglas"] = sorted(reglas)
        previo = next((previos[x] for x in huellas if x in previos), None)
        leccion = next((lid for lid, r_, h_ in origenes if h_ in huellas or (r_ and r_ in reglas)), None)
        # persistente: seguía abierto desde la anterior; reincidente: se había corregido
        # (o ya era una lección registrada) y volvió a aparecer.
        if previo and previo.get("estado") in ("abierto", "aceptado"):
            h["historial"] = "persistente"
            if previo["estado"] == "aceptado" and h["estado"] == "abierto":
                h["estado"] = "aceptado"
                h["nota"] = (previo.get("nota") or "riesgo aceptado") + f" (heredado de {anteriores[-1].name})"
        elif (previo and previo.get("estado") == "corregido") or leccion:
            h["historial"] = "reincidente"
        else:
            h["historial"] = "nuevo"
        if leccion and h["historial"] == "reincidente":
            h["incumple_leccion"] = leccion
        if h["historial"] == "reincidente" and h["confianza"] != "posible" \
                and h["severidad"] not in ("critica", "info"):
            h["severidad_original"] = h["severidad"]
            h["severidad"] = subir(h["severidad"], SEVERIDADES)
        finales.append(h)
    finales.sort(key=lambda h: (h["estado"] != "abierto", sev_i[h["severidad"]], conf_i[h["confianza"]], h["id"]))
    actuales = {m["huella"] for m in todos}
    no_reaparecen = []
    for h in lista_previa:
        if h.get("estado") in ("abierto", "aceptado") and not actuales & set(h.get("huellas") or [h["huella"]]):
            no_reaparecen.append(h)

    escribir_json(d / "hallazgos.json", finales)
    (d / "informe.md").write_text(informe(raiz, d, finales, no_reaparecen, archivos,
                                          anteriores[-1].name if anteriores else None), encoding="utf-8")
    abiertos = [h for h in finales if h["estado"] == "abierto"]
    print(f"Consolidados {len(todos)} hallazgos de {len(archivos)} archivos → {len(finales)} únicos.")
    print("Abiertos: " + " · ".join(f"{ICONO[s]} {s} {sum(1 for h in abiertos if h['severidad'] == s)}"
                                    for s in SEVERIDADES))
    pend = [h for h in abiertos if h["severidad"] in ("critica", "alta") and h["confianza"] != "confirmado"]
    if pend:
        print(f"⚠️  {len(pend)} críticos/altos sin confirmar: pásalos por verificación adversarial: "
              + ", ".join(h["id"] for h in pend))
    for h in abiertos:
        if h["severidad"] == "critica" and h["confianza"] == "confirmado":
            print(f"🟥 URGENTE {h['id']}: {h['titulo']}")
    print(f"✅ {d / 'hallazgos.json'}\n✅ {d / 'informe.md'}")
    return 0


def _donde(h):
    ev = h.get("evidencia") or {}
    if ev.get("archivo"):
        return f"`{ev['archivo']}" + (f":{ev['linea']}`" if ev.get("linea") else "`")
    return f"`{ev.get('url') or ev.get('comando')}`"


def _celda(texto):
    return str(texto or "").replace("|", "/").replace("\n", " ")


def informe(raiz, d, finales, no_reaparecen, archivos, anterior):
    abiertos = [h for h in finales if h["estado"] == "abierto"]
    cerrados = [h for h in finales if h["estado"] != "abierto"]
    o = [f"# Informe de auditoría {d.name} · {raiz.name}", "",
         f"Equipos: {', '.join(a.stem.replace('hallazgos-', '') for a in archivos)}"
         + (f" · Comparado con la auditoría {anterior}" if anterior else " · Primera auditoría consolidada"), "",
         "## Resumen", "", "| Severidad | Abiertos | Confirmados | Persistentes | Reincidentes |", "|---|---|---|---|---|"]
    for s in SEVERIDADES:
        g = [h for h in abiertos if h["severidad"] == s]
        o.append(f"| {ICONO[s]} {s} | {len(g)} | {sum(1 for h in g if h['confianza'] == 'confirmado')} | "
                 f"{sum(1 for h in g if h['historial'] == 'persistente')} | "
                 f"{sum(1 for h in g if h['historial'] == 'reincidente')} |")
    o += ["", f"Nuevos: {sum(1 for h in abiertos if h['historial'] == 'nuevo')} · "
              f"Persistentes: {sum(1 for h in abiertos if h['historial'] == 'persistente')} · "
              f"Reincidentes: {sum(1 for h in abiertos if h['historial'] == 'reincidente')} · "
              f"No reaparecen desde la anterior: {len(no_reaparecen)} · Cerrados en esta: {len(cerrados)}", ""]
    urg = [h for h in abiertos if h["severidad"] == "critica"]
    if urg:
        o += ["## 🟥 Urgente", ""]
        o += [f"- **{h['id']} · {h['titulo']}** ({h['confianza']}) — {h.get('impacto', '')} "
              f"**Qué hacer:** {h['propuesta']}" for h in urg]
        o.append("")
    o += ["## Hallazgos abiertos", "",
          "| ID | Sev. | Confianza | Categoría | Hallazgo | Dónde | Equipos | Historial |", "|---|---|---|---|---|---|---|---|"]
    for h in abiertos:
        o.append(f"| {h['id']} | {ICONO[h['severidad']]} {h['severidad']} | {h['confianza']} | {h['categoria']} | "
                 f"{_celda(h['titulo'])} | {_celda(_donde(h))} | {', '.join(h['equipos'])} | {h['historial']} |")
    o += ["", "## Detalle (crítica, alta y media)", ""]
    for h in abiertos:
        if h["severidad"] not in ("critica", "alta", "media"):
            continue
        ev = h.get("evidencia") or {}
        o += [f"### {h['id']} · {h['titulo']}", "",
              f"- **Severidad / confianza:** {h['severidad']} / {h['confianza']}"
              + (f" (subida desde {h['severidad_original']} por reincidente)" if h.get("severidad_original") else ""),
              f"- **Dónde:** {_donde(h)}" + (f" — `{ev['extracto']}`" if ev.get("extracto") else ""),
              *( [f"- **Comando / petición:** `{ev['comando']}`"] if ev.get("comando") and ev.get("archivo") else []),
              f"- **Impacto:** {h.get('impacto', '—')}",
              *( [f"- **Cómo se explotaría:** {h['escenario']}"] if h.get("escenario") else []),
              f"- **Cambio propuesto:** {h['propuesta']}",
              f"- **Esfuerzo:** {h.get('esfuerzo', '—')} puntos · **Referencia:** {h.get('referencia') or '—'}",
              *( [f"- **Lección:** {h['leccion']}"] if h.get("leccion") else []),
              *( [f"- **Incumple:** {h['incumple_leccion']} de docs/06-lecciones-aprendidas.md"] if h.get("incumple_leccion") else []),
              *( [f"- **Fusionado con:** {', '.join(h['fusionados'])}"] if h.get("fusionados") else []),
              ""]
    if cerrados:
        o += ["## Descartados, aceptados y corregidos", "", "| ID | Estado | Hallazgo | Nota |", "|---|---|---|---|"]
        o += [f"| {h['id']} | {h['estado']} | {_celda(h['titulo'])} | {_celda(h.get('nota', ''))} |" for h in cerrados]
        o.append("")
    if no_reaparecen:
        o += ["## No reaparecen desde la auditoría anterior", "",
              "Verifica que se corrigieron (no que el equipo que los encontró dejó de correr):", ""]
        o += [f"- {h['id']} · {h['titulo']} ({h['severidad']})" for h in no_reaparecen]
        o.append("")
    o += ["## Siguiente paso", "",
          "1. Presentar al dueño el resumen y registrar sus decisiones en `plan.md`.",
          "2. `auditar.py casos --proyecto RUTA --anexar` → etapa de endurecimiento en docs/05.",
          "3. `auditar.py lecciones --proyecto RUTA` → docs/06-lecciones-aprendidas.md.", ""]
    return "\n".join(o)


# ------------------------------------------------------------------ casos
def _insertar_fila_tabla(texto, encabezado, fila):
    i = texto.find(encabezado)
    if i == -1:
        return texto
    lineas = texto[i:].split("\n")
    n = 0
    while n < len(lineas) and lineas[n].startswith("|"):
        n += 1
    corte = i + len("\n".join(lineas[:n]))
    return texto[:corte] + "\n" + fila + texto[corte:]


def cmd_casos(args):
    raiz = raiz_de(args)
    d = dir_auditoria(raiz, args.fecha)
    if not (d / "hallazgos.json").exists():
        print(f"❌ Falta {d / 'hallazgos.json'}: corre `consolidar` primero.")
        return 1
    hallazgos = [h for h in leer_json(d / "hallazgos.json")
                 if h["estado"] == "abierto" and h["severidad"] != "info"
                 and (args.incluir_posibles or h["confianza"] != "posible")]
    cu = raiz / "docs" / "05-casos-de-uso.md"
    texto05 = cu.read_text(encoding="utf-8") if cu.exists() else ""
    etiqueta = f"Endurecimiento (auditoría {d.name})"
    etapas = [int(x) for x in re.findall(r"^##\s+E(\d+)\b", texto05, re.M)]
    n_etapa = max(etapas) + 1 if etapas else 1
    siguiente = {}
    for pref in ("SEC", "CAL", "MET"):
        usados = [int(x) for x in re.findall(rf"UC-{pref}-(\d+)", texto05)]
        siguiente[pref] = max(usados) + 1 if usados else 1

    proyecto = [h for h in hallazgos if h.get("alcance") != "metodo"]
    metodo = [h for h in hallazgos if h.get("alcance") == "metodo"]

    def caso(h, pref):
        uid = f"UC-{pref}-{siguiente[pref]:02d}"
        siguiente[pref] += 1
        pts = h.get("esfuerzo") if h.get("esfuerzo") in FIBONACCI else 3
        return uid, f"Corregir: {_celda(h['titulo'])} ({h['id']})", PRIORIDAD.get(h["severidad"], "🟩"), pts

    filas, fichas = [], []
    for h in proyecto:
        pref = "CAL" if h["categoria"] in CATEGORIAS_CAL else "SEC"
        uid, nombre, prio, pts = caso(h, pref)
        actor = "Dueño del proyecto" if h["categoria"] == "proveedor" else "Equipo de desarrollo"
        filas.append(f"| {uid} | {nombre} | {actor} | {prio} | {pts} | ⬜ |")
        if prio == "🟥":
            ev = h.get("evidencia") or {}
            prueba = ev.get("comando") if ev.get("comando") and ev.get("comando") != "auditar.py escanear" \
                else ("`auditar.py escanear` ya no lo reporta" if h["equipo"] == "EST" else f"la evidencia de {_donde(h)} ya no se reproduce")
            fichas += [f"### {uid} · {nombre}",
                       f"- **Actor:** {actor}" + ("" if actor.startswith("Dueño") else " (agente), con aprobación del dueño"),
                       f"- **Precondición:** hallazgo {h['id']} ({h['severidad']}, {h['confianza']}) abierto en la auditoría {d.name}.",
                       f"- **Disparador:** informe `docs/auditoria/{d.name}/informe.md`.",
                       f"- **Flujo principal:** {h['propuesta']}",
                       "- **Alternativas:** si el dueño acepta el riesgo, el hallazgo pasa a `aceptado` con su motivo y el caso se cierra sin código.",
                       f"- **Reglas de negocio:** {h.get('leccion') or 'RG-01: el cambio queda registrado con actor, fecha y motivo.'}",
                       f"- **Criterio de aceptación:** {prueba}; una auditoría rápida no lo reproduce.", ""]
    bloque = []
    if filas:
        bloque = [f"## E{n_etapa} · {etiqueta}", "",
                  "**Criterio de salida:** una auditoría rápida de re-verificación no reproduce ninguno de "
                  "los hallazgos de esta etapa y `auditar.py consolidar` no muestra críticos ni altos abiertos.", "",
                  f"Origen: `docs/auditoria/{d.name}/informe.md`. Los casos 🟥 se construyen **antes** de seguir "
                  "con la etapa en curso, aunque esta etapa tenga un número mayor.", "",
                  "| ID | Caso de uso | Actor | Prioridad | Puntos | Estado |", "|---|---|---|---|---|---|",
                  *filas, "", *fichas]
        (d / "casos-de-mejora.md").write_text("\n".join(bloque) + "\n", encoding="utf-8")
        print(f"✅ {d / 'casos-de-mejora.md'}: {len(filas)} casos ({sum('🟥' in f for f in filas)} 🟥)")
    else:
        print("ℹ️  No hay hallazgos abiertos de proyecto que conviertan en casos.")

    if metodo:
        m = [f"# Mejoras propuestas al método · auditoría {d.name} · {raiz.name}", "",
             "Problemas que nacen de las plantillas, guías o checklists de `diseno-express-de-apps` o de "
             "`auditoria-express-de-apps`, no solo de este proyecto. Aplicarlas en el repositorio de skills "
             "requiere aprobación del dueño.", "",
             "| ID | Mejora | Origen | Prioridad | Puntos | Propuesta |", "|---|---|---|---|---|---|"]
        for h in metodo:
            uid, nombre, prio, pts = caso(h, "MET")
            m.append(f"| {uid} | {_celda(h['titulo'])} | {h['id']} | {prio} | {pts} | {_celda(h['propuesta'])} |")
        (d / "casos-metodo.md").write_text("\n".join(m) + "\n", encoding="utf-8")
        print(f"✅ {d / 'casos-metodo.md'}: {len(metodo)} mejoras al método")

    if args.anexar and bloque:
        if not cu.exists():
            print("⚠️  No existe docs/05-casos-de-uso.md: no se anexó (el bloque está en casos-de-mejora.md).")
        elif etiqueta in texto05:
            print("⏭️  docs/05 ya tiene la etapa de esta auditoría: no se anexó de nuevo.")
        else:
            nuevo = _insertar_fila_tabla(texto05, "| Prefijo | Módulo | Etapa |",
                                         f"| SEC / CAL | Endurecimiento (auditorías) | E{n_etapa} |") \
                if "| SEC" not in texto05 else texto05
            nuevo = _insertar_fila_tabla(nuevo, "| Etapa | Propósito |",
                                         f"| E{n_etapa} | {etiqueta} | SEC, CAL | según puntos | "
                                         "Una auditoría rápida no reproduce sus hallazgos |")
            corte = nuevo.find("\n## Reglas globales")
            texto_bloque = "\n".join(bloque).rstrip() + "\n"
            nuevo = (nuevo[:corte + 1] + texto_bloque + "\n" + nuevo[corte + 1:]) if corte != -1 \
                else nuevo.rstrip() + "\n\n" + texto_bloque
            cu.write_text(nuevo, encoding="utf-8")
            print(f"✅ Anexada la etapa E{n_etapa} a {cu}. Valida con expres.py validar.")
    return 0


# ------------------------------------------------------------------ lecciones
def _norm(t):
    return re.sub(r"[\W_]+", " ", t.lower()).strip()


def cmd_lecciones(args):
    raiz = raiz_de(args)
    d = dir_auditoria(raiz, args.fecha)
    if not (d / "hallazgos.json").exists():
        print(f"❌ Falta {d / 'hallazgos.json'}: corre `consolidar` primero.")
        return 1
    p, texto, filas = leer_lecciones(raiz)
    if texto is None:
        texto = plantilla("06-lecciones-aprendidas.md", {"{{PROYECTO}}": raiz.name, "{{FECHA}}": d.name})
        print(f"✅ creado: {p}")
    if "<!-- LECCIONES:INICIO -->" not in texto:
        print(f"❌ {p} no tiene los marcadores <!-- LECCIONES:INICIO --> / <!-- LECCIONES:FIN -->.")
        return 1
    nuevas = actualizadas = 0
    siguiente = max([int(f["id"][3:]) for f in filas] + [0]) + 1
    for h in leer_json(d / "hallazgos.json"):
        if not h.get("leccion") or h["estado"] == "descartado" or h["confianza"] == "posible" \
                or h.get("historial") == "persistente":
            continue   # pistas sin confirmar no son reglas; lo persistente ya está registrado
        huellas = h.get("huellas") or [h["huella"]]
        marca = f"{d.name} {h['id']}" + "".join(f" r:{r}" for r in h.get("reglas") or []) + f" h:{h['huella']}"
        fila = next((f for f in filas if any(f"h:{x}" in f["origen"] for x in huellas)), None) or \
            next((f for f in filas if _norm(f["leccion"]) == _norm(h["leccion"])), None)
        if fila:
            if d.name in fila["origen"] and f"h:{h['huella']}" in fila["origen"]:
                continue
            if d.name not in fila["origen"]:
                fila["veces"] += 1
            fila["origen"] += f"; {marca}"
            actualizadas += 1
        else:
            filas.append({"id": f"LA-{siguiente:03d}", "leccion": _celda(h["leccion"]), "categoria": h["categoria"],
                          "origen": marca, "primera": d.name, "veces": 1})
            siguiente += 1
            nuevas += 1
    tabla = ["| ID | Lección | Categoría | Origen | Primera vez | Veces |", "|---|---|---|---|---|---|"]
    tabla += [f"| {f['id']} | {f['leccion']} | {f['categoria']} | {f['origen']} | {f['primera']} | {f['veces']} |"
              for f in filas]
    texto = re.sub(r"<!-- LECCIONES:INICIO -->\n[\s\S]*?<!-- LECCIONES:FIN -->",
                   lambda _: "<!-- LECCIONES:INICIO -->\n" + "\n".join(tabla) + "\n<!-- LECCIONES:FIN -->", texto)
    p.write_text(texto, encoding="utf-8")
    print(f"✅ {p}: {nuevas} nuevas, {actualizadas} actualizadas, {len(filas)} en total.")
    for f in filas:
        if f["veces"] >= 2:
            print(f"🔁 {f['id']} se repitió {f['veces']} veces: candidata a lección del método "
                  "(references/lecciones-aprendidas.md o la guía de diseno-express-de-apps).")
    return 0


# ------------------------------------------------------------------ automatizar
def tablas_publicas(raiz):
    """Tablas de public creadas por las migraciones (y no borradas), en orden de creación."""
    creadas, borradas = [], set()
    for p in sorted((raiz / "supabase" / "migrations").glob("*.sql")):
        t = re.sub(r"--[^\n]*", "", re.sub(r"/\*[\s\S]*?\*/", "", p.read_text(encoding="utf-8")))
        for m in re.finditer(r"(create|drop)\s+table\s+(?:if\s+(?:not\s+)?exists\s+)?(?:\"?(\w+)\"?\.)?\"?(\w+)\"?", t, re.I):
            if (m.group(2) or "public").lower() != "public":
                continue
            nombre = m.group(3).lower()
            if m.group(1).lower() == "create" and nombre not in creadas:
                creadas.append(nombre)
                borradas.discard(nombre)
            elif m.group(1).lower() == "drop":
                borradas.add(nombre)
    return [x for x in creadas if x not in borradas]


def pruebas_rls(tablas, publicas):
    privadas = [x for x in tablas if x not in publicas]
    o = ["-- Generado por auditoria-express-de-apps (auditar.py automatizar). Se ejecuta con: supabase test db",
         "-- Pruebas estructurales (valen para tablas futuras) + pruebas de acceso por tabla.",
         "-- Las de acceso solo significan algo si supabase/seed.sql inserta filas en cada tabla.",
         f"-- Tablas tratadas como catálogo público (sin prueba de acceso): {', '.join(publicas) or 'ninguna'}.",
         "-- Pruebas de aislamiento entre organizaciones (A no ve lo de B): escríbelas en 01_aislamiento.test.sql",
         "-- a partir de la columna 'Qué NO puede hacer' de los actores en docs/05-casos-de-uso.md.",
         "begin;", "create extension if not exists pgtap with schema extensions;",
         f"select plan({3 + 2 * len(privadas)});", "",
         "select is_empty($$ select c.relname::text from pg_class c join pg_namespace n on n.oid = c.relnamespace",
         "  where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity $$,",
         "  'Todas las tablas de public tienen RLS');",
         "select is_empty($$ select p.proname::text from pg_proc p join pg_namespace n on n.oid = p.pronamespace",
         "  where n.nspname = 'public' and p.prosecdef and not exists",
         "  (select 1 from unnest(coalesce(p.proconfig, '{}')) cfg where cfg like 'search_path=%') $$,",
         "  'Las funciones security definer tienen search_path fijo');",
         "select is_empty($$ select c.relname::text from pg_class c join pg_namespace n on n.oid = c.relnamespace",
         "  where n.nspname = 'public' and c.relkind = 'v'",
         "  and not coalesce('security_invoker=true' = any(c.reloptions), false) $$,",
         "  'Las vistas de public usan security_invoker');", ""]
    if privadas:
        o += ["-- true si el rol actual ve al menos una fila; un permiso denegado también cuenta como seguro.",
              "create function pg_temp.ve_filas(tabla text) returns boolean language plpgsql as $f$",
              "declare n int;", "begin",
              "  execute format('select count(*) from (select 1 from %s limit 1) x', tabla) into n;",
              "  return n > 0;",
              "exception when insufficient_privilege then return false;", "end $f$;", "",
              "-- Visitante sin sesión (clave anon)", "set local role anon;"]
        o += [f"select ok(not pg_temp.ve_filas('public.{x}'), 'anon no ve filas de public.{x}');" for x in privadas]
        o += ["reset role;", "",
              "-- Usuario autenticado que no pertenece a ninguna organización",
              "set local request.jwt.claims = '{\"sub\": \"00000000-0000-4000-8000-0000000000aa\", \"role\": \"authenticated\"}';",
              "set local role authenticated;"]
        o += [f"select ok(not pg_temp.ve_filas('public.{x}'), 'un usuario ajeno no ve filas de public.{x}');"
              for x in privadas]
        o += ["reset role;", ""]
    o += ["select * from finish();", "rollback;", ""]
    return "\n".join(o)


def cmd_automatizar(args):
    raiz = raiz_de(args)
    prueba = raiz / "supabase" / "tests" / "00_auditoria_rls.test.sql"
    lista = args.publicas
    if lista is None and prueba.exists():   # recuerda el catálogo público de la generación anterior
        m = re.search(r"catálogo público \(sin prueba de acceso\): (.*)\.$", prueba.read_text(encoding="utf-8"), re.M)
        lista = "" if not m or m.group(1) == "ninguna" else m.group(1)
    publicas = [x.strip().lower() for x in (lista or "").split(",") if x.strip()]
    tablas = tablas_publicas(raiz)
    flujo = (PLANTILLAS / "ci" / "auditoria.yml").read_text(encoding="utf-8")
    con_supabase = (raiz / "supabase" / "config.toml").exists()
    flujo = flujo.replace("# --- rls ---\n", "") if con_supabase else flujo.split("# --- rls ---")[0]
    nombre = raiz.name
    archivos = [
        (raiz / ".github" / "workflows" / "auditoria.yml", flujo, False),
        (raiz / ".github" / "dependabot.yml", (PLANTILLAS / "ci" / "dependabot.yml").read_text(encoding="utf-8"), False),
        (raiz / "docs" / "incidentes" / "llave-filtrada.md", plantilla("llave-filtrada.md", {"{{PROYECTO}}": nombre}), False),
        (raiz / "scripts" / "auditoria" / "auditar.py", Path(__file__).read_text(encoding="utf-8"), True),
    ]
    if con_supabase or tablas:
        archivos.append((raiz / "supabase" / "tests" / "00_auditoria_rls.test.sql", pruebas_rls(tablas, publicas), True))
    for destino, contenido, regenerable in archivos:
        rel = destino.relative_to(raiz)
        if destino.exists() and destino.read_text(encoding="utf-8") == contenido:
            print(f"⏭️  al día: {rel}")
            continue
        if destino.exists() and not regenerable:
            print(f"⏭️  omitido (ya existe, no se sobrescribe): {rel}")
            continue
        accion = "actualizar" if destino.exists() else "crear"
        if not args.escribir:
            print(f"📝 {accion}: {rel}")
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        print(f"✅ {'creado' if accion == 'crear' else 'actualizado'}: {rel}")
    if not con_supabase:
        print("ℹ️  Sin supabase/config.toml: el workflow no incluye pruebas de RLS (corre `npx supabase init`).")
    if tablas:
        print(f"Tablas con prueba de acceso: {', '.join(x for x in tablas if x not in publicas) or 'ninguna'}"
              + (f" · catálogo público: {', '.join(publicas)}" if publicas else ""))
    if not args.escribir:
        print("\nVista previa: repite con --escribir para crear los archivos.")
    else:
        print("\nSiguiente: completa los contactos de docs/incidentes/llave-filtrada.md, escribe las pruebas de "
              "aislamiento entre organizaciones y prueba localmente con `npx supabase test db` (requiere Docker).")
    return 0


# ------------------------------------------------------------------ estado
def cmd_estado(args):
    raiz = raiz_de(args)
    base = raiz / "docs" / "auditoria"
    dirs = sorted(p for p in base.glob("????-??-??") if p.is_dir()) if base.exists() else []
    print(f"Proyecto: {raiz}")
    if not dirs:
        print("  Sin auditorías. Empieza con `auditar.py iniciar`.")
    ultimo = None
    for dd in dirs:
        hj = dd / "hallazgos.json"
        if hj.exists():
            hs = [h for h in leer_json(hj) if h["estado"] == "abierto"]
            print(f"  {dd.name}: " + " · ".join(f"{ICONO[s]} {sum(1 for h in hs if h['severidad'] == s)}"
                                                for s in SEVERIDADES) + " abiertos")
            ultimo = hs
        else:
            print(f"  {dd.name}: sin consolidar ({len(list(dd.glob('hallazgos-*.json')))} archivos de equipos)")
    if ultimo:
        graves = [h for h in ultimo if h["severidad"] in ("critica", "alta")]
        if graves:
            print("\nCríticos y altos abiertos en la última auditoría consolidada:")
            for h in graves:
                print(f"  {ICONO[h['severidad']]} {h['id']} {h['titulo']} ({h['confianza']}, {h['historial']})")
    _, texto, filas = leer_lecciones(raiz)
    if texto is None:
        print("\nLecciones: no existe docs/06-lecciones-aprendidas.md")
    else:
        print(f"\nLecciones registradas: {len(filas)}"
              + (f" · repetidas: {', '.join(f['id'] for f in filas if f['veces'] >= 2)}"
                 if any(f["veces"] >= 2 for f in filas) else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Utilidades de la skill auditoria-express-de-apps.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("iniciar", "escanear", "consolidar", "casos", "lecciones", "automatizar", "estado"):
        p = sub.add_parser(nombre)
        p.add_argument("--proyecto", required=True)
        if nombre not in ("estado", "automatizar"):
            p.add_argument("--fecha", help="AAAA-MM-DD (por defecto hoy o la última auditoría)")
    sub.choices["iniciar"].add_argument("--nombre")
    sub.choices["escanear"].add_argument("--incluir-build", action="store_true")
    sub.choices["escanear"].add_argument("--sin-historial", action="store_true",
                                         help="no revisar el contenido de los commits anteriores")
    sub.choices["escanear"].add_argument("--ci", action="store_true",
                                         help="no escribe archivos; sale con 1 si hay críticos o altos no aceptados")
    sub.choices["casos"].add_argument("--anexar", action="store_true")
    sub.choices["automatizar"].add_argument("--escribir", action="store_true",
                                            help="crear los archivos (sin esto, solo muestra qué haría)")
    sub.choices["automatizar"].add_argument("--publicas", help="tablas de catálogo público, separadas por comas")
    sub.choices["casos"].add_argument("--incluir-posibles", action="store_true")
    args = ap.parse_args()
    return {"iniciar": cmd_iniciar, "escanear": cmd_escanear, "consolidar": cmd_consolidar,
            "casos": cmd_casos, "lecciones": cmd_lecciones, "automatizar": cmd_automatizar,
            "estado": cmd_estado}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
