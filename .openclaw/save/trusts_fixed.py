# --- Exclusive Path Route Lock ---

# Remove the old logger/debug snippet that caused the patch misalignment and 500s
# 
# --- Inject route guard function ---

async def ensure_routes_exclusive():
    """Prevent duplicate registration of /trusts paths by using direct FastAPI injection.
    """
    if hasattr(router, "_routes_lock"):
        return  # already guarded

    logger.info("Patched router routes: /trusts now guarded for GET/POST methods only.")
    router._routes_lock = True  # guard flag
    router.add("/trusts", get_trusts, methods=["GET"], response_model=List[TrustResponse], tags=["protected"])
    router.add("/trusts", create_trust, methods=["POST"], response_model=TrustResponse, tags=["protected"])


# --- EOF ---