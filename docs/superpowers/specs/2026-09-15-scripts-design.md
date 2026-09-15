# scripts natif : design

Date : 2026-09-15. Sous-projet de la reprise des dépôts YCappuccino, après `core`, `api`, `storage`, `endpoints_storage`, `http_server`, `endpoints_service` (`permissions_app` et `scheduler` en cours, en parallèle, non touchés ici).

## Objectif

`scripts` permet à un opérateur de déposer un script et de l'exécuter à la demande, comme une action `IExposedService` (`endpoints_service`), indépendamment du transport. C'est exactement le cas d'usage historique de `ScriptInterpreter.execute_script` : `POST /api/services/scripts/{scriptId}/execute` une fois `http_server` chargé.

## Décisions

| Sujet | Décision |
|---|---|
| Style | Composant natif, aucun décorateur ; modèle `@Item` inchangé dans son principe |
| Langage du script | **Python**, exécuté par `exec()`. `dukpy` (moteur JS) est une dépendance legacy retirée, non reconduite |
| Stockage du script | `Script.source` : `@Property` texte brut, pas un upload `multipart` — un script est du texte court, la complexité de `IFileStore` (upload, suppression de fichier associée) n'apporte rien ici |
| Convention d'injection | Conservée et généralisée : `# @Require ClassName varname [filtre_ldap]`, une ou plusieurs lignes en tête du script (le legacy n'en lisait qu'une seule) ; résolution par `Framework.get_framework().context.get_service_reference/get_service`, exactement le mécanisme déjà utilisé par le legacy (`self._context`), adapté au nommage natif des services (nom de la spécification = nom de la classe/interface, comme partout ailleurs dans le framework natif) |
| Sandboxing | Pragmatique : **aucune isolation de `exec()`** au-delà des `builtins` standard. Le service est `secure = True` : seul un appelant authentifié et autorisé (`call:scripts`) peut l'invoquer, donc il exécute du code que l'opérateur a lui-même déposé — du code de confiance, pas une entrée utilisateur non fiable. Documenté comme risque explicite ci-dessous plutôt que sur-conçu |
| Valeur de retour | Le script peut fixer une variable globale `result` ; à défaut, `"script executed"` (comportement du legacy, conservé comme valeur par défaut) |
| Méthode HTTP | Seul `POST` est supporté, comme le legacy (`has_get`/`has_put`/`has_delete` valaient tous `False` malgré le mort-code `get`/`delete`) |

## 1. Modèle (`src/main/python/ycappuccino/scripts/models/script.py`)

```python
from ycappuccino.api.decorators import Item, Property
from ycappuccino.api.models import Model


@Item(collection="scripts", name="script", plural="scripts", secure_read=True, secure_write=True)
class Script(Model):

    def __init__(self, a_dict=None):
        super().__init__(a_dict)
        self._name = None
        self._source = None

    @Property(name="name")
    def name(self, a_value):
        self._name = a_value

    @Property(name="source")
    def source(self, a_value):
        self._source = a_value
```

Deux champs seulement : `name` (libellé), `source` (le code Python). Persisté par `ycappuccino-storage`, comme n'importe quel `@Item` (`storage/README.md`).

## 2. Exécution (`src/main/python/ycappuccino/scripts/execution.py`)

Module pur, sans composant, testable sans framework ni `IManager` :

```python
"""
Parses the leading `# @Require ClassName varname [ldapFilter]` lines of a script and executes
the remaining source with the resolved services injected as globals.

Kept from the legacy convention (ycappuccino.scripts.bundles.script_interpreter, retired): one
binding per line, at the top of the script. Improved over the legacy single-line limit: several
leading @Require lines are now accepted, one per requirement.
"""

import re

_REQUIRE = re.compile(r"^#\s*@Require\s+(\S+)\s+(\S+)(?:\s+(\S+))?\s*$")


def parse_requirements(source):
    """returns ([(spec_name, variable_name, ldap_filter_or_None), ...], remaining_source)"""
    lines = source.splitlines(keepends=True)
    requirements = []
    index = 0
    for line in lines:
        match = _REQUIRE.match(line.rstrip("\n"))
        if match is None:
            break
        requirements.append(match.groups())
        index += 1
    return requirements, "".join(lines[index:])


def execute(source, resolve_service, extra_globals=None):
    """
    resolve_service(spec_name, ldap_filter) -> object, called once per leading @Require line.
    Runs the remaining source with the resolved services (and extra_globals) as globals; returns
    the script's global `result`, or "script executed" if it did not set one (legacy default).
    """
    requirements, body = parse_requirements(source)
    script_globals = dict(extra_globals or {})
    for spec_name, variable_name, ldap_filter in requirements:
        script_globals[variable_name] = resolve_service(spec_name, ldap_filter)
    exec(compile(body, "<script>", "exec"), script_globals)
    return script_globals.get("result", "script executed")
```

- `resolve_service` est injecté par l'appelant (le composant `ScriptService`, section 3) : `execution.py` ne connaît ni `Framework`, ni Pelix, ce qui le rend testable avec un simple `lambda`.
- Une exception levée par le script (erreur de syntaxe, `resolve_service` qui échoue, erreur métier du script) remonte telle quelle à l'appelant : `ScriptService.call` ne l'attrape pas, elle devient une erreur non gérée côté `endpoints_service`/`http_server` (HTTP 500), comme n'importe quelle exception inattendue ailleurs dans le framework.

## 3. `ScriptService(IExposedService)` (`src/main/python/ycappuccino/scripts/service.py`)

```python
from ycappuccino.api.endpoints_service import IExposedService, ServiceResult
from ycappuccino.api.endpoints_storage import NotFound
from ycappuccino.api.storage import IManager
from ycappuccino.scripts.execution import execute


class ScriptService(IExposedService):
    name = "scripts"
    secure = True

    def __init__(self, manager: IManager, resolve_service=None):
        self._manager = manager
        self._resolve_service = resolve_service or _resolve_from_framework

    async def start(self):
        pass

    async def stop(self):
        pass

    async def call(self, method, extra_path, params, body, subject):
        if method != "POST" or len(extra_path) != 2 or extra_path[1] != "execute":
            raise NotFound("not found")
        script_id = extra_path[0]
        script = await self._manager.get_one("script", script_id, subject=subject)
        if script is None:
            raise NotFound(f"unknown script {script_id}")
        result = execute(script.get_storage_model()["source"], self._resolve_service)
        return ServiceResult(body={"result": result})


def _resolve_from_framework(spec_name, ldap_filter):
    from ycappuccino.core.framework import Framework  # lazy: keeps unit tests framework-free

    context = Framework.get_framework().context
    reference = context.get_service_reference(spec_name, ldap_filter)
    if reference is None:
        raise NotFound(f"no service available for {spec_name}")
    return context.get_service(reference)
```

- `resolve_service` est un deuxième paramètre de constructeur **sans annotation de type** : ce n'est donc pas une dépendance native (voir `core/README.md`, tableau d'injection), c'est une propriété ordinaire, qui vaut toujours `None` en usage réel (jamais surchargée dans `application.yml`) — sa seule raison d'être est de permettre aux tests unitaires d'injecter un faux résolveur de service sans construire un vrai framework Pelix.
- `extra_path` reprend la forme legacy `{scriptId}/execute` : `extra_path == [script_id, "execute"]`. Toute autre forme, ou une méthode différente de `POST`, lève `NotFound` (même famille d'erreurs qu'`endpoints_storage`/`endpoints_service`).
- La lecture du script passe `subject` à `IManager.get_one` : si `permissions_app` (ou toute autre app) publie un `IFilter` multi-tenant, un script reste soumis aux mêmes règles de visibilité que n'importe quel autre item.
- `_resolve_from_framework` réutilise exactement le mécanisme déjà décrit dans `core/README.md` (`Framework.get_framework().context.get_service_reference(...)`), déjà utilisé ailleurs dans le framework (ex. `ListComponent` de `core`) — pas de nouveau concept.

## 4. Hors périmètre

- **Sandbox d'exécution** (namespace restreint, `RestrictedPython`, timeouts, limites mémoire/CPU) : explicitement écarté, voir Risques.
- **Upload de fichier pour le script** : `source` est une propriété texte ordinaire ; si un besoin de gros scripts binaires apparaît un jour, `multipart` (`storage/README.md`) est la voie déjà prévue par `storage`, réutilisable sans changer `ScriptService`.
- **Versionning / historique des scripts** : un `up_sert` écrase la version précédente, comme tout autre item.
- **Nouvelles routes HTTP** : `endpoints_service` + `http_server` exposent déjà `POST /api/services/scripts/{scriptId}/execute` dès que `ycappuccino.scripts` est chargé ; aucun code de transport à écrire ici.

## 5. Packaging et exemple

```
scripts/
  pyproject.toml
  README.md
  example/conf/application.yml
  example/library/__init__.py
  example/library/demo.py
  src/main/python/ycappuccino/scripts/
    __init__.py
    models/
      __init__.py
      script.py          Script
    execution.py          parse_requirements, execute
    service.py            ScriptService
  src/unittest/python/
    scripts_fixtures.py
    test_execution.py
    test_script_service.py
    test_scripts_framework.py
    test_readme.py
```

- **`pyproject.toml`** (uv, `uv_build`) : projet `ycappuccino-scripts`, module `ycappuccino.scripts`, racine `src/main/python`. Dépendances : `ycappuccino-api`, `ycappuccino-core`, `ycappuccino-storage`, `ycappuccino-endpoints-service`. **Pas** de `dukpy`.
- **Supprimés** : `build.py`, `setup.py` (PyBuilder), `src/main/python/ycappuccino/scripts/bundles/` (legacy `ScriptInterpreter`, `IService`/`dukpy`/`@ComponentFactory`), `src/main/python/ycappuccino/scripts/conf/config.yaml` (déclaration de couche legacy, remplacée par le fichier natif si besoin — ici aucune couche n'est nécessaire, le composant natif n'en déclare pas).
- **Exemple** : couche mémoire de `storage`, un composant `ScriptDemo` stocke un script au démarrage puis l'exécute en appelant `ScriptService.call(...)` **directement** (pas via `IServiceEndpoint`) : le contrôle d'autorisation d'un service `secure=True` est la responsabilité de `IServiceEndpoint._check` (`endpoints_service/README.md`, section « Autorisation »), qui a besoin d'un `IAuthorization` — fourni par `permissions_app`, un dépôt encore en cours et non disponible comme dépendance ici. Appeler le service directement reste un usage légitime et documenté (`IExposedService.call` est indépendant du transport, y compris de l'endpoint lui-même) ; un exemple bout-en-bout avec autorisation appartient à une future application qui combine `scripts` et `permissions_app`.
- **README** : mise en place, modèle, exécution, convention `# @Require`, avertissement sécurité.

## 6. Tests

| Fichier | Contenu |
|---|---|
| `test_execution.py` | `parse_requirements` : aucune ligne, une ligne sans filtre, une ligne avec filtre LDAP, plusieurs lignes, une ligne `@Require` qui n'est pas en tête (ignorée) ; `execute` : renvoie `result`, valeur par défaut `"script executed"`, injecte le service résolu sous son nom de variable |
| `test_script_service.py` | `name`/`secure` de la classe ; exécute un script stocké et renvoie son résultat ; valeur par défaut sans `result` ; injecte un service via `# @Require` avec un `resolve_service` factice ; script introuvable (`NotFound`) ; méthode ou chemin non supportés (`NotFound`) |
| `test_scripts_framework.py` | démarrage du framework (mémoire), `ScriptService` publié, un script stocké via le vrai `IManager` puis exécuté via `ScriptService`, avec injection d'un vrai service du framework (`IActivityLogger`) par `# @Require` |
| `test_readme.py` | l'exemple exécutable du README |

## 7. Risques

- **Exécution de code non isolée** : `exec()` a un accès complet à l'interpréteur Python (système de fichiers, réseau, imports). C'est un choix assumé, pas un oubli : ce service n'a de sens que pour un opérateur de confiance, déjà authentifié et explicitement autorisé (`call:scripts`) par l'`IAuthorization` de l'application qui charge `ycappuccino.scripts`. Il ne doit **jamais** être exposé à une entrée non fiable (utilisateur final, requête anonyme) — c'est la même hypothèse que le legacy (`is_secure()` retournait déjà `True`), simplement rendue explicite ici. Une vraie isolation (sous-processus, conteneur, `RestrictedPython`) resterait possible en couche au-dessus si le besoin apparaissait, mais serait hors de proportion pour ce cas d'usage.
- **`# @Require` sans service disponible** : lève `NotFound`, qui remonte comme une erreur HTTP 404 via `endpoints_service`/`http_server` — cohérent avec le reste du framework, mais un message peu spécifique pour un opérateur qui débogue un script (amélioration possible : un message dédié, non fait ici pour rester simple).
- **`resolve_service` en clair dans le constructeur** : un paramètre non typé qui n'est ni une dépendance ni une vraie propriété métier est un léger détournement du modèle d'injection ; accepté ici parce que l'alternative (importer et patcher `ycappuccino.core.framework.Framework` dans les tests unitaires) serait plus fragile et coupler ces tests au framework réel.
