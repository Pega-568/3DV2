# HY3D API Server

Guia operativa corta para el backend remoto HY3D.

## Instalar dependencias

```powershell
python -m pip install -r requirements-server.txt
```

## Configurar entorno

Copiar `.env.server.example` como referencia y definir variables en la terminal o en el entorno del proceso:

```powershell
$env:HY3D_SERVER_WORKSPACE_ROOT="server_workspace"
$env:HY3D_SERVER_EXPORTS_ROOT="server_exports"
$env:HY3D_ENGINE_ROOT="3D_ENGINES"
$env:HY3D_WRAPPER_RUN="tools\triposr\run_triposr_local.ps1"
$env:HY3D_JOB_TIMEOUT_SECONDS="900"
$env:HY3D_MAX_UPLOAD_MB="25"
```

No commitear `.env`, workspaces, exports, ZIPs ni modelos generados.

## Iniciar API

```powershell
uvicorn server.hy3d_api.main:app --host 0.0.0.0 --port 8000
```

## Smoke test

```powershell
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/jobs `
  -F "image=@hy3d_v2/test_assets/real_smoke_input.png"
```

Si `HY3D_ENGINE_ROOT` o `HY3D_WRAPPER_RUN` no estan configurados, `/api/jobs` crea el job y devuelve un error claro para el engine remoto.

## Ejecucion con Docker

Requisitos:

- Docker
- Docker Compose

Preparar:

```powershell
Copy-Item .env.docker.example .env
```

Construir:

```powershell
docker compose build
```

Levantar:

```powershell
docker compose up -d
```

Ver logs:

```powershell
docker compose logs -f hy3d-api
```

Probar health:

```powershell
curl http://127.0.0.1:8000/health
```

Modo fixture/dev:

```env
HY3D_SERVER_FIXTURE_RESULT_PACKAGE=hy3d_v2/test_assets/result_package_sample.zip
```

Con el fixture se puede probar `/api/jobs`, candidatos, reportes, accepted, STL y final package sin TripoSR real.

Para usar desde Blender en otra maquina, configurar:

```text
Execution Mode = Remote
Server URL = http://<IP_SERVIDOR>:8000
```

TripoSR real queda preparado para una fase posterior. La opcion recomendada sera montar un motor externo:

```yaml
volumes:
  - /opt/triposr-local:/opt/triposr-local:ro
```

Y definir:

```env
HY3D_ENGINE_ROOT=/opt/triposr-local
HY3D_WRAPPER_RUN=/app/tools/triposr/run_triposr_local.ps1
```

No descargar pesos grandes ni incluir TripoSR completo en GitHub.
