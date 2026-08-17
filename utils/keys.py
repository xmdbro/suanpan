from fastapi import Request, HTTPException

def get_namespace_key(request: Request) -> tuple[str, str]:
    """
    Extracts namespace and key from the request path parameters.
    """
    namespace = request.path_params.get("namespace", "")
    key = request.path_params.get("key", "")
    
    if not namespace or not key:
        raise HTTPException(status_code=400, detail="Namespace and key are required")
        
    return namespace, key

def create_key(namespace: str, key: str, is_admin: bool = False) -> str:
    """
    Constructs the database key.
    """
    prefix = "suanpan"
    if is_admin:
        return f"{prefix}:admin:{key}"
    return f"{prefix}:{namespace}:{key}"

def create_admin_key(db_key: str) -> str:
    """
    Creates an admin key based on a standard db_key.
    Example: suanpan:namespace:key -> suanpan:admin:key
    """
    parts = db_key.split(":")
    if len(parts) >= 3:
        return f"{parts[0]}:admin:{parts[2]}"
    return f"admin:{db_key}"
