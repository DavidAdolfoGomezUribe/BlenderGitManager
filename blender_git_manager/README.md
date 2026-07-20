# Blender Git Manager

**Blender Git Manager** es una extensión para Blender 4.2 o superior que integra un flujo visual de Git, Git LFS y GitHub CLI dentro de Blender. Está dirigida a artistas 3D y equipos que trabajan con archivos binarios grandes y quieren crear versiones sin escribir comandos manualmente.

Esta entrega implementa una base ejecutable del **MVP** descrito en el documento de requisitos. La arquitectura está preparada para ampliar posteriormente stash, merges, resolución avanzada de conflictos, GitLab y Bitbucket.

## Funciones incluidas en el MVP

- Menú **Git** en la barra superior de Blender.
- Panel **Git** en la barra lateral de la Vista 3D.
- Ventana amplia emergente con el panel principal.
- Detección de `git`, `git lfs` y `gh`.
- Autenticación de GitHub mediante `gh auth login --web`, con código temporal visible y recopiable.
- Detección automática del repositorio que contiene el archivo `.blend`.
- Asociación visible de otro repositorio con la sesión actual.
- Asistente visual para inicializar un repositorio.
- Selección de carpeta, nombre, rama inicial e identidad Git.
- Generación o ampliación segura de `.gitignore`.
- Inicialización local de Git LFS y selección de patrones frecuentes.
- Guardado del `.blend` dentro del repositorio antes de inicializar.
- Stage all o stage recomendado y creación del primer commit.
- Creación opcional de un repositorio en GitHub con `gh repo create`.
- Apertura de repositorios existentes.
- Clonación mediante Git o GitHub CLI.
- Descarga posterior de objetos LFS cuando el repositorio usa `.gitattributes`.
- Lista visual de archivos modificados, nuevos, staged y en conflicto.
- Stage y unstage por archivo, por selección o global.
- Descarte de cambios con confirmación.
- Campo visual para título y descripción del commit.
- Guardado automático de Blender antes del commit.
- Commit y Commit + Push.
- Quick Save desde el menú superior: prepara todos los cambios, crea `Quick Save N` y publica la rama activa.
- Fetch, Pull `--ff-only`, Push y Sync.
- Recuperación limitada de pushes LFS ante locks no disponibles y errores transitorios HTTP 5xx.
- Detección de upstream, commits ahead y behind.
- Git Graph estructurado con 200 commits iniciales, carga incremental hasta 1000, carriles, bifurcaciones y merges.
- Identificación visual de HEAD, ramas locales/remotas y tags, con búsqueda y filtros.
- Detalles del commit seleccionado, archivos modificados, estadísticas y acciones de History.
- Botón **Load Selected Commit** para materializar todo el árbol y recargar la escena en `Detached HEAD`.
- Carga de History y detalles en segundo plano sin acceder a la API de Blender desde el worker.
- Lista de ramas locales y remotas.
- Creación y cambio de rama con respaldo previo y recarga automática del `.blend` de la rama destino.
- Gestión inicial de patrones Git LFS.
- Panel de salida amigable y sin secretos.
- Operaciones de red mediante operadores modales para evitar congelar la interfaz.
- Pruebas unitarias e integración local para módulos que no dependen de `bpy`.

## Requisitos

- Blender 4.2 o superior.
- Windows 10 u 11 para el objetivo inicial.
- Git instalado y disponible en `PATH`.
- Git LFS instalado.
- GitHub CLI para autenticación y operaciones específicas de GitHub.

El complemento continúa ofreciendo Git local cuando GitHub CLI no está instalado. Git LFS solo se exige cuando el usuario lo activa.

## Instalación rápida

1. Descarga `blender_git_manager-0.1.7.zip`.
2. En Blender abre **Edit > Preferences > Add-ons** o **Extensions**.
3. Selecciona **Install from Disk**.
4. Elige el ZIP sin descomprimirlo.
5. Habilita **Blender Git Manager**.
6. Abre el menú superior **Git > Open Git Manager**.
7. Presiona **Refresh** para comprobar las dependencias.

## Primer flujo recomendado

1. Guarda o abre tu proyecto Blender.
2. Abre **Git > Initialize Repository**.
3. Confirma la carpeta y la rama `main`.
4. Configura nombre y correo de Git.
5. Mantén activo **Create Blender .gitignore**.
6. Activa Git LFS y, como mínimo, `*.blend`.
7. Selecciona **Stage All** o **Stage Recommended**.
8. Crea el commit inicial.
9. Para publicar en GitHub, autentícate con **Connect in Browser**.
10. Crea el remoto desde el asistente o desde **Create on GitHub**.

## Estructura

```text
blender_git_manager/
├── __init__.py                  Registro principal y temporizador de actualización
├── blender_manifest.toml        Manifiesto de extensión Blender 4.2+
├── constants.py                 Patrones y valores predeterminados
├── preferences.py               Preferencias y rutas de ejecutables
├── properties.py                Estado RNA visible por la interfaz
├── state_sync.py                Sincronización servicios → propiedades de Blender
├── models/
│   ├── __init__.py
│   ├── domain.py                Modelos generales independientes de Blender
│   └── history.py               Modelos tipados del Git Graph y sus detalles
├── operators/
│   ├── __init__.py              Registro ordenado de operadores
│   ├── base.py                  Infraestructura modal para tareas largas
│   ├── authentication.py        Login y logout de GitHub CLI
│   ├── repository.py            Init, open, clone, remote y GitHub repo
│   ├── staging.py               Stage, unstage y discard
│   ├── commits.py               Commit, Commit + Push y Quick Save
│   ├── synchronization.py       Fetch, pull, push y sync
│   ├── branches.py              Crear y cambiar ramas
│   ├── history.py               Checkout de commits y recarga segura de la escena
│   ├── history_actions.py       Acciones del commit seleccionado
│   ├── history_runtime.py       Coordinador asíncrono History → hilo principal
│   ├── lfs.py                   Track y untrack de patrones LFS
│   └── common.py                Refresh, carpetas, navegador y preferencias
├── services/
│   ├── process_service.py       Único punto de ejecución de procesos
│   ├── git_service.py           Fachada de comandos Git
│   ├── lfs_service.py           Fachada de Git LFS
│   ├── github_service.py        Fachada de GitHub CLI
│   ├── repository_service.py    Flujos de negocio compuestos
│   ├── lfs_push_failures.py     Clasificación segura y recuperación de errores LFS
│   ├── history_parser.py        Parser estructurado del historial Git
│   ├── history_diff_parser.py   Parser NUL-safe de archivos y estadísticas
│   ├── history_service.py       Consultas, filtros y detalles de History
│   ├── graph_layout_service.py  Algoritmo independiente de carriles
│   ├── status_parser.py         Parser de git status porcelain
│   ├── background_task_service.py Cola reutilizable de tareas
│   └── credential_service.py    Política explícita de no almacenar secretos
├── ui/
│   ├── __init__.py
│   ├── top_menu.py              Menú Git superior
│   ├── main_panel.py            Panel lateral
│   ├── dashboard.py             Diseño del administrador principal
│   └── lists.py                 UILists de cambios, commits, ramas y salida
└── utils/
    ├── __init__.py
    ├── backups.py               Respaldo timestamp del archivo Blender
    ├── checkout.py              Planificación y rollback seguro del árbol Git
    ├── formatting.py            Tamaños y redacción de argumentos
    ├── paths.py                 Normalización y relación entre rutas
    └── validation.py            Validación de refs, nombres y carpetas
```

## Seguridad

Todos los procesos pasan por `ProcessService` y usan:

```python
subprocess.Popen(
    [executable, *arguments],
    shell=False,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
```

La salida se consume de forma incremental desde lectores separados para evitar bloqueos, se envía a la consola de Blender y se incorpora a `Git Output` desde el hilo principal. No se concatenan comandos, no se ejecuta texto arbitrario y no existe una API para guardar tokens. Las credenciales siguen bajo responsabilidad de GitHub CLI, Git Credential Manager o el agente SSH del sistema.

El registro redacta argumentos y salida relacionados con `token`, `password`, `secret`, `credential`, cabeceras de autorización, credenciales en URL y códigos OAuth temporales. El `.gitignore` recomendado bloquea `.env`, claves privadas y `credentials.json`.

## Comandos principales utilizados

```text
git rev-parse --show-toplevel
git init -b main
git config user.name ...
git config user.email ...
git status --porcelain=v1 --untracked-files=all
git add -- <archivos>
git add --all
git restore --staged -- <archivos>
git commit -m <título> -m <descripción>
git commit -m "Quick Save N"
git fetch origin --prune
git pull --ff-only
git push origin
git push [-u] <remoto> <rama>:refs/heads/<rama-remota>
git -c lfs.<url>.locksverify=false push ...
git log --all --pretty=format:<formato estructurado>
git for-each-ref ...
git lfs install --local
git lfs track <patrón>
git lfs ls-files --long --size
gh auth login --hostname github.com --git-protocol https --web --clipboard
gh auth status --hostname github.com
gh repo create ... --source . --remote origin --push
gh repo clone owner/repository destino
```

## Desarrollo y pruebas

Las pruebas no necesitan Blender porque los servicios y modelos no importan `bpy`.

```bash
cd blender_git_manager_project
python -m unittest discover -s tests -v
```

Para comprobar sintaxis:

```bash
python -m compileall blender_git_manager
```

Para construir el ZIP manualmente desde la carpeta del complemento:

```bash
cd blender_git_manager
python ../build_extension.py
```

También puede usarse el comando oficial de Blender para construir extensiones desde la carpeta que contiene `blender_manifest.toml`.

## Depuración dentro de Blender

- Activa **Show developer output** en las preferencias del complemento.
- Abre **Window > Toggle System Console** en Windows para ver comandos, stdout, stderr, duración y código de salida en tiempo real.
- Utiliza la pestaña **Output** del panel Git para revisar las mismas operaciones, incluso antes de abrir o inicializar un repositorio.
- Para recargar durante desarrollo, desactiva y vuelve a activar la extensión.
- Evita modificar datos de Blender desde hilos secundarios. Los operadores modales aplican resultados desde el hilo principal.

## Limitaciones de esta primera versión

- El Git Graph usa componentes nativos de Blender; los carriles se distinguen mediante nodos de color y conexiones ortogonales adaptadas al ancho disponible.
- No implementa aún stash, creación de merges ni reset desde la interfaz.
- Los conflictos `.blend` se detectan, pero la resolución guiada y el respaldo de ambas variantes pertenecen a la siguiente fase.
- Pull usa `--ff-only` para evitar merges automáticos inesperados.
- Presionar Escape solicita la terminación del proceso externo y mantiene la tarea ocupada hasta confirmar su finalización.
- El asistente usa modos Stage All, Recommended o None; la selección individual posterior se realiza desde Changes.
- Abrir un repositorio no abre silenciosamente otro `.blend`.
- Git y Git LFS no pueden fusionar geometría, materiales o animaciones dentro de un `.blend` binario.

## Próximas fases

Consulta `docs/ROADMAP.md` para el diseño de stash, merges controlados, conflictos binarios, bloqueo de archivos, proveedores adicionales y colaboración en equipo.

## Licencia

GPL-3.0-or-later.
