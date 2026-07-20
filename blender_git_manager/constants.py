"""Shared constants for Blender Git Manager."""

from __future__ import annotations

ADDON_NAME = "Blender Git Manager"
ADDON_VERSION = (0, 1, 3)
DEFAULT_BRANCH = "main"
DEFAULT_REMOTE = "origin"
MAX_HISTORY_COMMITS = 100
MAX_OUTPUT_LINES = 300

DEFAULT_LFS_PATTERNS = (
    "*.blend",
    "*.fbx",
    "*.glb",
    "*.gltf",
    "*.abc",
    "*.usd",
    "*.usdc",
    "*.usdz",
    "*.exr",
    "*.hdr",
    "*.psd",
    "*.tif",
    "*.tiff",
    "*.wav",
    "*.mp3",
    "*.mp4",
    "*.mov",
)

DEFAULT_GITIGNORE = """# Blender automatic backups
*.blend1
*.blend2
*.blend3
*.blend@

# Blender temporary files
*.blend.tmp
*.tmp
*.temp

# Python cache
__pycache__/
*.pyc

# Operating system
.DS_Store
Thumbs.db

# Secrets and credentials
.env
*.pem
*.key
credentials.json
"""

SENSITIVE_ARGUMENT_MARKERS = (
    "token",
    "password",
    "passwd",
    "secret",
    "authorization",
    "credential",
)

DANGEROUS_FILE_PATTERNS = (
    ".env",
    "*.pem",
    "*.key",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
)
