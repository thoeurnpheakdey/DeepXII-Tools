#!/usr/bin/env python3
"""Offline activation-key management for DeepXII Tools administrators."""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.license_manager import create_activation_code


ROOT = Path(__file__).resolve().parent
PRIVATE_KEY = ROOT / "activation_keys" / "license_private_key.pem"
PUBLIC_KEY = ROOT / "resources" / "license_public_key.pem"
MACHINE_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def initialize_keys(force: bool = False) -> int:
    if (PRIVATE_KEY.exists() or PUBLIC_KEY.exists()) and not force:
        print("Activation keys already exist. Use --force only when intentionally replacing all keys.")
        return 1
    PRIVATE_KEY.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_KEY.parent.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    PRIVATE_KEY.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PUBLIC_KEY.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Private key: {PRIVATE_KEY}")
    print(f"Public key:  {PUBLIC_KEY}")
    print("Back up the private key securely. Never distribute or commit it.")
    return 0


def generate_code(machine_id: str, license_id: str | None, plan: str) -> int:
    machine_id = machine_id.strip()
    if not MACHINE_ID_PATTERN.fullmatch(machine_id):
        print("Error: Machine ID must contain exactly 32 hexadecimal characters.", file=sys.stderr)
        return 2
    if not PRIVATE_KEY.exists():
        print("Error: run 'python activate.py init' first.", file=sys.stderr)
        return 2
    value = create_activation_code(
        PRIVATE_KEY,
        machine_id,
        license_id or uuid.uuid4().hex,
        plan,
    )
    print(value)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepXII offline activation manager")
    commands = parser.add_subparsers(dest="command")
    init = commands.add_parser("init", help="create the activation signing key pair")
    init.add_argument("--force", action="store_true", help="replace the existing key pair")
    generate = commands.add_parser("generate", help="generate a code for one Machine ID")
    generate.add_argument("machine_id", help="32-character Machine ID shown by the app")
    generate.add_argument("--license-id", help="optional license identifier")
    generate.add_argument("--plan", default="lifetime", help="license plan label")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command is None:
        if not PRIVATE_KEY.exists():
            if PUBLIC_KEY.exists():
                print(
                    f"Error: private key is missing: {PRIVATE_KEY}\n"
                    "Restore its backup before generating more Activation Codes.",
                    file=sys.stderr,
                )
                return 2
            if initialize_keys() != 0:
                return 2
            print()
        try:
            machine_id = input("Enter User Machine ID: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1
        if not machine_id:
            print("Error: Machine ID is required.", file=sys.stderr)
            return 2
        print("\nActivation Code:")
        return generate_code(machine_id, None, "lifetime")
    if args.command == "init":
        return initialize_keys(args.force)
    return generate_code(args.machine_id, args.license_id, args.plan)


if __name__ == "__main__":
    raise SystemExit(main())
