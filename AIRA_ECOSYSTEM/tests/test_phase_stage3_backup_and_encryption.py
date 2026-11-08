"""
AIRA OS — Stage 3 Test Suite: Secret Security, Vault Encryption & Database Safety (REC-12, REC-26).

Validates:
1. AES-256-GCM SecretVault encryption, decryption, and authentication tag tamper detection.
2. SecretVault idempotency and transparent legacy migration (Fernet & base64).
3. SecretVault master key rotation policy.
4. Model Registry API key encryption at rest (never stored in plaintext).
5. Device inventory credential encryption at rest & removal of insecure SSH_PASSWORD fallback.
6. MFA TOTP secret seed encryption at rest in operational_users.
7. SQLite Online Backup API (sqlite3.Connection.backup) with page counts & SHA-256 sidecars.
8. Online backup resilience during active concurrent writes (zero corruption, WAL safe).
9. Safe database restore with SHA-256 verification and PRAGMA integrity_check.
10. scripts/backup_restore.py CLI commands (backup, verify, list, restore).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import pytest

from core.database.backup_service import (
    check_database_integrity,
    compute_file_sha256,
    create_online_backup,
    list_backups,
    restore_database,
)
from core.security.encryption import (
    MAGIC_PREFIX,
    SecretVault,
    VaultDecryptionError,
    decrypt_secret,
    encrypt_secret,
    get_secret_vault,
)
from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import IdentityManager
from core.topology_db import topology_transaction


# ===========================================================================
# 1. SECRET VAULT & AES-256-GCM ENCRYPTION
# ===========================================================================

def test_secret_vault_aes_gcm_encrypt_decrypt():
    """Validates AES-256-GCM encryption and exact plaintext recovery."""
    vault = SecretVault(master_key="MySuperSecureMasterPassphrase123!")
    secret = "SuperSecretRouterPassword_P@ssw0rd99!"

    encrypted = vault.encrypt(secret)
    assert encrypted is not None
    assert encrypted != secret
    assert encrypted.startswith(MAGIC_PREFIX)

    decrypted = vault.decrypt(encrypted)
    assert decrypted == secret


def test_secret_vault_tamper_detection():
    """Tampering with ciphertext or authentication tag raises VaultDecryptionError."""
    vault = SecretVault(master_key="TestMasterKey123!")
    encrypted = vault.encrypt("SensitiveData")

    # Tamper with the ciphertext body
    parts = encrypted.split("$")
    corrupted_ct = parts[2][:-4] + "AAAA"
    tampered = f"{parts[0]}${parts[1]}${corrupted_ct}"

    with pytest.raises(VaultDecryptionError):
        vault.decrypt(tampered)


def test_secret_vault_idempotency():
    """Encrypting an already encrypted payload returns the input unchanged."""
    vault = SecretVault(master_key="TestMasterKey123!")
    secret = "ApiKey_AIzaSyA_Example123"

    enc1 = vault.encrypt(secret)
    enc2 = vault.encrypt(enc1)
    assert enc1 == enc2


def test_secret_vault_legacy_migration():
    """Vault transparently decrypts legacy Fernet (enc:...) and base64 (b64:...) payloads."""
    from cryptography.fernet import Fernet
    raw_key = b"12345678901234567890123456789012"
    f_key = Fernet.generate_key()
    fernet = Fernet(f_key)

    plain = "OldLegacySecret"
    legacy_enc = "enc:" + fernet.encrypt(plain.encode("utf-8")).decode("ascii")
    legacy_b64 = "b64:T2xkTGVnYWN5U2VjcmV0"

    # Vault initialized with matching legacy keyfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        key_file = Path(tmp_dir) / ".master.key"
        legacy_key_file = Path(tmp_dir) / ".inventory.key"
        legacy_key_file.write_bytes(f_key)

        vault = SecretVault(master_key=raw_key, key_file_path=key_file)
        assert vault.decrypt(legacy_enc) == plain
        assert vault.decrypt(legacy_b64) == plain


def test_secret_vault_key_rotation():
    """Rotates an encrypted secret to a new master key."""
    old_key = "OldMasterPassphrase123!"
    new_key = "NewMasterPassphrase456!"

    vault_old = SecretVault(master_key=old_key)
    secret = "CriticalInfrastructurePassword"
    old_ciphertext = vault_old.encrypt(secret)

    # Rotate ciphertext
    new_ciphertext = vault_old.rotate_key(new_master_key=new_key, ciphertext=old_ciphertext)
    assert new_ciphertext != old_ciphertext

    vault_new = SecretVault(master_key=new_key)
    assert vault_new.decrypt(new_ciphertext) == secret

    # Old vault cannot decrypt new ciphertext
    with pytest.raises(VaultDecryptionError):
        vault_old.decrypt(new_ciphertext)


# ===========================================================================
# 2. MODEL REGISTRY API KEY ENCRYPTION
# ===========================================================================

def test_model_registry_api_key_encryption():
    """API keys in model_registry are encrypted at rest and masked in public views."""
    from core import model_registry

    raw_api_key = "sk-proj-SecretApiKey1234567890"
    model_name = f"test-model-sec-{int(time.time() * 1000)}"

    try:
        res = model_registry.create_model(
            nickname=model_name,
            provider="openrouter",
            model_id="nvidia/nemotron-3.5-lightning:free",
            api_key=raw_api_key,
        )
        assert res["success"] is True

        # 1. Public list / get masks API key
        model_masked = model_registry.get_model(model_name, mask_api_key=True)
        assert "api_key" not in model_masked
        assert model_masked["has_api_key"] is True

        # 2. Internal get decrypts API key
        model_internal = model_registry.get_model(model_name, mask_api_key=False)
        assert model_internal["api_key"] == raw_api_key

        # 3. Direct SQLite query proves key is stored encrypted at rest
        with sqlite3.connect(model_registry.DB_FILE) as conn:
            row = conn.execute(
                "SELECT api_key FROM model_registry WHERE nickname = ?",
                (model_name,),
            ).fetchone()
            assert row is not None
            stored_val = row[0]
            assert stored_val != raw_api_key
            assert stored_val.startswith(MAGIC_PREFIX)
    finally:
        model_registry.delete_model(model_name)


# ===========================================================================
# 3. INVENTORY STORE SECRET ENCRYPTION & ZERO SSH_PASSWORD FALLBACK
# ===========================================================================

def test_inventory_store_secret_encryption_and_no_fallback():
    """Device passwords are encrypted at rest; resolve_ssh does not fallback to SSH_PASSWORD."""
    from core.inventory_store import InventoryStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_inventory.db"
        inv = InventoryStore(db_path=db_path)

        dev_name = "core-router-01"
        secret_pw = "SecureRouterPass99!"

        # Create device with credentials
        res = inv.create_device(
            name=dev_name,
            host="192.168.88.1",
            port=22,
            username="admin",
            new_credentials=[{"name": "core-ssh", "type": "ssh_password", "secret": secret_pw}],
        )
        assert res["success"] is True

        # Direct database inspection confirms encryption at rest
        with sqlite3.connect(db_path) as conn:
            cred_row = conn.execute("SELECT secret_enc FROM credentials WHERE name = 'core-ssh'").fetchone()
            assert cred_row is not None
            assert cred_row[0] != secret_pw

        # resolve_ssh returns decrypted password
        resolved = inv.resolve_ssh(dev_name)
        assert resolved["success"] is True
        assert resolved["password"] == secret_pw

        # Negative test: Device without credential must NOT fallback to os.getenv("SSH_PASSWORD")
        inv.create_device(name="ad-hoc-untrusted", host="10.0.0.99", port=22, username="admin")
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("SSH_PASSWORD", "LeakedMasterPassword123!")
            adhoc_resolved = inv.resolve_ssh("ad-hoc-untrusted")
            assert adhoc_resolved["password"] is None
            assert adhoc_resolved["has_ssh_credential"] is False


# ===========================================================================
# 4. MFA SECRET ENCRYPTION AT REST
# ===========================================================================

def test_mfa_secret_encryption_in_operational_users():
    """TOTP seed secrets in operational_users are encrypted at rest."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "mfa_test.db"
        ensure_tenant_schema(db_path)

        id_mgr = IdentityManager(db_path)
        u = id_mgr.create_user(
            username="mfa_user",
            email="mfa@example.com",
            password="StrongPassword123!",
            is_internal=True,
        )

        from core.security.mfa import generate_totp_secret, compute_totp_code
        plain_secret = generate_totp_secret()
        code = compute_totp_code(plain_secret)

        # Enable MFA
        assert id_mgr.verify_and_enable_mfa(u.user_id, plain_secret, code) is True

        # Verify direct DB storage is encrypted
        with topology_transaction(db_path, write=False) as conn:
            row = conn.execute(
                "SELECT mfa_secret, mfa_enabled FROM operational_users WHERE user_id = ?",
                (u.user_id,),
            ).fetchone()
            assert row[1] == 1
            stored_secret = row[0]
            assert stored_secret != plain_secret
            assert stored_secret.startswith(MAGIC_PREFIX)

        # Authentication with TOTP succeeds by transparently decrypting
        auth_res = id_mgr.authenticate_user_detailed(
            username_or_email="mfa_user",
            password="StrongPassword123!",
            totp_code=compute_totp_code(plain_secret),
        )
        assert auth_res["success"] is True


# ===========================================================================
# 5. SQLITE ONLINE BACKUP API & INTEGRITY
# ===========================================================================

def test_sqlite_online_backup_api():
    """Online backup generates valid database copy, computes SHA-256, and writes sidecar."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        src_db = Path(tmp_dir) / "source_topology.db"
        ensure_tenant_schema(src_db)

        # Populate sample tables
        id_mgr = IdentityManager(src_db)
        id_mgr.create_user(
            username="backup_test_user",
            email="backup@example.com",
            password="Password123!",
            is_internal=True,
        )

        backup_dir = Path(tmp_dir) / "backups"
        meta = create_online_backup(src_db, backup_dir=backup_dir)

        assert Path(meta.backup_path).exists()
        assert meta.size_bytes > 0
        assert meta.integrity_ok is True
        assert meta.foreign_keys_ok is True
        assert "operational_users" in meta.table_counts
        assert meta.table_counts["operational_users"] >= 1

        # Verify sidecar metadata file
        meta_file = Path(meta.backup_path).with_suffix(".db.meta.json")
        assert meta_file.exists()
        meta_json = json.loads(meta_file.read_text(encoding="utf-8"))
        assert meta_json["sha256"] == meta.sha256


def test_sqlite_backup_during_concurrent_writes():
    """Online backup executes safely while concurrent transactions mutate the source database."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        src_db = Path(tmp_dir) / "live_wal.db"
        ensure_tenant_schema(src_db)

        # Set WAL mode
        with sqlite3.connect(src_db) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")

        stop_event = threading.Event()
        writer_errors: list[Exception] = []

        def writer_worker():
            idx = 0
            while not stop_event.is_set():
                try:
                    with topology_transaction(src_db, write=True) as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO operational_tenants (tenant_id, name, slug, status, config_json, created_at, updated_at) "
                            "VALUES (?, ?, ?, 'ACTIVE', '{}', '2026-01-01', '2026-01-01')",
                            (f"tenant_live_{idx}", f"Live Tenant {idx}", f"live-{idx}"),
                        )
                    idx += 1
                    time.sleep(0.005)
                except Exception as e:
                    writer_errors.append(e)

        thread = threading.Thread(target=writer_worker, daemon=True)
        thread.start()

        time.sleep(0.05)  # Let writer start

        try:
            backup_dir = Path(tmp_dir) / "backups"
            meta = create_online_backup(src_db, backup_dir=backup_dir)
            assert meta.integrity_ok is True
        finally:
            stop_event.set()
            thread.join(timeout=2.0)

        assert len(writer_errors) == 0, f"Writer errors during backup: {writer_errors}"
        integrity_ok, fk_ok, msg = check_database_integrity(meta.backup_path)
        assert integrity_ok is True
        assert fk_ok is True


# ===========================================================================
# 6. DATABASE RESTORE & VERIFICATION
# ===========================================================================

def test_database_restore_and_verification():
    """Restores database from backup, verifying SHA-256 and data completeness."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        src_db = Path(tmp_dir) / "original.db"
        ensure_tenant_schema(src_db)

        id_mgr = IdentityManager(src_db)
        u = id_mgr.create_user("restore_user", "restore@example.com", "Password123!", is_internal=True)

        backup_dir = Path(tmp_dir) / "backups"
        meta = create_online_backup(src_db, backup_dir=backup_dir)

        # Restore to new target path
        target_restored = Path(tmp_dir) / "restored.db"
        res = restore_database(meta.backup_path, target_restored, verify_sha256=True)

        assert res["success"] is True
        assert res["integrity_ok"] is True
        assert target_restored.exists()

        # Verify restored contents
        restored_mgr = IdentityManager(target_restored)
        restored_u = restored_mgr.get_user_by_username("restore_user")
        assert restored_u is not None
        assert restored_u.user_id == u.user_id


# ===========================================================================
# 7. CLI BACKUP/RESTORE TOOLING (scripts/backup_restore.py)
# ===========================================================================

def test_backup_restore_cli_tool():
    """Runs backup_restore.py CLI subcommands end-to-end."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "cli_test.db"
        ensure_tenant_schema(db_path)

        backups_dir = Path(tmp_dir) / "cli_backups"
        cli_path = Path("AIRA_ECOSYSTEM/scripts/backup_restore.py").resolve()
        if not cli_path.exists():
            cli_path = Path("scripts/backup_restore.py").resolve()

        # 1. CLI backup
        cmd_bak = [
            sys.executable, str(cli_path), "backup",
            "--source", str(db_path),
            "--dir", str(backups_dir),
        ]
        p_bak = subprocess.run(cmd_bak, capture_output=True, text=True)
        assert p_bak.returncode == 0
        assert "BACKUP SUCCESSFUL" in p_bak.stdout

        # 2. CLI list
        cmd_list = [sys.executable, str(cli_path), "list", "--dir", str(backups_dir)]
        p_list = subprocess.run(cmd_list, capture_output=True, text=True)
        assert p_list.returncode == 0
        assert "Found 1 backups" in p_list.stdout

        # 3. CLI verify
        backup_files = list(backups_dir.glob("*.db"))
        assert len(backup_files) == 1
        bak_file = backup_files[0]

        cmd_verify = [sys.executable, str(cli_path), "verify", "--file", str(bak_file)]
        p_ver = subprocess.run(cmd_verify, capture_output=True, text=True)
        assert p_ver.returncode == 0
        assert "Integrity:    PASSED" in p_ver.stdout

        # 4. CLI restore
        restore_target = Path(tmp_dir) / "cli_restored.db"
        cmd_res = [
            sys.executable, str(cli_path), "restore",
            "--file", str(bak_file),
            "--target", str(restore_target),
        ]
        p_res = subprocess.run(cmd_res, capture_output=True, text=True)
        assert p_res.returncode == 0
        assert "RESTORE SUCCESSFUL" in p_res.stdout
        assert restore_target.exists()
