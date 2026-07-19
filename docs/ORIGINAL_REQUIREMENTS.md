# Prompt para desarrollar un add-on de control de versiones Git y Git LFS para Blender

Quiero desarrollar un add-on profesional para Blender que permita gestionar repositorios Git y GitHub directamente desde la interfaz gráfica de Blender, sin que el usuario tenga que escribir comandos manualmente en una terminal.

El add-on debe funcionar como una interfaz visual similar a las herramientas de control de versiones de Visual Studio Code, Visual Studio y extensiones como Git Graph.

El objetivo principal es permitir que artistas 3D, diseñadores y desarrolladores puedan guardar versiones de archivos `.blend`, modelos, texturas, animaciones y otros recursos pesados mediante Git y Git LFS, usando una interfaz intuitiva integrada en Blender.

## 1. Objetivo general

Desarrollar un add-on para Blender escrito en Python que permita:

* Conectar Blender con Git.
* Conectar Blender con GitHub.
* Utilizar Git LFS para archivos grandes.
* Autenticarse en GitHub mediante el navegador.
* Crear commits sin utilizar la consola.
* Ejecutar operaciones comunes de Git desde botones y formularios.
* Visualizar ramas, commits, autores y cambios.
* Mostrar un gráfico visual del historial Git.
* Administrar repositorios desde la interfaz de Blender.
* Inicializar visualmente un repositorio Git nuevo desde la carpeta del archivo `.blend` o desde una carpeta seleccionada, sin utilizar una terminal.
* Guardar automáticamente el archivo `.blend` antes de crear un commit.
* Evitar almacenar contraseñas o tokens directamente dentro del add-on.

El add-on no debe implementar Git desde cero. Debe utilizar los ejecutables instalados en el sistema:

* `git`
* `git-lfs`
* `gh`, GitHub CLI

La comunicación debe realizarse desde Python mediante `subprocess`, usando siempre listas de argumentos y `shell=False`.

## 2. Nombre provisional

Nombre del add-on:

```text
Blender Git Manager
```

Otros nombres posibles:

```text
Blend Version Control
BlendGit
Git Tools for Blender
Blender Git Graph
```

## 3. Compatibilidad

El add-on debe diseñarse inicialmente para:

* Blender 4.2 o superior.
* Windows 10 y Windows 11.
* Git instalado en el sistema.
* Git LFS instalado.
* GitHub CLI instalada para autenticación mediante navegador.

Posteriormente debe poder ampliarse para:

* Linux.
* macOS.

La arquitectura debe evitar rutas absolutas específicas de Windows cuando sea posible.

## 4. Integración en la interfaz de Blender

El add-on debe integrarse en la barra superior principal de Blender, donde aparecen menús como:

```text
File
Edit
Render
Window
Help
```

Se debe añadir un nuevo menú:

```text
Git
```

Ejemplo:

```text
File | Edit | Render | Window | Git | Help
```

El menú Git debe contener accesos rápidos como:

```text
Git
├── Open Git Manager
├── Initialize Repository
├── Open Existing Repository
├── Clone Repository
├── Repository Status
├── Save and Commit
├── Pull
├── Push
├── Fetch
├── Branches
├── Git LFS
├── GitHub Authentication
└── Settings
```

Además del menú superior, el add-on debe incluir una ventana principal o panel amplio para administrar el repositorio.

La ventana puede implementarse inicialmente como:

* Panel lateral en la Vista 3D.
* Ventana emergente.
* Área personalizada.
* Editor reutilizando un espacio existente.
* Panel independiente accesible desde el menú Git.

La prioridad es crear una interfaz amplia, clara y organizada, no limitar toda la funcionalidad a un panel lateral estrecho.

## 5. Ventana principal Git Manager

La ventana principal debe estar dividida en secciones.

### Encabezado del repositorio

Debe mostrar:

* Nombre del repositorio.
* Ruta local.
* URL remota.
* Proveedor remoto, inicialmente GitHub.
* Rama activa.
* Estado de sincronización.
* Último commit.
* Autor del último commit.
* Indicador de conexión con GitHub.
* Indicador de Git LFS.
* Indicador de archivos modificados.

Ejemplo:

```text
Repository: TankGameAssets
Branch: main
Remote: github.com/david/TankGameAssets
Status: 3 modified files
Git LFS: Active
GitHub: Authenticated
```

Debe incluir botones:

```text
Refresh
Open Repository Folder
Open on GitHub
Settings
```

Cuando el archivo `.blend` actual no pertenezca a un repositorio Git, la ventana no debe aparecer vacía ni limitarse a mostrar un error. Debe mostrar una pantalla inicial de incorporación:

```text
No Git repository detected

[Initialize Repository]
[Open Existing Repository]
[Clone from GitHub]
```

La acción principal debe ser **Initialize Repository**, porque es el punto de entrada necesario para comenzar a preparar archivos y crear commits.

## 6. Autenticación con GitHub mediante navegador

La autenticación debe realizarse usando GitHub CLI.

El add-on debe comprobar si `gh` está instalado ejecutando:

```bash
gh --version
```

Debe comprobar el estado de autenticación con:

```bash
gh auth status
```

Cuando el usuario presione:

```text
Connect to GitHub
```

el add-on debe ejecutar:

```bash
gh auth login --web
```

El proceso debe:

1. Abrir el navegador.
2. Permitir que el usuario inicie sesión en GitHub.
3. Autorizar GitHub CLI.
4. Volver a Blender.
5. Verificar automáticamente el estado de autenticación.
6. Mostrar el nombre del usuario conectado.

No se deben pedir ni guardar:

* Contraseñas.
* Tokens de acceso personal.
* Claves privadas.
* Credenciales en texto plano.

Debe existir también una opción:

```text
Disconnect GitHub
```

que utilice:

```bash
gh auth logout
```

Antes de cerrar la sesión debe mostrarse una confirmación visual.

## 7. Detección de dependencias

Al iniciar el add-on debe comprobar:

```bash
git --version
git lfs version
gh --version
```

Debe mostrar una sección de estado:

```text
Git: Installed
Git LFS: Installed
GitHub CLI: Installed
```

Si falta alguna dependencia debe indicar:

* Qué programa falta.
* Para qué se necesita.
* Cómo instalarlo.
* Botón para abrir la página oficial de instalación.

El add-on no debe fallar completamente si falta GitHub CLI. Las funciones locales de Git deben seguir disponibles cuando Git y Git LFS estén instalados.

## 8. Inicialización, apertura y clonación de repositorios

La inicialización de un repositorio es una funcionalidad primordial del add-on y debe formar parte del flujo principal del MVP. El usuario debe poder convertir la carpeta de su proyecto Blender en un repositorio Git completamente funcional sin abrir una terminal.

Antes de mostrar las acciones de control de versiones, el add-on debe detectar si el archivo `.blend` actual ya se encuentra dentro de un repositorio mediante:

```bash
git rev-parse --show-toplevel
```

También puede comprobar directamente la existencia de una carpeta `.git`, pero `git rev-parse` debe considerarse la fuente principal para detectar la raíz real del repositorio.

La ventana principal debe presentar tres acciones cuando no se detecte un repositorio:

```text
Initialize Repository
Open Existing Repository
Clone Repository
```

### 8.1 Inicializar un repositorio local

Debe existir un botón principal:

```text
Initialize Repository
```

Este botón debe abrir un asistente visual, no ejecutar inmediatamente `git init` sin mostrar opciones.

El asistente debe incluir como mínimo:

```text
Repository folder:
[Folder selector]

Repository name:
[Project name]

Initial branch:
[main]

Git author name:
[Current Git user or editable value]

Git author email:
[Current Git email or editable value]

Save current .blend inside repository:
[Enabled / Disabled]

Create Blender .gitignore:
[Enabled / Disabled]

Enable Git LFS:
[Enabled / Disabled]

Track .blend files with Git LFS:
[Enabled / Disabled]

Create initial commit:
[Enabled / Disabled]

Initial commit message:
[Initial commit]

Connect to GitHub after initialization:
[Enabled / Disabled]
```

#### Selección de la carpeta

Por defecto, si el archivo actual ya fue guardado, debe proponerse como raíz del repositorio:

```python
Path(bpy.data.filepath).parent
```

Si el archivo `.blend` todavía no ha sido guardado, el add-on debe solicitar una carpeta y ofrecer guardar el archivo dentro de ella antes de continuar.

El usuario también debe poder seleccionar una carpeta diferente mediante el selector de archivos de Blender.

El add-on debe validar:

* Que la ruta exista o pueda crearse.
* Que el usuario tenga permisos de escritura.
* Que no se esté intentando inicializar accidentalmente dentro de otro repositorio.
* Que no exista ya una carpeta `.git` sin que el usuario lo sepa.
* Que la carpeta seleccionada no sea una ruta temporal de recuperación de Blender.
* Que el nombre de la rama sea válido.
* Que el nombre y correo del autor estén configurados antes del primer commit.

Si ya existe un repositorio, debe mostrarse:

```text
A Git repository already exists in this folder.

[Open Repository]
[Refresh Status]
[Cancel]
```

No se debe volver a inicializar silenciosamente.

#### Comando de inicialización

La opción preferida debe ser:

```bash
git init -b main
```

donde `main` corresponde al nombre de rama elegido por el usuario.

Para versiones antiguas de Git que no soporten `-b`, debe existir un fallback:

```bash
git init
git branch -M main
```

El resultado debe verificarse antes de continuar con los siguientes pasos.

#### Configuración de identidad Git

El asistente debe leer primero:

```bash
git config user.name
git config user.email
git config --global user.name
git config --global user.email
```

Si no hay una identidad local válida, debe permitir configurarla visualmente.

Para el repositorio actual:

```bash
git config user.name "Nombre"
git config user.email "correo@example.com"
```

La configuración global solo debe modificarse cuando el usuario seleccione explícitamente:

```text
Apply identity globally
```

#### Creación de `.gitignore`

El asistente debe poder generar automáticamente un `.gitignore` recomendado para Blender.

Contenido base sugerido:

```gitignore
# Blender automatic backups
*.blend1
*.blend2
*.blend3
*.blend@

# Blender temporary files
*.blend.tmp
*.tmp
*.temp

# Python cache
__pycache__/
*.pyc

# Operating system
.DS_Store
Thumbs.db

# Secrets and credentials
.env
*.pem
*.key
credentials.json
```

El usuario debe poder:

* Previsualizar el contenido.
* Activar o desactivar reglas.
* Agregar patrones personalizados.
* Elegir si los archivos `.blend1`, `.blend2` y `.blend3` se ignoran o se gestionan mediante Git LFS.
* Evitar sobrescribir un `.gitignore` existente sin confirmación.

#### Configuración inicial de Git LFS

Cuando Git LFS esté activado, la inicialización local del repositorio debe ejecutar:

```bash
git lfs install --local
```

Después debe aplicar los patrones seleccionados, por ejemplo:

```bash
git lfs track "*.blend"
git lfs track "*.fbx"
git lfs track "*.glb"
git lfs track "*.psd"
```

Debe verificarse que `.gitattributes` haya sido creado o actualizado.

El asistente debe mostrar claramente qué archivos serán manejados por Git LFS antes de preparar el primer commit.

#### Guardar el archivo Blender

Si la opción está habilitada, el add-on debe guardar el archivo antes del primer commit:

```python
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
```

Cuando el archivo todavía no exista dentro de la carpeta del repositorio, debe permitir:

```text
Save a copy inside repository
Move project file into repository
Cancel
```

No se debe mover ni sobrescribir un archivo sin confirmación explícita.

#### Primer stage y primer commit

Después de inicializar el repositorio, el asistente debe mostrar los archivos detectados y permitir seleccionar cuáles formarán parte del primer commit.

Opciones:

```text
Stage Selected Files
Stage Recommended Project Files
Stage All
Skip Initial Commit
```

Comandos posibles:

```bash
git add archivo
git add .gitignore
git add .gitattributes
git add .
```

Antes del primer commit debe mostrarse un resumen:

```text
Repository folder: C:/Projects/TankAssets
Initial branch: main
Git LFS: Enabled
Tracked patterns: *.blend, *.fbx, *.glb
Files to commit: 8
Commit message: Initial commit
```

El primer commit debe ejecutarse visualmente mediante:

```bash
git commit -m "Initial commit"
```

El mensaje debe ser editable y no se debe crear un commit vacío accidentalmente. Si no hay archivos preparados, debe advertirse al usuario y ofrecer:

```text
Select Files
Create Repository Without Commit
Cancel
```

#### Conectar el repositorio local con GitHub

La inicialización local debe funcionar aunque el usuario no esté autenticado en GitHub.

Después de crear el repositorio local, el usuario debe poder elegir una de estas opciones:

```text
Keep Local Only
Connect Existing GitHub Repository
Create New GitHub Repository
```

Para conectar un repositorio remoto existente:

```bash
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

Para crear un repositorio nuevo con GitHub CLI y autenticación por navegador:

```bash
gh repo create REPOSITORY_NAME --source=. --remote=origin --push
```

El formulario de creación debe permitir:

```text
Repository name
Description
Visibility: Public / Private
Organization or personal account
Remote name: origin
Push initial branch after creation
```

Antes de usar `gh repo create`, debe verificarse:

```bash
gh auth status
```

Si el usuario todavía no está autenticado, debe mostrarse el botón:

```text
Connect to GitHub in Browser
```

que ejecutará:

```bash
gh auth login --web
```

El repositorio local debe permanecer funcional incluso si la autenticación o la creación remota fallan.

#### Flujo completo de inicialización

El asistente debe seguir este orden:

```text
1. Select repository folder
2. Validate folder
3. Configure repository name and initial branch
4. Configure Git author
5. Run git init
6. Create or update .gitignore
7. Initialize Git LFS locally
8. Configure selected LFS patterns
9. Save the current .blend file
10. Detect project files
11. Select and stage files
12. Create the initial commit
13. Optionally connect or create a GitHub repository
14. Optionally push the initial branch
15. Refresh repository status and open Git Manager
```

Cada paso debe mostrar su estado:

```text
Pending
Running
Completed
Failed
Skipped
```

Si un paso falla, el asistente debe detener las acciones dependientes, conservar el repositorio local ya creado cuando sea seguro y ofrecer:

```text
Retry Step
Open Git Output
Continue Without GitHub
Cancel
```

#### Resultado visual al finalizar

Al completar la inicialización, el add-on debe mostrar:

```text
Repository initialized successfully

Repository: TankAssets
Path: C:/Projects/TankAssets
Branch: main
Initial commit: 4d12ab3
Git LFS: Active
Remote: origin
GitHub: Connected

[Open Git Manager]
[Open Repository Folder]
[Open on GitHub]
```

### 8.2 Abrir un repositorio existente

Debe existir una opción:

```text
Open Existing Repository
```

El usuario debe seleccionar cualquier carpeta dentro del repositorio. El add-on debe localizar la raíz mediante:

```bash
git rev-parse --show-toplevel
```

Debe validar el repositorio y mostrar:

* Ruta raíz.
* Rama actual.
* Remotos.
* Estado.
* Último commit.
* Configuración de Git LFS.
* Si el archivo `.blend` actual pertenece o no al repositorio.

Abrir un repositorio desde el add-on no significa cambiar silenciosamente el archivo `.blend`. La asociación entre el repositorio seleccionado y la sesión de Blender debe ser visible y editable.

### 8.3 Clonar un repositorio

Debe existir un formulario:

```text
Repository URL or owner/repository:
Destination Folder:
Open project after clone:
[Enabled / Disabled]

[Clone]
```

Debe soportar:

* URL HTTPS.
* URL SSH.
* Formato `owner/repository` cuando GitHub CLI esté disponible.
* Repositorios públicos.
* Repositorios privados cuando exista autenticación válida.

Comandos:

```bash
git clone URL DESTINATION
```

o:

```bash
gh repo clone owner/repository DESTINATION
```

Después de clonar debe ejecutar o verificar:

```bash
git lfs install --local
git lfs pull
```

solo cuando el repositorio use Git LFS.

La clonación y la descarga de objetos LFS deben ejecutarse como tareas controladas para evitar bloquear la interfaz de Blender.

Al finalizar, debe mostrar los archivos `.blend` encontrados y permitir que el usuario elija cuál abrir.

### 8.4 Operadores mínimos requeridos

La implementación debe incluir, como mínimo, operadores equivalentes a:

```text
git_manager.initialize_repository
git_manager.open_repository
git_manager.clone_repository
git_manager.create_initial_commit
git_manager.connect_remote
git_manager.create_github_repository
```

La lógica de negocio no debe estar incrustada completamente dentro de los operadores. Debe delegarse a servicios reutilizables como:

```text
RepositoryService
GitService
LFSService
GitHubService
```
## 9. Git LFS

Git LFS debe ser una función central del add-on.

El add-on debe comprobar si Git LFS está activo:

```bash
git lfs version
git lfs env
```

Debe permitir inicializarlo mediante:

```bash
git lfs install
```

Debe incluir una interfaz para seleccionar qué extensiones serán gestionadas mediante LFS.

Configuración inicial recomendada:

```text
*.blend
*.blend1
*.blend2
*.fbx
*.obj
*.gltf
*.glb
*.abc
*.usd
*.usdc
*.usdz
*.exr
*.hdr
*.psd
*.tif
*.tiff
*.png
*.jpg
*.jpeg
*.wav
*.mp3
*.mp4
*.mov
```

No todas deben activarse obligatoriamente. El usuario debe poder seleccionar cuáles quiere rastrear.

Debe permitir agregar patrones personalizados:

```text
*.sbsar
*.kra
*.customformat
```

La interfaz debe ejecutar:

```bash
git lfs track "*.blend"
```

También debe poder ejecutar:

```bash
git lfs untrack "*.blend"
```

Debe mostrar el contenido de `.gitattributes`.

Debe recordar al usuario que `.gitattributes` debe incluirse en el commit.

Debe mostrar qué archivos están actualmente administrados por Git LFS:

```bash
git lfs ls-files
```

Debe mostrar:

* Nombre del archivo.
* Tamaño.
* Patrón LFS.
* Estado.
* Si está pendiente de subir.

## 10. Estado del repositorio

Debe existir una sección equivalente a Source Control.

Debe ejecutar:

```bash
git status --short
```

La interfaz debe clasificar los archivos en:

```text
Staged Changes
Changes
Untracked Files
Conflicts
Ignored Files
```

Cada archivo debe mostrar:

* Nombre.
* Ruta relativa.
* Estado.
* Tamaño.
* Si utiliza Git LFS.
* Tipo de cambio.

Estados visuales:

```text
M = Modified
A = Added
D = Deleted
R = Renamed
?? = Untracked
UU = Conflict
```

Los archivos deben poder seleccionarse individualmente.

## 11. Git add visual

El usuario no debe escribir:

```bash
git add .
```

Debe haber controles visuales.

Opciones:

```text
Stage Selected
Stage File
Stage All
Unstage Selected
Unstage File
Unstage All
Discard Changes
```

Comandos correspondientes:

```bash
git add archivo
git add .
git restore --staged archivo
git reset
git restore archivo
```

Antes de descartar cambios debe mostrarse una confirmación clara, porque es una acción destructiva.

Debe existir una casilla:

```text
Include current .blend file
```

También debe mostrarse si el archivo `.blend` actual tiene cambios sin guardar.

## 12. Creación intuitiva de commits

La creación de commits debe realizarse mediante una interfaz visual.

Debe incluir:

```text
Commit message:
[Campo de texto]

Extended description:
[Área de texto opcional]

Author:
Nombre <correo>

Staged files:
Lista de archivos

[Save Blender File Before Commit]
[Commit]
[Commit and Push]
```

El usuario nunca debe necesitar escribir manualmente:

```bash
git commit -m "mensaje"
```

El add-on debe ejecutar internamente:

```bash
git commit -m "mensaje"
```

Para una descripción extendida puede utilizar:

```bash
git commit -m "Título" -m "Descripción"
```

Validaciones:

* No permitir un commit sin mensaje.
* Advertir si no existen archivos preparados.
* Advertir si el archivo `.blend` tiene cambios sin guardar.
* Mostrar errores de Git de forma clara.
* Detectar cuando no hay nada para confirmar.
* Mostrar confirmación al completar el commit.

Antes del commit debe poder ejecutarse:

```python
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
```

Debe existir una preferencia para activar o desactivar el guardado automático.

## 13. Push, pull y fetch

Botones principales:

```text
Fetch
Pull
Push
Sync
```

Comandos:

```bash
git fetch
git pull
git push
```

La función `Sync` debe ejecutar una secuencia segura:

```text
Fetch
Pull
Push
```

Debe mostrar:

* Rama local.
* Rama remota.
* Commits por delante.
* Commits por detrás.
* Estado de sincronización.

Ejemplo:

```text
main
2 commits ahead
1 commit behind
```

Debe evitar realizar `push --force` desde la interfaz principal.

Una opción avanzada de force push solo puede estar disponible en configuraciones avanzadas, con advertencias y confirmación obligatoria.

## 14. Gestión de ramas

Debe existir una sección Branches.

Debe ejecutar:

```bash
git branch
git branch --all
git branch --show-current
```

Debe mostrar:

* Rama actual.
* Ramas locales.
* Ramas remotas.
* Último commit por rama.
* Autor.
* Fecha.
* Relación con la rama actual.

Acciones visuales:

```text
Create Branch
Switch Branch
Rename Branch
Delete Branch
Merge Branch
Publish Branch
Set Upstream
```

Comandos:

```bash
git switch nombre
git switch -c nombre
git branch -m nuevo_nombre
git branch -d nombre
git merge nombre
git push -u origin nombre
```

Antes de cambiar de rama se debe comprobar si existen cambios sin guardar.

Opciones cuando existan cambios:

```text
Commit Changes
Stash Changes
Discard Changes
Cancel
```

## 15. Visualización del historial

Debe existir una sección visual inspirada en Git Graph.

Debe utilizar comandos como:

```bash
git log --graph --decorate --oneline --all
```

Para obtener información estructurada debe preferirse un formato personalizado, por ejemplo:

```bash
git log --all --date=iso --pretty=format:"%H%x1f%P%x1f%an%x1f%ae%x1f%ad%x1f%D%x1f%s%x1e"
```

Cada commit debe mostrar:

* Hash corto.
* Hash completo.
* Mensaje.
* Autor.
* Correo del autor.
* Fecha.
* Rama.
* Tags.
* Commits padres.
* Si es un merge commit.
* Indicadores de rama local y remota.

La interfaz debe representar visualmente las conexiones entre commits y ramas.

Ejemplo conceptual:

```text
● 4d12ab3 main origin/main Fix tank track animation
│
● a3f7c82 Add Git LFS configuration
│
├─● e1bd422 feature/materials Add metal materials
│/
● 82ac911 Initial commit
```

La visualización debe incluir:

* Líneas de colores por rama.
* Nodos para cada commit.
* Indicadores de merge.
* Scroll vertical.
* Filtro por rama.
* Búsqueda por mensaje, autor o hash.
* Botón para actualizar.
* Posibilidad de seleccionar un commit.

Al seleccionar un commit debe abrirse un panel de detalles.

## 16. Detalles de un commit

Al seleccionar un commit se debe mostrar:

* Hash.
* Mensaje.
* Descripción.
* Autor.
* Correo.
* Fecha.
* Padres.
* Ramas asociadas.
* Tags.
* Lista de archivos modificados.
* Tipo de cambio.
* Estadísticas de líneas cuando sean archivos de texto.

Comandos posibles:

```bash
git show --stat HASH
git show --name-status HASH
```

Para archivos binarios como `.blend`, debe indicarse:

```text
Binary file changed
```

No se debe intentar mostrar diferencias internas de geometría dentro de un `.blend`.

Acciones:

```text
Copy Commit Hash
Checkout Commit
Create Branch from Commit
Create Tag
Revert Commit
Open Commit on GitHub
```

Acciones destructivas o que cambien el estado deben requerir confirmación.

## 17. Autor y configuración de Git

Debe mostrar la identidad Git actual:

```bash
git config user.name
git config user.email
```

Debe permitir configurar:

```text
User name
User email
```

Opciones:

```text
Apply to Current Repository
Apply Globally
```

Comandos:

```bash
git config user.name "Name"
git config user.email "email@example.com"

git config --global user.name "Name"
git config --global user.email "email@example.com"
```

Debe mostrar claramente si la configuración es local o global.

## 18. Repositorios remotos

Debe mostrar:

```bash
git remote -v
```

La interfaz debe permitir:

```text
Add Remote
Edit Remote
Remove Remote
Set Default Remote
Open Remote in Browser
```

Comandos:

```bash
git remote add origin URL
git remote set-url origin URL
git remote remove origin
```

Debe detectar si el remoto es de GitHub.

Cuando sea GitHub, debe permitir abrir:

```text
Repository
Issues
Pull Requests
Actions
Commit
Branch
```

en el navegador.

## 19. Creación de repositorios en GitHub

Cuando el usuario esté autenticado mediante GitHub CLI, el add-on debe permitir crear un repositorio remoto.

Formulario:

```text
Repository Name
Description
Visibility: Public / Private
Initialize with README
Add .gitignore
Add license
Create and Push
```

Debe utilizar GitHub CLI, por ejemplo:

```bash
gh repo create
```

Debe permitir conectar el repositorio local y subir el primer commit.

No se deben incluir credenciales en la URL remota.

## 20. Stash

Debe existir una sección para Git Stash.

Acciones:

```text
Create Stash
Create Stash with Message
Include Untracked Files
List Stashes
Apply Stash
Pop Stash
Drop Stash
Clear Stashes
```

Comandos:

```bash
git stash push -m "mensaje"
git stash push -u -m "mensaje"
git stash list
git stash apply
git stash pop
git stash drop
```

Las acciones `drop` y `clear` deben requerir confirmación.

## 21. Tags

Debe permitir:

```text
Create Tag
Create Annotated Tag
Delete Tag
Push Tag
Push All Tags
```

Debe mostrar:

* Nombre.
* Commit.
* Mensaje.
* Fecha.
* Autor.

Comandos:

```bash
git tag
git tag nombre
git tag -a nombre -m "mensaje"
git push origin nombre
git push origin --tags
```

## 22. Conflictos

El add-on debe detectar archivos en conflicto.

Debe mostrar una sección especial:

```text
Merge Conflicts
```

Para archivos de texto puede permitir:

```text
Use Ours
Use Theirs
Mark as Resolved
Open Externally
```

Para archivos `.blend` debe advertir:

```text
Los archivos .blend son binarios y no pueden fusionarse automáticamente.
Debes elegir una versión o recuperar manualmente el contenido.
```

Opciones:

```text
Keep Local Version
Keep Remote Version
Create Backup of Both
Cancel Merge
```

Antes de sobrescribir un `.blend`, debe crear una copia de seguridad.

## 23. Archivos `.blend` y seguridad

El add-on debe detectar el archivo abierto mediante:

```python
bpy.data.filepath
```

Si el archivo no ha sido guardado, debe mostrar:

```text
Save the Blender file before using version control.
```

Antes de operaciones importantes debe permitir crear copias de seguridad:

```text
project_backup_YYYYMMDD_HHMMSS.blend
```

Las siguientes operaciones deben ofrecer respaldo:

* Cambio de rama.
* Checkout de commit.
* Pull con cambios.
* Resolución de conflictos.
* Revert.
* Reset.
* Restauración de archivos.

## 24. Operaciones que no deben bloquear Blender

Las operaciones que pueden tardar deben ejecutarse en procesos o tareas controladas:

* Clone.
* Pull.
* Push.
* Fetch.
* Git LFS upload.
* Git LFS download.
* Checkout de archivos grandes.

La interfaz debe mostrar:

```text
Running...
Progress
Cancel
Output
```

No se debe modificar directamente la API de Blender desde hilos secundarios.

Los resultados deben enviarse al hilo principal usando mecanismos seguros como temporizadores de Blender:

```python
bpy.app.timers
```

## 25. Consola interna y registro

Debe existir un panel llamado:

```text
Git Output
```

Debe mostrar las operaciones ejecutadas y sus resultados.

Ejemplo:

```text
[10:31:02] git status --short
[10:31:03] Completed successfully

[10:32:15] git push origin main
[10:32:21] Push completed
```

No se deben mostrar credenciales, tokens ni información sensible.

En modo normal puede mostrarse una descripción amigable:

```text
Creating commit...
Uploading large files with Git LFS...
Push completed successfully.
```

En modo desarrollador se pueden mostrar los argumentos completos, siempre ocultando información sensible.

## 26. Manejo de errores

Los errores no deben mostrarse únicamente en la consola de Python.

Deben transformarse en mensajes entendibles.

Ejemplos:

```text
Git is not installed.
Git LFS is not installed.
GitHub authentication is required.
No remote repository has been configured.
There are no staged files.
The branch has no upstream.
Push was rejected because the remote contains newer commits.
A merge conflict was detected.
The current Blender file has not been saved.
```

Cada error debe incluir, cuando sea posible:

* Qué ocurrió.
* Por qué ocurrió.
* Cómo solucionarlo.
* Botón de acción directa.

## 27. Seguridad

Requisitos obligatorios:

* Utilizar `subprocess.run()` o `subprocess.Popen()`.
* Pasar comandos como listas.
* Utilizar `shell=False`.
* Validar nombres de ramas, tags y rutas.
* No concatenar comandos.
* No ejecutar texto arbitrario introducido por el usuario.
* No guardar tokens en archivos del add-on.
* No guardar credenciales en `.blend`.
* No mostrar tokens en logs.
* No subir automáticamente archivos secretos.
* Advertir sobre archivos como `.env`, claves privadas y credenciales.
* Incluir `.gitignore` recomendado.

Ejemplo de `.gitignore`:

```gitignore
# Blender backups
*.blend1
*.blend2
*.blend3

# Temporary files
*.tmp
*.temp
__pycache__/
*.pyc

# Operating system
.DS_Store
Thumbs.db

# Secrets
.env
*.pem
*.key
credentials.json
```

Debe permitir que el usuario decida si quiere incluir los archivos de respaldo `.blend1` y `.blend2` en Git LFS o ignorarlos.

## 28. Arquitectura del código

Utilizar una arquitectura modular:

```text
blender_git_manager/
├── __init__.py
├── blender_manifest.toml
├── preferences.py
├── properties.py
├── constants.py
│
├── operators/
│   ├── authentication.py
│   ├── repository.py
│   ├── staging.py
│   ├── commits.py
│   ├── branches.py
│   ├── remotes.py
│   ├── synchronization.py
│   ├── history.py
│   ├── lfs.py
│   ├── stash.py
│   ├── tags.py
│   └── conflicts.py
│
├── services/
│   ├── process_service.py
│   ├── git_service.py
│   ├── github_service.py
│   ├── lfs_service.py
│   ├── repository_service.py
│   ├── history_parser.py
│   ├── credential_service.py
│   └── background_task_service.py
│
├── ui/
│   ├── top_menu.py
│   ├── main_panel.py
│   ├── repository_panel.py
│   ├── changes_panel.py
│   ├── commit_panel.py
│   ├── graph_panel.py
│   ├── branches_panel.py
│   ├── lfs_panel.py
│   ├── output_panel.py
│   └── dialogs.py
│
├── models/
│   ├── repository.py
│   ├── commit.py
│   ├── branch.py
│   ├── file_change.py
│   └── task.py
│
└── utils/
    ├── paths.py
    ├── validation.py
    ├── formatting.py
    └── backups.py
```

## 29. Servicio central para comandos

Crear un servicio central seguro.

Ejemplo conceptual:

```python
from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass
class CommandResult:
    return_code: int
    stdout: str
    stderr: str

    @property
    def successful(self) -> bool:
        return self.return_code == 0


class ProcessService:

    @staticmethod
    def run(
        executable: str,
        arguments: list[str],
        working_directory: Path | None = None,
        timeout: int | None = None,
    ) -> CommandResult:

        result = subprocess.run(
            [executable, *arguments],
            cwd=str(working_directory) if working_directory else None,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=timeout,
        )

        return CommandResult(
            return_code=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )
```

Todos los comandos Git, Git LFS y GitHub CLI deben pasar por este servicio.

## 30. Preferencias del add-on

Crear una sección de preferencias con:

```text
Git executable path
Git LFS executable path
GitHub CLI executable path

Save .blend before commit
Create backup before checkout
Refresh repository automatically
Refresh interval
Default remote
Default branch name
Enable advanced Git operations
Show developer output
```

Las rutas deben detectarse automáticamente mediante mecanismos como:

```python
shutil.which("git")
shutil.which("gh")
```

## 31. Diseño visual

La interfaz debe tener un diseño similar a un cliente Git moderno.

Distribución sugerida:

```text
┌──────────────────────────────────────────────────────────────────┐
│ Repository: TankAssets        Branch: main        Sync: Up to date│
├────────────────┬─────────────────────────────────────────────────┤
│ Changes        │ Commit Graph                                    │
│                │                                                 │
│ Staged         │ ● main Fix track animation                      │
│  tank.blend    │ │                                               │
│                │ ● Configure Git LFS                              │
│ Modified       │ │                                               │
│  texture.png   │ ├─● feature/materials Add materials             │
│                │ │/                                              │
│ Untracked      │ ● Initial commit                                │
│  notes.txt     │                                                 │
├────────────────┴─────────────────────────────────────────────────┤
│ Commit message                                                   │
│ [Fix tank track animation                                     ] │
│                                                                  │
│ [Commit] [Commit and Push] [Pull] [Push]                         │
└──────────────────────────────────────────────────────────────────┘
```

Prioridades del diseño:

* Interfaz intuitiva.
* Acciones visibles.
* Estados claramente diferenciados.
* Confirmaciones para acciones peligrosas.
* Información técnica disponible sin sobrecargar al usuario.
* Uso de iconos propios de Blender cuando sea posible.
* Tooltips descriptivos.
* Compatibilidad con tema claro y oscuro.

## 32. Limitaciones conocidas

Debe informarse claramente:

* Git LFS almacena archivos grandes, pero no permite fusionar internamente dos archivos `.blend`.
* Git no puede mostrar diferencias visuales de geometría, materiales o animaciones dentro de un `.blend`.
* Dos usuarios modificando el mismo archivo `.blend` pueden producir conflictos.
* Es recomendable dividir proyectos grandes en varios archivos enlazados.
* Git LFS puede tener cuotas según el proveedor remoto.
* La autenticación depende de GitHub CLI, Git Credential Manager o SSH configurados en el sistema.

## 33. Desarrollo por fases

### Fase 1: MVP

Implementar:

* Detección de Git, Git LFS y GitHub CLI.
* Autenticación GitHub mediante navegador.
* Detección del repositorio actual.
* Asistente visual completo para inicializar un repositorio local, elegir la carpeta raíz, crear la rama inicial, configurar identidad Git, generar `.gitignore`, activar Git LFS, preparar archivos y crear el primer commit.
* Clonar repositorio.
* Mostrar rama activa.
* Mostrar `git status`.
* Stage individual.
* Stage all.
* Unstage.
* Campo visual para mensaje.
* Commit.
* Commit and Push.
* Pull.
* Push.
* Fetch.
* Configuración básica de Git LFS.
* Menú Git en la barra superior.
* Panel de salida.

### Fase 2

Implementar:

* Lista de ramas.
* Crear y cambiar ramas.
* Remotos.
* Stash.
* Tags.
* Historial de commits.
* Detalles de commit.
* Indicadores ahead y behind.
* Creación de repositorios en GitHub.

### Fase 3

Implementar:

* Gráfico visual de commits.
* Líneas de ramas.
* Merge.
* Revert.
* Resolución guiada de conflictos.
* Operaciones en segundo plano.
* Barra de progreso.
* Búsquedas y filtros.

### Fase 4

Implementar:

* Compatibilidad completa con Linux y macOS.
* Soporte para GitLab y Bitbucket.
* Bloqueo de archivos grandes.
* Comparación de metadatos de escenas Blender.
* Integración con equipos.
* Pull requests.
* Issues.
* Releases.

## 34. Criterios de aceptación del MVP

El MVP se considera funcional cuando un usuario puede:

1. Abrir Blender.
2. Acceder al menú superior Git.
3. Inicializar un repositorio local desde una carpeta seleccionada o desde la carpeta del archivo `.blend`.
4. Elegir la rama inicial, configurar la identidad Git y generar un `.gitignore`.
5. Activar Git LFS para archivos `.blend` durante la inicialización.
6. Seleccionar archivos y crear el primer commit desde el asistente.
7. Autenticarse en GitHub mediante el navegador cuando decida conectar el repositorio remoto.
8. Ver los archivos modificados.
9. Seleccionar archivos.
10. Prepararlos para commit.
11. Escribir el mensaje en un campo visual.
12. Crear el commit con un botón.
13. Ver la rama activa.
14. Ejecutar pull y push desde botones.
15. Consultar el historial básico de commits.
16. Ver autor, fecha, hash y mensaje de cada commit.
17. Recibir mensajes claros cuando una operación falla.
18. Completar todo el flujo sin abrir una terminal.


## 35. Resultado esperado

Genera el proyecto completo del add-on con:

* Código modular.
* Tipado cuando sea posible.
* Manejo de errores.
* Registro y desregistro correcto de clases de Blender.
* Menú Git en la barra superior.
* Panel principal funcional.
* Asistente visual funcional para inicializar repositorios y crear el primer commit.
* Operadores para inicializar, abrir y clonar repositorios.
* Servicios seguros para ejecutar comandos.
* Integración con Git LFS.
* Integración con GitHub CLI.
* Autenticación mediante navegador.
* Interfaz visual de staging y commits.
* Historial de commits.
* Gestión inicial de ramas.
* Archivo `blender_manifest.toml`.
* Archivo `README.md`.
* Archivo `LICENSE`.
* Archivo `.gitignore`.
* Instrucciones de instalación.
* Instrucciones para desarrollo y depuración.
* Pruebas unitarias para las funciones que no dependan directamente de la interfaz de Blender.

No generes únicamente ejemplos aislados. Construye una base de proyecto real, extensible y organizada.

Empieza desarrollando el MVP. Explica cada archivo creado, presenta la estructura del proyecto y entrega el contenido completo de cada archivo necesario para ejecutar la primera versión en Blender.
