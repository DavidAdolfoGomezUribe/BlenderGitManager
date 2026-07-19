# Matriz de cobertura de requisitos

Leyenda: **Implementado**, **Parcial**, **Planificado**.

| Sección | Estado | Cobertura actual |
|---|---|---|
| 1. Objetivo general | Implementado | Git, GitHub CLI, LFS, commits, ramas, historial y UI sin terminal. |
| 3. Compatibilidad | Implementado inicial | Blender 4.2+, diseño portable; validación principal dirigida a Windows. |
| 4-5. Integración UI | Implementado | Menú superior, panel lateral, popup ancho, encabezado y onboarding. |
| 6. Autenticación | Implementado | `gh auth status/login --web/logout`; no almacena secretos. |
| 7. Dependencias | Implementado | Estado de Git, LFS y GH; configuración manual de rutas. |
| 8. Init/Open/Clone | Implementado MVP | Wizard, identidad, `.gitignore`, LFS, stage mode, primer commit, GitHub opcional y clone. |
| 9. Git LFS | Implementado básico | Install local, track/untrack, ls-files y recordatorio de `.gitattributes`. |
| 10. Estado | Implementado básico | Porcelain XY, tamaño, staged, untracked, conflictos y marca LFS. |
| 11. Git add visual | Implementado | Stage/unstage por archivo, selección y global; discard confirmado. |
| 12. Commits | Implementado | Título, descripción, save before commit, commit y commit+push. |
| 13. Push/Pull/Fetch | Implementado | Tareas modales, sync y ahead/behind. Pull usa `--ff-only`. |
| 14. Ramas | Implementado básico | Lista, crear y cambiar con bloqueo por archivo sucio y backup. |
| 15. Historial | Parcial | Datos estructurados y selección; faltan carriles de colores. |
| 16. Detalle commit | Parcial | Metadatos principales; faltan archivos y acciones avanzadas. |
| 17. Autor Git | Implementado en init | Configuración local/global durante inicialización; falta panel independiente. |
| 18. Remotos | Parcial | Add/set URL y apertura GitHub; falta CRUD completo visual. |
| 19. Crear GitHub repo | Implementado básico | Nombre, owner, visibilidad, descripción, remote y push. |
| 20. Stash | Planificado | Fase 2. |
| 21. Tags | Parcial interno | Servicio crea tags; falta interfaz completa. |
| 22. Conflictos | Parcial | Detección y señalización; falta resolución guiada binaria/texto. |
| 23. Seguridad `.blend` | Parcial | Guardado y backup al cambiar rama; faltan backups en todas las operaciones destructivas futuras. |
| 24. No bloquear Blender | Implementado principal | Init, clone, auth, commit/push y sync usan Future + timer modal. Cancelación dura pendiente. |
| 25. Git Output | Implementado | Log con niveles y límite de líneas. |
| 26. Errores | Implementado básico | Mensajes UI y salida; catálogo especializado ampliable. |
| 27. Seguridad | Implementado | Argument lists, `shell=False`, validación, redacción y política de credenciales. |
| 28-29. Arquitectura | Implementado | Capas UI/operadores/servicios/modelos/utils y ProcessService central. |
| 30. Preferencias | Implementado | Ejecutables, save, backup, refresh, remote, branch y modo avanzado. |
| 31. Diseño | Implementado básico | Dashboard, listas, acciones visibles y compatibilidad con tema Blender. |
| 32. Limitaciones | Implementado en docs | Binarios, merges, cuotas y división de proyectos. |
| 33. Fases | Implementado en roadmap | Fases 2-4 detalladas. |
| 34. Criterios MVP | Mayormente implementado | Flujo completo sin terminal; selección individual del primer commit se realiza después del wizard. |
| 35. Entregables | Implementado | Código, manifest, README, LICENSE, gitignore, docs y pruebas. |
