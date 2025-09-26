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

HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
GRAPHQL_URL = "https://api.github.com/graphql"

# Configuración de colores para las etiquetas de proyecto
PROJECT_LABEL_COLORS = {
    "todo": "d73a4a",          # Rojo
    "to do": "d73a4a",         # Rojo
    "backlog": "d73a4a",       # Rojo
    "in progress": "fbca04",   # Amarillo
    "in review": "0052cc",     # Azul
    "review": "0052cc",        # Azul
    "testing": "5319e7",       # Morado
    "done": "0e8a16",          # Verde
    "completed": "0e8a16",     # Verde
    "closed": "0e8a16",        # Verde
    "default": "bfd4f2"        # Azul claro por defecto
}

# ==========================================================
# Funciones auxiliares
# ==========================================================

def log(msg):
    """Imprime logs de forma verbosa"""
    print(f"[LOG] {msg}")

def get_column_color(column_name):
    """Obtiene un color apropiado para la columna basado en su nombre"""
    column_lower = column_name.lower().strip()
    return PROJECT_LABEL_COLORS.get(column_lower, PROJECT_LABEL_COLORS["default"])

def execute_graphql_query(query, variables=None):
    """Ejecuta una consulta GraphQL"""
    data = {"query": query}
    if variables:
        data["variables"] = variables
    
    resp = requests.post(GRAPHQL_URL, headers=HEADERS, json=data)
    
    if resp.status_code != 200:
        log(f"❌ Error en consulta GraphQL: {resp.status_code} - {resp.text}")
        return None
    
    result = resp.json()
    if "errors" in result:
        log(f"❌ Errores GraphQL: {result['errors']}")
        return None
    
    return result.get("data")

def get_organization_projects_v2(org):
    """Obtiene todos los proyectos V2 de la organización usando GraphQL"""
    projects = []
    cursor = None
    
    try:
        while True:
            after_clause = f', after: "{cursor}"' if cursor else ""
            query = f"""
            query {{
                organization(login: "{org}") {{
                    projectsV2(first: 20{after_clause}) {{
                        pageInfo {{
                            hasNextPage
                            endCursor
                        }}
                        nodes {{
                            id
                            title
                            number
                        }}
                    }}
                }}
            }}
            """
            
            data = execute_graphql_query(query)
            if not data or not data.get("organization"):
                break
            
            projects_data = data["organization"]["projectsV2"]
            projects.extend(projects_data["nodes"])
            
            if not projects_data["pageInfo"]["hasNextPage"]:
                break
            cursor = projects_data["pageInfo"]["endCursor"]
        
        log(f"🏢 Encontrados {len(projects)} proyectos V2 en la organización {org}")
        
    except Exception as e:
        log(f"❌ Error obteniendo proyectos V2 de la organización: {str(e)}")
    
    return projects

def get_user_projects_v2(user):
    """Obtiene todos los proyectos V2 del usuario usando GraphQL"""
    projects = []
    cursor = None
    
    try:
        while True:
            after_clause = f', after: "{cursor}"' if cursor else ""
            query = f"""
            query {{
                user(login: "{user}") {{
                    projectsV2(first: 20{after_clause}) {{
                        pageInfo {{
                            hasNextPage
                            endCursor
                        }}
                        nodes {{
                            id
                            title
                            number
                        }}
                    }}
                }}
            }}
            """
            
            data = execute_graphql_query(query)
            if not data or not data.get("user"):
                break
            
            projects_data = data["user"]["projectsV2"]
            projects.extend(projects_data["nodes"])
            
            if not projects_data["pageInfo"]["hasNextPage"]:
                break
            cursor = projects_data["pageInfo"]["endCursor"]
        
        log(f"👤 Encontrados {len(projects)} proyectos V2 del usuario {user}")
        
    except Exception as e:
        log(f"❌ Error obteniendo proyectos V2 del usuario: {str(e)}")
    
    return projects

def get_project_fields_and_options(project_id):
    """Obtiene los campos y opciones de un proyecto V2"""
    field_options = set()
    
    try:
        query = f"""
        query {{
            node(id: "{project_id}") {{
                ... on ProjectV2 {{
                    title
                    fields(first: 20) {{
                        nodes {{
                            ... on ProjectV2SingleSelectField {{
                                id
                                name
                                options {{
                                    id
                                    name
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }}
        """
        
        data = execute_graphql_query(query)
        if not data or not data.get("node"):
            return field_options
        
        project = data["node"]
        log(f"   📁 Proyecto V2: '{project['title']}'")
        
        for field in project["fields"]["nodes"]:
            if field and "options" in field:
                field_name = field["name"]
                log(f"      🔧 Campo: '{field_name}'")
                
                for option in field["options"]:
                    option_name = option["name"]
                    field_options.add(option_name)
                    log(f"         📌 Opción: '{option_name}'")
        
    except Exception as e:
        log(f"❌ Error obteniendo campos del proyecto: {str(e)}")
    
    return field_options

def get_repository_projects(org, repo):
    """Obtiene todos los proyectos de un repositorio específico"""
    projects = []
    
    try:
        # Obtener proyectos del repositorio
        projects_url = f"https://api.github.com/repos/{org}/{repo}/projects"
        projects_resp = requests.get(projects_url, headers=HEADERS)
        
        if projects_resp.status_code != 200:
            log(f"⚠️ Error obteniendo proyectos de {org}/{repo}: {projects_resp.status_code}")
            return projects
        
        projects = projects_resp.json()
        log(f"� Encontrados {len(projects)} proyectos en el repositorio {org}/{repo}")
        
    except Exception as e:
        log(f"❌ Error obteniendo proyectos del repositorio: {str(e)}")
    
    return projects

def get_project_columns_from_projects(projects):
    """Obtiene todas las columnas de una lista de proyectos"""
    columns = set()  # Usar set para evitar duplicados
    
    try:
        for project in projects:
            log(f"   📁 Proyecto: '{project['name']}'")
            
            # Obtener columnas del proyecto
            columns_url = f"https://api.github.com/projects/{project['id']}/columns"
            columns_resp = requests.get(columns_url, headers=HEADERS)
            
            if columns_resp.status_code != 200:
                log(f"   ⚠️ Error obteniendo columnas del proyecto '{project['name']}': {columns_resp.status_code}")
                continue
                
            project_columns = columns_resp.json()
            
            for column in project_columns:
                columns.add(column['name'])
                log(f"      📌 Columna: '{column['name']}'")
    
    except Exception as e:
        log(f"❌ Error obteniendo columnas de proyectos: {str(e)}")
    
    return columns

def get_project_field_options(org):
    """Obtiene todas las opciones de campos de proyectos V2 (organización)"""
    all_options = set()
    
    # Obtener opciones de proyectos de la organización
    org_projects = get_organization_projects_v2(org)
    for project in org_projects:
        project_options = get_project_fields_and_options(project["id"])
        all_options.update(project_options)
    
    # También intentar como usuario (para proyectos personales)
    try:
        user_projects = get_user_projects_v2(org)
        for project in user_projects:
            project_options = get_project_fields_and_options(project["id"])
            all_options.update(project_options)
    except Exception:
        # Silenciar errores si no es un usuario
        pass
    
    return all_options

def get_existing_labels(org, repo):
    """Obtiene todas las etiquetas existentes en el repositorio"""
    url = f"https://api.github.com/repos/{org}/{repo}/labels"
    existing_labels = set()
    
    while url:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            log(f"⚠️ Error obteniendo labels de {org}/{repo}: {resp.status_code}")
            return existing_labels
        
        labels = resp.json()
        for label in labels:
            existing_labels.add(label["name"])
        
        # paginación
        url = resp.links.get("next", {}).get("url")
    
    log(f"🏷️ {len(existing_labels)} etiquetas existentes en {org}/{repo}")
    return existing_labels

def create_project_label(org, repo, option_name):
    """Crea una etiqueta de proyecto en el repositorio destino"""
    label_name = f"Project: {option_name}"
    label_color = get_column_color(option_name)
    
    url = f"https://api.github.com/repos/{org}/{repo}/labels"
    
    data = {
        "name": label_name,
        "description": f"Issue belongs to project field option: {option_name}",
        "color": label_color
    }
    
    resp = requests.post(url, headers=HEADERS, json=data)
    
    if resp.status_code == 201:
        log(f"✅ Etiqueta '{label_name}' creada en {org}/{repo}")
        return True
    elif resp.status_code == 422:
        # La etiqueta ya existe
        log(f"ℹ️ Etiqueta '{label_name}' ya existe en {org}/{repo}")
        return True
    else:
        log(f"❌ Error creando etiqueta '{label_name}': {resp.status_code} - {resp.text}")
        return False

def create_labels_for_repo(dest_repo):
    """Crea etiquetas de proyecto para un repositorio específico basado en proyectos V2"""
    log(f"🚀 Procesando repositorio destino: {dest_repo}")
    
    # Obtener todas las opciones de campos (organización)
    all_options = get_project_field_options(ORG_SOURCE)
    
    if not all_options:
        log(f"ℹ️ No se encontraron opciones de campos de proyecto en {ORG_SOURCE}")
        return
    
    log(f"📋 Total de opciones únicas encontradas: {len(all_options)}")
    log(f"   Opciones: {', '.join(sorted(all_options))}")
    
    # Obtener etiquetas existentes en el repo destino
    existing_labels = get_existing_labels(ORG_DEST, dest_repo)
    
    # Crear etiquetas para cada opción
    created_count = 0
    for option in sorted(all_options):
        label_name = f"Project: {option}"
        
        if label_name in existing_labels:
            log(f"ℹ️ Etiqueta '{label_name}' ya existe, se omite")
            continue
        
        if create_project_label(ORG_DEST, dest_repo, option):
            created_count += 1
    
    log(f"🎯 Proceso completado para {dest_repo}: {created_count} etiquetas nuevas creadas")

def show_preview():
    """Muestra una vista previa de qué etiquetas se crearán"""
    log("🔍 VISTA PREVIA - Analizando proyectos V2...")
    
    # Analizar proyectos de la organización
    log(f"\n--- Analizando proyectos V2 de la organización {ORG_SOURCE} ---")
    all_options = get_project_field_options(ORG_SOURCE)
    
    if all_options:
        log(f"Opciones de campos encontradas: {', '.join(sorted(all_options))}")
        
        log(f"\n📋 RESUMEN: Se crearán etiquetas para {len(all_options)} opciones únicas:")
        for option in sorted(all_options):
            color = get_column_color(option)
            log(f"   • Project: {option} (color: #{color})")
    else:
        log(f"\n⚠️ No se encontraron opciones de campos en proyectos V2 de {ORG_SOURCE}")
        log("💡 Nota: Asegúrate de que tienes acceso a los proyectos V2 y que tu token tiene el scope 'project'")
    
    return len(all_options) > 0

# ==========================================================
# Script principal
# ==========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🏷️  GENERADOR DE ETIQUETAS DE PROYECTO")
    print("=" * 60)
    
    # Mostrar vista previa
    if not show_preview():
        log("\n❌ No hay nada que procesar. Saliendo...")
        exit(0)
    
    # Pedir confirmación
    print(f"\n¿Deseas crear estas etiquetas en los repositorios de {ORG_DEST}? (y/N): ", end="")
    confirm = input().strip().lower()
    
    if confirm not in ['y', 'yes', 'sí', 's']:
        log("❌ Operación cancelada por el usuario")
        exit(0)
    
    # Crear etiquetas
    log(f"\n🚀 Creando etiquetas en repositorios de {ORG_DEST}...")
    
    for repo in REPOS:
        repo = repo.strip()
        print(f"\n{'='*40}")
        create_labels_for_repo(repo)
    
    print(f"\n{'='*60}")
    log("🎉 Proceso completado! Las etiquetas están listas para la migración de issues.")