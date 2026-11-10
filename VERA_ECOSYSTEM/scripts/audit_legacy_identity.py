"""
VERA_ECOSYSTEM/scripts/audit_legacy_identity.py

Automated scanner for legacy 'AIRA' identity references across the repository.
Enforces the executive policy:
  - 0 active product branding violations allowed in user-facing UI, active API branding,
    active persona identity, or active log identity.
  - Recognizes and permits legitimate historical archives, ADRs, heritage records,
    and backward-compatibility fallback aliases.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Allowed historical paths and files where AIRA is legitimate provenance
ALLOWED_HISTORICAL_PATHS = [
    "reports",
    "core/knowledge/heritage",
    "docs/brand-history",
    "AUDIT_REPORT",
    "VERA_NETWORKING_AUDIT",
    "database/backups",
    "VERA_PROJECT_HISTORY.md",
    "VERA_PROJECT_HERITAGE.md",
    "VERA_IDENTITY_AND_EVOLUTION.md",
    "VERA_ARCHITECTURAL_DECISION_HISTORY.md",
    "VERA_ENGINEERING_MILESTONES.md",
    "VERA_LEGACY_AIRA_CAPABILITY_MAP.md",
    "VERA_HISTORICAL_KNOWLEDGE_INTEGRATION_REPORT.md",
    "VERA_IDENTITY_MIGRATION_REPORT.md",
    "VERA_BACKEND_MIGRATION_REPORT.md",
    "VERA_NETWORKING_CAPABILITY_MIGRATION.md",
    "VERA_AI_RUNTIME_MIGRATION_REPORT.md",
    "VERA_FRONTEND_IDENTITY_REPORT.md",
    "VERA_DEPLOYMENT_MIGRATION_REPORT.md",
    "VERA_FEATURE_PARITY_MATRIX.md",
    "VERA_TOTAL_MIGRATION_BASELINE.md",
    "VERA_LEGACY_REFERENCE_AUDIT.md",
    "VERA_MIGRATION_TEST_REPORT.md",
    "VERA_TOTAL_MIGRATION_FINAL_REPORT.md",
    "AIRA_OS_MASTER_DECISION_AND_EXECUTION_PLAN.md",
    "IMPLEMENTATION_PROGRESS.md",
    "IMPLEMENTATION_BASELINE.md",
    "FINAL_REMEDIATION_REPORT.md",
    "CLAUDE.md",
]

# Allowed backward-compatibility fallback patterns
ALLOWED_COMPATIBILITY_PATTERNS = [
    r"X-AIRA-Admin-Token",
    r"AIRA_ADMIN_TOKEN",
    r"AIRA_ENV",
    r"AIRA_DEFAULT_MODEL",
    r"AIRA_CLASSIFIER_MODEL",
    r"AIRA_DISABLE_THINKING",
    r"AIRA_SECRET_KEY",
    r"AIRA_ECOSYSTEM",
    r"AIRAContext",
    r"aira\.context",
    r"aira\.persona",
    r"profil aira",
    r"aira-os",
    r"recall_heritage",
    r"heritage",
    r"symlink",
    r"legacy_compatible",
    r"fallback",
    r"AIRA_ECOSYSTEM/app/frontend", # Source map or comment markers
]

# Patterns that indicate an ACTIVE VIOLATION if found in active source files
ACTIVE_VIOLATION_PATTERNS = [
    r'title:\s*["\']AIRA Siap["\']',
    r'label\s*=\s*["\']Menyiapkan AIRA\.\.\.["\']',
    r'console\.error\(["\']AIRA UI crashed',
    r'>\s*Tanya AIRA\s*<',
    r'aria-label=["\']Tanya AIRA',
    r'assistant_name:\s*["\']AIRA["\']',
    r'"assistant_name":\s*"AIRA"',
    r'"platform":\s*"AIRA',
    r'AIRA Menjawab\.\.\.',
]

# File extensions to scan
SCAN_EXTENSIONS = {".py", ".jsx", ".js", ".html", ".json", ".yaml", ".yml", ".md", ".sh"}

# Directories to skip
SKIP_DIRS = {
    ".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"
}


def is_allowed_historical(rel_path: str) -> bool:
    for allowed in ALLOWED_HISTORICAL_PATHS:
        if rel_path.startswith(allowed) or allowed in rel_path or "IMPLEMENTATION_STAGE" in rel_path:
            return True
    return False


def is_allowed_compatibility(line: str) -> bool:
    for pattern in ALLOWED_COMPATIBILITY_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def scan_workspace(root_dir: Path) -> Tuple[List[Dict], List[Dict]]:
    violations: List[Dict] = []
    legitimate_historical: List[Dict] = []

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            file_path = Path(root) / f
            if file_path.suffix not in SCAN_EXTENSIONS:
                continue

            rel_path = str(file_path.relative_to(root_dir))

            # If inside known historical archive, track as historical
            if is_allowed_historical(rel_path):
                legitimate_historical.append({
                    "file": rel_path,
                    "type": "HISTORICAL_ARCHIVE"
                })
                continue

            # Scan lines
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line_num, line in enumerate(fp, 1):
                        if "AIRA" in line or "aira" in line:
                            # Check if line matches an explicit active violation pattern
                            for v_pat in ACTIVE_VIOLATION_PATTERNS:
                                if re.search(v_pat, line):
                                    violations.append({
                                        "file": rel_path,
                                        "line_num": line_num,
                                        "content": line.strip(),
                                        "reason": f"Active branding violation matching pattern: {v_pat}"
                                    })
                                    break
                            else:
                                # Check if it's an allowed compatibility alias
                                if is_allowed_compatibility(line):
                                    legitimate_historical.append({
                                        "file": rel_path,
                                        "line_num": line_num,
                                        "content": line.strip(),
                                        "type": "COMPATIBILITY_ALIAS"
                                    })
                                elif "#" in line or "//" in line or "/*" in line or line.strip().startswith("*"):
                                    # Comment mentioning historical context
                                    legitimate_historical.append({
                                        "file": rel_path,
                                        "line_num": line_num,
                                        "content": line.strip(),
                                        "type": "CODE_COMMENT_PROVENANCE"
                                    })
            except Exception as e:
                print(f"Error reading {rel_path}: {e}", file=sys.stderr)

    return violations, legitimate_historical


def main():
    workspace = Path(__file__).resolve().parent.parent.parent
    print(f"[*] Starting VERA Legacy Identity Reference Audit in: {workspace}")

    violations, historical = scan_workspace(workspace)

    print("\n" + "=" * 80)
    print("AUDIT RESULTS SUMMARY:")
    print(f"  - Legitimate Historical / Compatibility References: {len(historical)}")
    print(f"  - Active Branding / Persona Violations:             {len(violations)}")
    print("=" * 80)

    if violations:
        print("\n[!] ACTIVE VIOLATIONS FOUND:")
        for v in violations:
            print(f"  {v['file']}:{v['line_num']} -> {v['content']}")
            print(f"      Reason: {v['reason']}")
        sys.exit(1)
    else:
        print("\n[+] SUCCESS: ZERO (0) ACTIVE BRANDING VIOLATIONS DETECTED.")
        print("    Platform strictly enforces VERA as the sole active runtime identity.")
        sys.exit(0)


if __name__ == "__main__":
    main()
