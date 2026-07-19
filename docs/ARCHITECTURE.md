# Arquitectura técnica

## Principios

1. **La interfaz no ejecuta comandos directamente.** Los operadores llaman a servicios.
2. **Todo proceso externo pasa por `ProcessService`.** Se prohíbe `shell=True`.
3. **Los modelos de dominio no dependen de Blender.** Esto permite pruebas unitarias.
4. **Los hilos no modifican `bpy`.** Los operadores modales reciben el resultado y actualizan Blender en el hilo principal.
5. **El repositorio local es independiente de GitHub.** Un fallo remoto nunca invalida un repositorio local ya creado.
6. **No existe almacenamiento de credenciales.** La autenticación se delega en `gh` y gestores del sistema.

## Capas

### UI

`ui/dashboard.py` concentra el diseño para reutilizarlo tanto en el panel lateral como en la ventana emergente. Las `UIList` no consultan Git; solo dibujan colecciones RNA.

### Operadores

Los operadores validan contexto Blender, guardan el archivo cuando corresponde y delegan la operación. Las tareas de red usan `AsyncModalMixin`.

### Sincronización de estado

`state_sync.py` convierte un `RepositorySnapshot` en propiedades Blender. También es el único lugar que rellena las colecciones de cambios, commits y ramas.

### Servicios

- `GitService`: comandos atómicos y parsing.
- `LFSService`: comandos `git lfs`.
- `GitHubService`: comandos `gh`.
- `RepositoryService`: flujos compuestos como init y clone.
- `ProcessService`: subprocess seguro.

### Modelos

Los dataclasses describen resultados de comandos, archivos modificados, commits, ramas, remotos, estado de sincronización y progreso del asistente.

## Flujo de inicialización

```text
Blender Operator
  ├─ guarda .blend en hilo principal
  ├─ construye InitConfig
  └─ inicia tarea modal
       └─ RepositoryService.initialize_repository
            ├─ valida carpeta e identidad
            ├─ git init
            ├─ git config
            ├─ .gitignore
            ├─ git lfs install --local
            ├─ git lfs track
            ├─ stage
            ├─ commit inicial
            └─ gh repo create opcional
```

Cada etapa genera un `InitStep` con estado `running`, `completed`, `failed` o `skipped`. La interfaz registra el resultado de todos los pasos.

## Evolución del gráfico Git

La fase siguiente debe separar:

1. Consulta estructurada con `git log`.
2. Asignación de carriles mediante un algoritmo de columnas activas por hash padre.
3. Modelo visual `GraphLane`, `GraphNode` y `GraphEdge`.
4. Render mediante `gpu`/`blf` en un editor o región dedicada.
5. Selección de commits conectada con el panel de detalles.

No debe analizarse el texto de `git log --graph`; el grafo debe construirse desde hashes y padres.
