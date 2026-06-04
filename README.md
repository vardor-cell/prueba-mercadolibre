# prueba-mercadolibre

[![Powered by Kedro](https://img.shields.io/badge/powered_by-kedro-ffc900?logo=kedro)](https://kedro.org)

## Overview

This is your new Kedro project with PySpark setup, which was generated using `kedro 1.4.0`.

Take a look at the [Kedro documentation](https://docs.kedro.org) to get started.

## Rules and guidelines

In order to get the best out of the template:

* Don't remove any lines from the `.gitignore` file we provide
* Make sure your results can be reproduced by following a [data engineering convention](https://docs.kedro.org/en/stable/faq/faq.html#what-is-data-engineering-convention)
* Don't commit data to your repository
* Don't commit any credentials or your local configuration to your repository. Keep all your credentials and local configuration in `conf/local/`

## How to install dependencies

Declare any dependencies in `requirements.txt` for `pip` installation.

To install them, run:

```
pip install -r requirements.txt
```

## Datos en BigQuery (free tier — Sandbox)

Todo el flujo de datos reside en BigQuery (dataset `risk_profiling`). El pipeline lee los datos raw de BQ y escribe ahí intermedios, features y scores. El único artefacto local es el modelo (`data/06_models/anomaly_ensemble.pkl`).

### Setup inicial (una vez)

1. **Activar BigQuery Sandbox**: entrá a [BigQuery Console](https://console.cloud.google.com/bigquery) con tu cuenta Google (crea un proyecto automático, sin tarjeta). Anotá el **PROJECT_ID**.
2. **Service Account**: IAM → Service Accounts → crear `kedro-bq` con roles **BigQuery Data Editor** + **BigQuery Job User**. Generar una **llave JSON** y guardarla en `conf/local/gcp-key.json` (gitignored).
3. **Configurar el project**: editá `conf/base/globals.yml` y reemplazá `gcp.project` con tu PROJECT_ID.
4. **Instalar deps**: `pip install -r requirements.txt`

### Correr el pipeline

```bash
kedro run    # lee raw de BQ y escribe TODO el flujo a BQ (11 tablas)
```

> Los datos raw ya están cargados en el dataset `risk_profiling`. Si necesitás
> re-sembrar las tablas raw desde los CSV (p. ej. tras el expiry de 60 días),
> cargá `data/01_raw/*.csv` a BigQuery con la consola o el CLI `bq load`.

### Correr con Docker (conectado a BigQuery)

`docker-compose.yml` levanta el pipeline en un contenedor, montando las credenciales
(no quedan en la imagen).

**1) Construir la imagen** (una vez, y cada vez que cambie el código):

```bash
docker compose build
```

**2) Correr cualquier pipeline** sobreescribiendo el comando del contenedor:

```bash
docker compose run --rm kedro kedro run                    # proceso completo (sin ingesta)
docker compose run --rm kedro kedro run --pipeline=ingest  # solo ingesta (CSV local → BQ)
docker compose run --rm kedro kedro run --pipeline=full    # ingesta + proceso completo
docker compose run --rm kedro kedro run --tags=score       # solo scoring
docker compose run --rm kedro bash                         # shell interactiva
```

O directamente `docker compose up --build` para construir y correr el pipeline completo
en un solo paso.

> **Importante:** el Dockerfile copia `src/` al construir la imagen, así que tras
> cualquier cambio de código hay que volver a correr `docker compose build`
> (o usar `--build`). Si no, el contenedor corre con la versión anterior.

Requiere `conf/local/gcp-key.json` y `conf/local/credentials.yml` (gitignored), que se
montan como volumen de solo lectura. Los CSV locales de `data/01_raw/` (para la ingesta)
también se montan vía el volumen `data/`.

### Notas del Sandbox
- Límites free: 10 GB storage / 1 TB query por mes (nuestros datos son ~1.5 MB).
- **Las tablas expiran a los 60 días**. Re-correr el pipeline las refresca.
- Sin streaming ni Cloud Run → la orquestación se hace con GitHub Actions (cron).
- Para desarrollo offline sin BQ, descomentá los overrides CSV en `conf/local/catalog.yml`.

## How to run your Kedro pipeline

You can run your Kedro project with:

```
kedro run
```

## How to test your Kedro project

Have a look at the files `tests/test_run.py` and `tests/pipelines/data_science/test_pipeline.py` for instructions on how to write your tests. Run the tests as follows:

```
pytest
```

You can configure the coverage threshold in your project's `pyproject.toml` file under the `[tool.coverage.report]` section.

## Project dependencies

To see and update the dependency requirements for your project use `requirements.txt`. Install the project requirements with `pip install -r requirements.txt`.

[Further information about project dependencies](https://docs.kedro.org/en/stable/kedro_project_setup/dependencies.html#project-specific-dependencies)

## How to work with Kedro and notebooks

> Note: Using `kedro jupyter` or `kedro ipython` to run your notebook provides these variables in scope: `catalog`, `context`, `pipelines` and `session`.
>
> Jupyter, JupyterLab, and IPython are already included in the project requirements by default, so once you have run `pip install -r requirements.txt` you will not need to take any extra steps before you use them.

### Jupyter
To use Jupyter notebooks in your Kedro project, you need to install Jupyter:

```
pip install jupyter
```

After installing Jupyter, you can start a local notebook server:

```
kedro jupyter notebook
```

### JupyterLab
To use JupyterLab, you need to install it:

```
pip install jupyterlab
```

You can also start JupyterLab:

```
kedro jupyter lab
```

### IPython
And if you want to run an IPython session:

```
kedro ipython
```

### How to ignore notebook output cells in `git`
To automatically strip out all output cell contents before committing to `git`, you can use tools like [`nbstripout`](https://github.com/kynan/nbstripout). For example, you can add a hook in `.git/config` with `nbstripout --install`. This will run `nbstripout` before anything is committed to `git`.

> *Note:* Your output cells will be retained locally.

## Package your Kedro project

[Further information about building project documentation and packaging your project](https://docs.kedro.org/en/stable/tutorial/package_a_project.html)
