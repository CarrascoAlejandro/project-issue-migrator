import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, cast

import requests
from dotenv import load_dotenv

GRAPHQL_URL = "https://api.github.com/graphql"

# -----------------------------
# Env and headers
# -----------------------------
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ORG_SOURCE = os.getenv("ORG_SOURCE")
ORG_DEST = os.getenv("ORG_DEST")
REPOS = [r.strip() for r in os.getenv("REPOS", "").split(",") if r.strip()]
PROJECT_NAME = os.getenv("PROJECT")

if not GITHUB_TOKEN or not ORG_SOURCE or not ORG_DEST or not REPOS or not PROJECT_NAME:
    print("❌ Missing environment variables. Require GITHUB_TOKEN, ORG_SOURCE, ORG_DEST, REPOS, PROJECT")
    sys.exit(1)

HEADERS_GQL = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
HEADERS_REST = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

# Narrow types for static checkers after validation
ORG_SOURCE = cast(str, ORG_SOURCE)
ORG_DEST = cast(str, ORG_DEST)
PROJECT_NAME = cast(str, PROJECT_NAME)


def log(msg: str):
    print(f"[PROJECT V2 SYNC] {msg}")


# -----------------------------
# GraphQL helpers
# -----------------------------

def gql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {"query": query, "variables": variables or {}}
    resp = requests.post(GRAPHQL_URL, headers=HEADERS_GQL, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"GraphQL HTTP {resp.status_code}: {resp.text}")
    j = resp.json()
    if "errors" in j and j["errors"]:
        raise RuntimeError(f"GraphQL errors: {j['errors']}")
    return j.get("data", {})


def paginated_projects_v2_for_org(org: str) -> List[Dict[str, Any]]:
    projects = []
    cursor = None
    while True:
        q = """
        query($org:String!, $after:String) {
          organization(login:$org) {
            projectsV2(first:50, after:$after) {
              nodes { id title number }
              pageInfo { hasNextPage endCursor }
            }
          }
        }
        """
        data = gql(q, {"org": org, "after": cursor})
        pv2 = data.get("organization", {}).get("projectsV2", {})
        nodes = pv2.get("nodes", [])
        projects.extend(nodes)
        page = pv2.get("pageInfo", {})
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    return projects


def get_org_project_by_name(org: str, name: str) -> Optional[Dict[str, Any]]:
    for p in paginated_projects_v2_for_org(org):
        if p.get("title") == name:
            return p
    return None


def get_project_fields(project_id: str) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
                q = """
                query($id:ID!, $after:String) {
                    node(id:$id) {
                        ... on ProjectV2 {
                            fields(first:50, after:$after) {
                                nodes {
                                    __typename
                                    ... on ProjectV2SingleSelectField { id name dataType options { id name } }
                                    ... on ProjectV2Field { id name dataType }
                                }
                                pageInfo { hasNextPage endCursor }
                            }
                        }
                    }
                }
                """
                data = gql(q, {"id": project_id, "after": cursor})
                node = data.get("node") or {}
                f = node.get("fields") or {}
                fields.extend(f.get("nodes", []))
                page = f.get("pageInfo") or {}
                if not page.get("hasNextPage"):
                        break
                cursor = page.get("endCursor")
        return fields


def get_field_map(fields: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    # Map by lower-cased name
    return {f.get("name", "").lower(): f for f in fields}


def list_project_items_with_values(project_id: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
                q = """
                query($id:ID!, $after:String) {
                    node(id:$id) {
                        ... on ProjectV2 {
                            items(first:100, after:$after) {
                                nodes {
                                    id
                                    content { __typename ... on Issue { id number title repository { name } } }
                                    fieldValues(first:20) {
                                        nodes {
                                            __typename
                                            ... on ProjectV2ItemFieldSingleSelectValue { field { ... on ProjectV2SingleSelectField { id name } ... on ProjectV2Field { id name } } name optionId }
                                            ... on ProjectV2ItemFieldTextValue { field { ... on ProjectV2Field { id name } } text }
                                            ... on ProjectV2ItemFieldNumberValue { field { ... on ProjectV2Field { id name } } number }
                                        }
                                    }
                                }
                                pageInfo { hasNextPage endCursor }
                            }
                        }
                    }
                }
                """
                data = gql(q, {"id": project_id, "after": cursor})
                node = data.get("node") or {}
                it = node.get("items") or {}
                items.extend(it.get("nodes", []))
                page = it.get("pageInfo") or {}
                if not page.get("hasNextPage"):
                        break
                cursor = page.get("endCursor")
        return items


def gql_add_item_to_project(project_id: str, content_node_id: str) -> Optional[str]:
    q = """
    mutation($projectId:ID!, $contentId:ID!) {
      addProjectV2ItemById(input:{projectId:$projectId, contentId:$contentId}) {
        item { id }
      }
    }
    """
    try:
        data = gql(q, {"projectId": project_id, "contentId": content_node_id})
        item = data.get("addProjectV2ItemById", {}).get("item")
        return item.get("id") if item else None
    except RuntimeError as e:
        log(f"ℹ️ addProjectV2ItemById skipped: {e}")
        return None


def extract_values_map(field_values_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return {field_name_lower: {type, value, optionName?, optionId?}}"""
    result: Dict[str, Any] = {}
    for v in field_values_nodes or []:
        typename = v.get("__typename")
        field = v.get("field", {})
        name = field.get("name") if isinstance(field, dict) else None
        if not name:
            continue
        key = name.lower()
        if typename == "ProjectV2ItemFieldSingleSelectValue":
            result[key] = {"type": "single_select", "name": v.get("name"), "optionId": v.get("optionId")}
        elif typename == "ProjectV2ItemFieldNumberValue":
            result[key] = {"type": "number", "number": v.get("number")}
        elif typename == "ProjectV2ItemFieldTextValue":
            result[key] = {"type": "text", "text": v.get("text")}
    return result


def rest_find_issue_by_title(org: str, repo: str, title: str) -> Optional[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{org}/{repo}/issues?state=all&per_page=100"
    while url:
        resp = requests.get(url, headers=HEADERS_REST)
        if resp.status_code != 200:
            log(f"❌ REST error listing issues {org}/{repo}: {resp.status_code} - {resp.text}")
            return None
        for issue in resp.json():
            if "pull_request" in issue:
                continue
            if issue.get("title") == title:
                return issue
        url = resp.links.get("next", {}).get("url")
    return None


def gql_find_item_for_issue(project_id: str, issue_node_id: str) -> Optional[str]:
    # Brute-force search among items (acceptable for <= few thousand)
    for it in list_project_items_with_values(project_id):
        content = it.get("content") or {}
        if content.get("__typename") == "Issue" and content.get("id") == issue_node_id:
            return it.get("id")
    return None


def map_option_name_to_id(dest_field: Dict[str, Any], option_name: str) -> Optional[str]:
    options = (dest_field or {}).get("options", [])
    for opt in options:
        if opt.get("name", "").strip().lower() == (option_name or "").strip().lower():
            return opt.get("id")
    return None


def gql_update_field_value(project_id: str, item_id: str, field: Dict[str, Any], value_info: Dict[str, Any]):
    data_type = field.get("dataType")
    field_id = field.get("id")

    if data_type == "SINGLE_SELECT":
        option_name = value_info.get("name")
        if not isinstance(option_name, str) or not option_name:
            return
        option_id = map_option_name_to_id(field, option_name)
        if not option_id:
            log(f"⚠️ Option '{option_name}' not found in destination for field '{field.get('name')}', skipping")
            return
        q = """
        mutation($projectId:ID!, $itemId:ID!, $fieldId:ID!, $optionId:String!) {
          updateProjectV2ItemFieldValue(input:{projectId:$projectId, itemId:$itemId, fieldId:$fieldId, value:{singleSelectOptionId:$optionId}}) { clientMutationId }
        }
        """
        gql(q, {"projectId": project_id, "itemId": item_id, "fieldId": field_id, "optionId": option_id})
    elif data_type == "NUMBER":
        number = value_info.get("number")
        if number is None:
            return
        q = """
        mutation($projectId:ID!, $itemId:ID!, $fieldId:ID!, $number:Float!) {
          updateProjectV2ItemFieldValue(input:{projectId:$projectId, itemId:$itemId, fieldId:$fieldId, value:{number:$number}}) { clientMutationId }
        }
        """
        gql(q, {"projectId": project_id, "itemId": item_id, "fieldId": field_id, "number": float(number)})
    else:
        # Treat other as text (TEXT/DATE/UNKNOWN -> only TEXT supported here)
        text = value_info.get("text") or value_info.get("name")
        if text is None:
            return
        q = """
        mutation($projectId:ID!, $itemId:ID!, $fieldId:ID!, $text:String!) {
          updateProjectV2ItemFieldValue(input:{projectId:$projectId, itemId:$itemId, fieldId:$fieldId, value:{text:$text}}) { clientMutationId }
        }
        """
        gql(q, {"projectId": project_id, "itemId": item_id, "fieldId": field_id, "text": str(text)})


def sync_item_fields(src_values: Dict[str, Any], dest_field_map: Dict[str, Dict[str, Any]], project_id_dest: str, item_id_dest: str):
    for key in ["status", "size", "estimate", "type issue"]:
        if key not in src_values:
            continue
        dest_field = dest_field_map.get(key)
        if not dest_field:
            log(f"ℹ️ Destination field '{key}' not present, skipping")
            continue
        gql_update_field_value(project_id_dest, item_id_dest, dest_field, src_values[key])


def main():
    print("=" * 60)
    print("🔁 Project V2 items and fields sync")
    print("=" * 60)

    # Locate source/destination projects by name
    src_project = get_org_project_by_name(ORG_SOURCE or "", PROJECT_NAME or "")
    if not src_project:
        log(f"❌ Source project '{PROJECT_NAME}' not found in org {ORG_SOURCE}")
        sys.exit(1)
    dst_project = get_org_project_by_name(ORG_DEST or "", PROJECT_NAME or "")
    if not dst_project:
        log(f"❌ Destination project '{PROJECT_NAME}' not found in org {ORG_DEST}")
        sys.exit(1)

    log(f"Source project: {src_project['title']} (#{src_project['number']})")
    log(f"Dest project: {dst_project['title']} (#{dst_project['number']})")

    # Load fields
    src_fields = get_project_fields(src_project["id"])  # includes options for single-select
    dst_fields = get_project_fields(dst_project["id"])  # includes options for single-select
    src_field_map = get_field_map(src_fields)
    dst_field_map = get_field_map(dst_fields)

    # List source items with field values
    src_items = list_project_items_with_values(src_project["id"])  # includes content and fieldValues
    log(f"Found {len(src_items)} source project items")

    processed = 0
    skipped_repo = 0
    skipped_no_target_issue = 0

    for src_item in src_items:
        content = src_item.get("content") or {}
        if content.get("__typename") != "Issue":
            continue
        repo_name = content.get("repository", {}).get("name")
        if repo_name not in REPOS:
            skipped_repo += 1
            continue

        issue_title = content.get("title") or ""
        if not issue_title:
            skipped_no_target_issue += 1
            log("⚠️ Source issue missing title, skipping")
            continue
        # Find corresponding issue in destination org/repo by title
        target_issue = rest_find_issue_by_title(ORG_DEST or "", repo_name, issue_title)
        if not target_issue:
            skipped_no_target_issue += 1
            log(f"⚠️ Target issue not found for '{issue_title}' in {ORG_DEST}/{repo_name}")
            continue

        # Ensure item exists in destination project
        # Need GraphQL node id for the target issue
        # Use a lightweight GraphQL lookup by URL id
        issue_api_url = target_issue.get("url")
        # The REST issue returns "url" like https://api.github.com/repos/{org}/{repo}/issues/{number}
        # We need node id -> perform a short GQL query by repository + number
        q_issue = """
        query($owner:String!, $name:String!, $number:Int!) {
          repository(owner:$owner, name:$name) { issue(number:$number) { id number title } }
        }
        """
        data_issue = gql(q_issue, {"owner": ORG_DEST, "name": repo_name, "number": target_issue["number"]})
        issue_node = (data_issue.get("repository") or {}).get("issue")
        if not issue_node:
            log(f"❌ Could not resolve node id for {ORG_DEST}/{repo_name}#{target_issue['number']}")
            continue

        dest_item_id = gql_add_item_to_project(dst_project["id"], issue_node["id"]) or gql_find_item_for_issue(dst_project["id"], issue_node["id"])
        if not dest_item_id:
            log(f"❌ Could not add/find project item for {ORG_DEST}/{repo_name}#{target_issue['number']}")
            continue

        # Extract source values
        src_values = extract_values_map((src_item.get("fieldValues") or {}).get("nodes", []))

        # Sync only the requested fields. Setting Status replicates board column placement.
        sync_item_fields(src_values, dst_field_map, dst_project["id"], dest_item_id)
        processed += 1

    log("-" * 60)
    log(f"Processed: {processed}")
    log(f"Skipped (repo not listed): {skipped_repo}")
    log(f"Skipped (no target issue): {skipped_no_target_issue}")
    log("✅ Done")


if __name__ == "__main__":
    main()
