import os
import requests
from dotenv import load_dotenv

"""
label_synchronizer.py
---------------------
Sincroniza labels entre issues migrados anteriormente.
Requisitos solicitados:
1. Leer todos los issues de los repos origen
2. Actualizar labels de los issues correspondientes en el repo destino (añadir/quitar)
3. Añadir labels que representen el tamaño y el estado columna (TODO, in progress, done, etc.) provenientes de proyectos de la organización origen
4. Omitir labels que no existan en el repositorio destino

Suposiciones:
- Ya se ejecutó issue_migrator.py y los issues existen (para matching se usa el título).
- Labels de tamaño se detectan por prefijos comunes (e.g., Size:, Tamaño:, Story Points:, Points:, SP: ).
- Estado de columna de proyecto: se intenta localizar el issue en proyectos clásicos y se anota con label "Project: <Column>" si dicha label existe en el destino.
- Para proyectos V2 (beta) no se hace query avanzada GraphQL de items -> columns (requeriría item iteration); se puede ampliar luego.
"""


def check_env_vars():
    required_vars = ["GITHUB_TOKEN", "ORG_SOURCE", "ORG_DEST", "REPOS"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"❌ Faltan variables de entorno requeridas: {', '.join(missing)}")
        exit(1)

load_dotenv()
check_env_vars()


# After check_env_vars(), these are guaranteed to be str
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""
ORG_SOURCE = os.getenv("ORG_SOURCE") or ""
ORG_DEST = os.getenv("ORG_DEST") or ""
REPOS = [r.strip() for r in os.getenv("REPOS", "").split(",") if r.strip()]

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

SIZE_LABEL_PREFIXES = [
    "size:", "tamaño:", "story points:", "points:", "sp:", "point:", "estimate:", "estimación:", "estimacion:"  # normalizados a minúsculas
]


def log(msg: str):
    print(f"[LABEL SYNC] {msg}")


# ----------------------------------------------------------
# Utilidades básicas
# ----------------------------------------------------------

def paginated_get(url: str):
    while url:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            log(f"❌ Error GET {url}: {resp.status_code} - {resp.text}")
            return
        yield resp.json()
        url = resp.links.get("next", {}).get("url")


def get_issues(org: str, repo: str):
    url = f"https://api.github.com/repos/{org}/{repo}/issues?state=all&per_page=100"
    issues = []
    for page in paginated_get(url) or []:
        issues.extend(page)
    return [i for i in issues if "pull_request" not in i]


def find_issue_by_title(org: str, repo: str, title: str):
    # paginar hasta encontrarlo (optimización simple)
    url = f"https://api.github.com/repos/{org}/{repo}/issues?state=all&per_page=100"
    while url:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            log(f"❌ Error buscando issue por título: {resp.status_code} - {resp.text}")
            return None
        for issue in resp.json():
            if "pull_request" in issue:
                continue
            if issue.get("title") == title:
                return issue
        url = resp.links.get("next", {}).get("url")
    return None


def get_existing_labels(org: str, repo: str):
    url = f"https://api.github.com/repos/{org}/{repo}/labels?per_page=100"
    existing = set()
    for page in paginated_get(url) or []:
        for label in page:
            name = label.get("name")
            if name:
                existing.add(name)
    return existing


def filter_existing(labels, existing):
    return [l for l in labels if l in existing]


# ----------------------------------------------------------
# Project column detection (classic projects)
# ----------------------------------------------------------

def get_projects(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/projects"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    return resp.json()

def get_columns(project_id):
    url = f"https://api.github.com/projects/{project_id}/columns"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    return resp.json()

def get_cards(column_id):
    url = f"https://api.github.com/projects/columns/{column_id}/cards"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    return resp.json()

def find_issue_column_in_projects(projects, issue_number):
    for project in projects:
        columns = get_columns(project['id'])
        for col in columns:
            if find_issue_in_column(col, issue_number):
                return col.get("name")
    return None

def find_issue_in_column(col, issue_number):
    cards = get_cards(col['id'])
    for card in cards:
        content_url = card.get("content_url")
        if content_url and content_url.endswith(f"/issues/{issue_number}"):
            return True
    return False

def get_issue_project_column(org: str, repo: str, issue_number: int):
    """Devuelve el nombre de la columna del project classic donde está el issue (primera coincidencia)."""
    try:
        projects = get_projects(org, repo)
        column_name = find_issue_column_in_projects(projects, issue_number)
        if column_name:
            return column_name
    except Exception as e:
        log(f"⚠️ Error detectando columna de proyecto para issue #{issue_number}: {e}")
    return None


# ----------------------------------------------------------
# Size label detection
# ----------------------------------------------------------

def detect_size_labels(original_labels):
    detected = []
    for lbl in original_labels:
        low = lbl.lower()
        for prefix in SIZE_LABEL_PREFIXES:
            if low.startswith(prefix):
                detected.append(lbl)
                break
    return detected


# ----------------------------------------------------------
# Sync logic
# ----------------------------------------------------------

def sync_issue_labels(source_issue: dict, target_issue: dict, existing_target_labels: set, repo: str):
    original_label_names = [l.get("name") for l in source_issue.get("labels", []) if l.get("name")]

    # Base: copy labels that already exist in target
    labels_to_apply = set(filter_existing(original_label_names, existing_target_labels))

    # Size labels (subset of original already filtered, so they stay if exist)
    size_labels = detect_size_labels(original_label_names)
    labels_to_apply.update([l for l in size_labels if l in existing_target_labels])

    # Project column -> label "Project: <Column>"
    project_column = get_issue_project_column(ORG_SOURCE, repo, source_issue["number"])
    if project_column:
        project_label_name = f"Project: {project_column}"
        if project_label_name in existing_target_labels:
            labels_to_apply.add(project_label_name)
        else:
            log(f"ℹ️ Label de columna '{project_label_name}' no existe en destino, se omite")

    desired_labels_sorted = sorted(labels_to_apply)

    # If sets differ, PATCH
    current_target_labels = {l.get("name") for l in target_issue.get("labels", []) if l.get("name")}
    if current_target_labels != set(desired_labels_sorted):
        patch_url = target_issue["url"]
        resp = requests.patch(patch_url, headers=HEADERS, json={"labels": desired_labels_sorted})
        if resp.status_code == 200:
            log(f"✅ Labels sincronizados para issue #{target_issue['number']} '{target_issue.get('title')}' -> {desired_labels_sorted}")
        else:
            log(f"❌ Error actualizando labels issue #{target_issue['number']}: {resp.status_code} - {resp.text}")
    else:
        log(f"✅ Labels ya alineados para issue #{target_issue['number']} ({target_issue.get('title')})")


def sync_repository(repo: str):
    log(f"\n====== Sincronizando labels repo {repo} ======")
    source_issues = get_issues(ORG_SOURCE, repo)
    if not source_issues:
        log("(sin issues origen)")
        return

    existing_target_labels = get_existing_labels(ORG_DEST, repo)
    log(f"🏷️ {len(existing_target_labels)} labels en destino {ORG_DEST}/{repo}")

    updated = 0
    skipped_missing_issue = 0

    for src in source_issues:
        tgt = find_issue_by_title(ORG_DEST, repo, src.get("title"))
        if not tgt:
            skipped_missing_issue += 1
            log(f"⚠️ Issue destino no encontrado para '{src.get('title')}', se omite")
            continue
        sync_issue_labels(src, tgt, existing_target_labels, repo)
        updated += 1

    log(f"Resumen repo {repo}: {updated} issues sincronizados, {skipped_missing_issue} sin match")


def main():
    print("=" * 60)
    print("🔄  SINCRONIZADOR DE LABELS")
    print("=" * 60)

    if not GITHUB_TOKEN or not ORG_SOURCE or not ORG_DEST or not REPOS:
        log("❌ Variables de entorno incompletas. Requiere GITHUB_TOKEN, ORG_SOURCE, ORG_DEST, REPOS")
        return

    for repo in REPOS:
        sync_repository(repo)

    print("=" * 60)
    log("🎉 Sincronización de labels completada")


if __name__ == "__main__":
    main()
