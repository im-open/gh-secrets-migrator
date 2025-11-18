#!/usr/bin/env python3
"""GitHub Secrets Migrator - Migrate secrets from one repository to another."""

import warnings

# Suppress urllib3 SSL warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
warnings.filterwarnings("ignore", module="urllib3")

from src.cli import migrate

if __name__ == "__main__":
    migrate()
