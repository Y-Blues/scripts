# ycappuccino-scripts

Cas d'usage : un opérateur dépose un script Python et l'exécute à la demande, comme un service natif exposé indépendamment du transport (`IExposedService`, `endpoints_service`). Reprend le cas d'usage historique de `ScriptInterpreter.execute_script` : `POST /api/services/scripts/{scriptId}/execute` une fois `http_server` chargé.

Conception : [docs/superpowers/specs/2026-09-15-scripts-design.md](docs/superpowers/specs/2026-09-15-scripts-design.md).

Prérequis : lire les README de [core](../core/README.md), [storage](../storage/README.md) et [endpoints_service](../endpoints_service/README.md).

## Mise en place

```bash
uv add --editable ../scripts
```

`conf/application.yml` :

```yaml
bundle_prefix:
  - ycappuccino.storage
  - ycappuccino.endpoints_service
  - ycappuccino.scripts
  - myapp
layers:
  ycappuccino_storage_memory:
    active: true
```

Le service `ScriptService` (`name = "scripts"`, `secure = True`) est publié dès que `ycappuccino.scripts` est chargé.

## Déclarer un script

Un script est un item `@Item` ordinaire, persisté par `ycappuccino-storage` (`storage/README.md`) : `name` (libellé) et `source` (le code Python, en texte brut — pas un upload `multipart`, voir la conception).

```python
from ycappuccino.scripts.models.script import Script

script = Script()
script.id("greet")
script.name("Greet")
script.source("result = 'hello'\n")
await manager.up_sert_model(script)
```

## Exécuter un script

`ScriptService.execute(script_id, subject)` lit le script avec les droits du sujet et l'exécute ; un id inconnu lève `NotFound`. La méthode est marquée `@rpc_method(method="POST", path="/{script_id}/execute")`, ce qui reproduit la forme legacy `{scriptId}/execute` : `IServiceEndpoint` y route `POST` sur `[script_id, "execute"]`, toute autre combinaison lève `NotFound`.

```python
result = await script_service.execute("greet", subject)
print(result)  # {"result": "hello"}
```

Le script peut fixer une variable globale `result` ; sans elle, le résultat est `"script executed"` (comportement du legacy, conservé par défaut). Une fois `http_server` chargé, le même appel se fait par `POST /api/services/scripts/greet/execute`.

## Injecter des services : `# @Require`

Un script peut demander un service publié dans le framework en le déclarant sur une ou plusieurs lignes en tête du fichier, avant tout code Python :

```python
# @Require IActivityLogger logger
# @Require IManager manager
logger.info("script started")
result = "ok"
```

`ClassName` est le nom de la spécification du service (comme partout ailleurs dans le framework natif : le nom de la classe ou de l'interface), `varname` le nom sous lequel le service est injecté dans les globales du script, et un troisième mot optionnel un filtre LDAP (`(name=main)`). La résolution passe par `Framework.get_framework().context.get_service_reference/get_service`, exactement le mécanisme déjà utilisé ailleurs dans `core` — reprise et généralisation de la convention legacy (`//@Require`), qui ne lisait qu'une seule ligne.

## Sécurité

`ScriptService` est `secure = True` : `exec()` n'est **pas isolé** — un script a un accès complet à l'interpréteur Python. C'est un choix assumé : ce service n'a de sens que pour du code déposé par un opérateur de confiance, déjà authentifié et autorisé (`call:scripts`) par l'`IAuthorization` de l'application. Il ne doit jamais être exposé à une entrée non fiable. Voir la section « Risques » de la conception.

## Tester avec scripts

```python
import unittest

from ycappuccino.scripts.models.script import Script
from ycappuccino.scripts.service import ScriptService


class TestGreetScript(unittest.IsolatedAsyncioTestCase):
    async def test_script_sets_result(self):
        # manager déjà construit sur un backend mémoire
        script = Script()
        script.id("greet")
        script.source("result = 1 + 1\n")
        await manager.up_sert_model(script)

        service = ScriptService(manager)
        result = await service.execute("greet", None)

        self.assertEqual(result, {"result": 2})
```

## Développer scripts

```bash
uv sync
uv run python -m unittest discover -s src/unittest/python
```

L'exemple `example/` se lance avec `cd example && uv run --project .. ycappuccino`.
