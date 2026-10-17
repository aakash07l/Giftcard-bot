"""
Multi-Account Manager for Rooter Gift Card Sniper Bot.
Manages 5-10 Rooter accounts, their JWT Bearer tokens, wallet balances, and active states.
Persists data to sessions/accounts.json.
"""

import json
import logging
import base64
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

import config

logger = logging.getLogger(__name__)

ACCOUNTS_FILE = config.SESSION_DIR / "accounts.json"

def extract_user_id(token: str) -> int:
    """Extracts Rooter userId from JWT Bearer token payload."""
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            padding = "=" * (-len(parts[1]) % 4)
            payload_str = base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8")
            data = json.loads(payload_str)
            return int(data.get("userId", 0))
    except Exception:
        pass
    return 0

class AccountManager:
    """Manages multiple Rooter user accounts for concurrent restock sniping."""

    def __init__(self, filepath: Path = ACCOUNTS_FILE):
        self.filepath = filepath
        self.accounts: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Loads accounts from JSON file or auto-seeds from config."""
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.accounts = data.get("accounts", [])
            except Exception as e:
                logger.warning(f"Failed to read {self.filepath}: {e}")
                self.accounts = []

        # Auto-seed initial account from config if accounts list is empty
        if not self.accounts and config.ROOTER_AUTH_TOKEN and len(config.ROOTER_AUTH_TOKEN) > 10:
            uid = extract_user_id(config.ROOTER_AUTH_TOKEN)
            default_acc = {
                "id": "acc_1",
                "label": "Account 1 (Primary)",
                "token": config.ROOTER_AUTH_TOKEN,
                "user_id": uid or 2104663773,
                "wallet_balance": 1084.0,
                "is_active": True,
                "created_at": datetime.now().isoformat(),
            }
            self.accounts.append(default_acc)
            self._save()

    def _save(self):
        """Saves current accounts to JSON file atomically."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({"accounts": self.accounts}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save accounts to {self.filepath}: {e}")

    def get_all(self) -> List[Dict[str, Any]]:
        """Returns all registered accounts."""
        return list(self.accounts)

    def get_active(self) -> List[Dict[str, Any]]:
        """Returns all active accounts."""
        return [acc for acc in self.accounts if acc.get("is_active", True)]

    def get_account(self, acc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single account by ID or UserID."""
        for acc in self.accounts:
            if acc.get("id") == acc_id or str(acc.get("user_id")) == str(acc_id):
                return acc
        return None

    def add_account(
        self,
        token: str,
        label: Optional[str] = None,
        wallet_balance: float = 0.0,
    ) -> Dict[str, Any]:
        """Adds a new Rooter account. Replaces if same userId already exists."""
        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        uid = extract_user_id(clean_token)

        # Check if already exists by token or userId
        for acc in self.accounts:
            if acc.get("token") == clean_token or (uid and acc.get("user_id") == uid):
                acc["token"] = clean_token
                if label:
                    acc["label"] = label
                if wallet_balance > 0:
                    acc["wallet_balance"] = wallet_balance
                acc["is_active"] = True
                self._save()
                logger.info(f"Updated existing account {acc['id']} (UID: {uid})")
                return acc

        # Determine next ID
        existing_indices = []
        for a in self.accounts:
            aid = a.get("id", "")
            if aid.startswith("acc_"):
                try:
                    existing_indices.append(int(aid[4:]))
                except ValueError:
                    pass
        next_idx = max(existing_indices, default=0) + 1
        new_id = f"acc_{next_idx}"

        new_label = label or f"Account {next_idx}"
        new_acc = {
            "id": new_id,
            "label": new_label,
            "token": clean_token,
            "user_id": uid,
            "wallet_balance": float(wallet_balance),
            "is_active": True,
            "created_at": datetime.now().isoformat(),
        }

        self.accounts.append(new_acc)
        self._save()
        logger.info(f"Added new account {new_id} ({new_label}, UID: {uid}, Balance: ₹{wallet_balance})")
        return new_acc

    def remove_account(self, acc_id: str) -> bool:
        """Removes an account by ID."""
        initial_len = len(self.accounts)
        self.accounts = [a for a in self.accounts if a.get("id") != acc_id and str(a.get("user_id")) != str(acc_id)]
        if len(self.accounts) < initial_len:
            self._save()
            logger.info(f"Removed account {acc_id}")
            return True
        return False

    def update_balance(self, acc_id: str, balance: float) -> bool:
        """Updates the wallet balance of an account."""
        acc = self.get_account(acc_id)
        if acc:
            acc["wallet_balance"] = max(0.0, float(balance))
            self._save()
            logger.info(f"Updated balance for {acc['id']} -> ₹{acc['wallet_balance']:,}")
            return True
        return False

    def deduct_balance(self, acc_id: str, amount: float) -> bool:
        """Deducts purchased amount from account's tracked wallet balance."""
        acc = self.get_account(acc_id)
        if acc:
            acc["wallet_balance"] = max(0.0, float(acc.get("wallet_balance", 0.0) - amount))
            self._save()
            return True
        return False

    def toggle_active(self, acc_id: str) -> Optional[bool]:
        """Toggles active/paused status of an account."""
        acc = self.get_account(acc_id)
        if acc:
            acc["is_active"] = not acc.get("is_active", True)
            self._save()
            return acc["is_active"]
        return None

    def get_total_balance(self) -> float:
        """Returns the sum of wallet balances across all active accounts."""
        return sum(float(a.get("wallet_balance", 0.0)) for a in self.get_active())

# Global singleton
account_manager = AccountManager()
