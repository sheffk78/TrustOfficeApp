"""Module entrypoint: python -m mcp_server (requires ADMIN_API_KEY env var)."""

from mcp_server.server import main

if __name__ == "__main__":
    main()