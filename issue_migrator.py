import os
import requests
from dotenv import load_dotenv

# ==========================================================
# Cargar variables desde .env
# ==========================================================
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ORG_SOURCE = os.getenv("ORG_SOURCE")
ORG_DEST = os.getenv("ORG_DEST")
REPOS = os.getenv("REPOS").split(",") # type: ignore

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# ==========================================================
# Funciones auxiliares
# ==========================================================

def log(msg):
    """Imprime logs de forma verbosa"""
    print(f"[LOG] {msg}")

def get_issues(org, repo):
    """Obtiene todos los issues de un repo"""
    url = f"https://api.github.com/repos/{org}/{repo}/issues?state=all&per_page=100"
    issues = []
    while url:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            log(f"❌ Error al obtener issues: {resp.status_code} - {resp.text}")
            return []
        issues.extend(resp.json())
        # paginación
        url = resp.links.get("next", {}).get("url")
    log(f"✅ {len(issues)} issues obtenidos de {org}/{repo}")
    return issues

def find_existing_issue(org, repo, title):
    """Busca si ya existe un issue con el mismo título en el repo destino"""
    url = f"https://api.github.com/repos/{org}/{repo}/issues?state=all&per_page=100"
    
    while url:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            log(f"❌ Error al buscar issues existentes: {resp.status_code} - {resp.text}")
            return None
        
        issues = resp.json()
        for issue in issues:
            # Saltar PRs
            if "pull_request" in issue:
                continue
            if issue["title"] == title:
                return issue
        
        # paginación
        url = resp.links.get("next", {}).get("url")
    
    return None

def create_issue(org, repo, issue):
    """Crea un issue en el repo destino manteniendo título, cuerpo, responsables y estado.
    Nota: La lógica de labels y columnas de proyecto fue movida al script separado de sincronización de labels.
    """
    
    # Verificar si ya existe un issue con el mismo título
    existing_issue = find_existing_issue(org, repo, issue["title"])
    
    if existing_issue:
        log(f"🔍 Issue '{issue['title']}' ya existe en {org}/{repo} (#{existing_issue['number']})")
        
        # Verificar si necesitamos actualizar el estado
        if existing_issue["state"] != issue["state"]:
            if issue["state"] == "closed":
                close_issue(org, repo, existing_issue["number"])
            else:
                reopen_issue(org, repo, existing_issue["number"])
        else:
            log(f"✅ Issue '{issue['title']}' ya tiene el estado correcto ({issue['state']})")
        
        return existing_issue
    
    # Si no existe, crear el issue (sin labels; se sincronizarán por el nuevo script)
    url = f"https://api.github.com/repos/{org}/{repo}/issues"

    data = {
        "title": issue["title"],
        "body": issue.get("body", ""),
        # labels vacíos aquí; otro script hará la sincronización
        "labels": [],
        "assignees": [assignee["login"] for assignee in issue.get("assignees", [])],
    }

    resp = requests.post(url, headers=HEADERS, json=data)

    if resp.status_code == 201:
        new_issue = resp.json()
        log(f"✅ Issue '{issue['title']}' creado en {org}/{repo} (#{new_issue['number']})")
        
        # Si el issue original estaba cerrado, cerrarlo en el destino
        if issue["state"] == "closed":
            close_issue(org, repo, new_issue["number"])
            
        return new_issue
    else:
        log(f"❌ Error creando issue '{issue['title']}': {resp.status_code} - {resp.text}")
        return None

def close_issue(org, repo, issue_number):
    """Cierra un issue en el repo destino"""
    url = f"https://api.github.com/repos/{org}/{repo}/issues/{issue_number}"
    
    data = {"state": "closed"}
    
    resp = requests.patch(url, headers=HEADERS, json=data)
    
    if resp.status_code == 200:
        log(f"✅ Issue #{issue_number} cerrado en {org}/{repo}")
        return True
    else:
        log(f"❌ Error cerrando issue #{issue_number}: {resp.status_code} - {resp.text}")
        return False

def reopen_issue(org, repo, issue_number):
    """Reabre un issue en el repo destino"""
    url = f"https://api.github.com/repos/{org}/{repo}/issues/{issue_number}"
    
    data = {"state": "open"}
    
    resp = requests.patch(url, headers=HEADERS, json=data)
    
    if resp.status_code == 200:
        log(f"✅ Issue #{issue_number} reabierto en {org}/{repo}")
        return True
    else:
        log(f"❌ Error reabriendo issue #{issue_number}: {resp.status_code} - {resp.text}")
        return False

def migrate_repo(repo):
    """Migra issues de un repo de ORG_SOURCE a ORG_DEST"""
    log(f"🚀 Migrando issues de {ORG_SOURCE}/{repo} → {ORG_DEST}/{repo}")
    issues = get_issues(ORG_SOURCE, repo)

    for issue in issues:
        # Saltar PRs (aparecen como issues en la API)
        if "pull_request" in issue:
            continue
        # Sincronizar asignees si el issue ya existe
        existing_issue = find_existing_issue(ORG_DEST, repo, issue["title"])
        if existing_issue:
            origin_assignees = set([a["login"] for a in issue.get("assignees", [])])
            dest_assignees = set([a["login"] for a in existing_issue.get("assignees", [])])
            if origin_assignees != dest_assignees:
                url = f"https://api.github.com/repos/{ORG_DEST}/{repo}/issues/{existing_issue['number']}"
                data = {"assignees": list(origin_assignees)}
                resp = requests.patch(url, headers=HEADERS, json=data)
                if resp.status_code == 200:
                    log(f"🔄 Asignees sincronizados en issue '{issue['title']}' ({existing_issue['number']})")
                elif resp.status_code == 422 and "could not be found" in resp.text.lower():
                    # Algún asignee no existe en el repo destino, intentar con lista vacía
                    log(f"⚠️ Algún asignee no existe en el repo destino para issue '{issue['title']}', dejando vacío y reintentando...")
                    data_empty = {"assignees": []}
                    resp2 = requests.patch(url, headers=HEADERS, json=data_empty)
                    if resp2.status_code == 200:
                        log(f"🔄 Asignees vacíos sincronizados en issue '{issue['title']}' ({existing_issue['number']})")
                    else:
                        log(f"❌ Error sincronizando asignees vacíos en issue '{issue['title']}': {resp2.status_code} - {resp2.text}")
                else:
                    log(f"❌ Error sincronizando asignees en issue '{issue['title']}': {resp.status_code} - {resp.text}")
        create_issue(ORG_DEST, repo, issue)

# ==========================================================
# Script principal
# ==========================================================
if __name__ == "__main__":
    for repo in REPOS:
        repo = repo.strip()
        migrate_repo(repo)
