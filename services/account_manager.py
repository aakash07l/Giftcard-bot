"""
Multi-Account Manager for Rooter Gift Card Sniper Bot.
Manages 5-10 Rooter accounts, their JWT Bearer tokens, wallet balances, and active states.
Persists data to sessions/accounts.json.
"""

import json
import logging
import base64
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx

import config

logger = logging.getLogger(__name__)

ACCOUNTS_FILE = config.SESSION_DIR / "accounts.json"
ROOTER_WALLET_BALANCE_URL = "https://payments.rooter.io/wallet/balance"

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

async def fetch_live_balance_for_token(token: str) -> Optional[float]:
    """Fetches real-time live wallet balance directly from Rooter payments API using Bearer token."""
    clean_tok = token.strip()
    if clean_tok.lower().startswith("bearer "):
        clean_tok = clean_tok[7:].strip()
    if not clean_tok:
        return None

    headers = {
        "Authorization": f"Bearer {clean_tok}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(ROOTER_WALLET_BALANCE_URL, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                comp = data.get("component", {})
                dep = float(comp.get("deposit", 0.0))
                cred = float(comp.get("credit", 0.0))
                vouch = float(comp.get("voucher", 0.0))
                total = round(dep + cred + vouch, 2)
                logger.info(f"Rooter live balance fetched: ₹{total:.2f} (dep={dep}, cred={cred}, vouch={vouch})")
                return total
            else:
                logger.warning(f"Rooter balance API returned status {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        logger.warning(f"Failed to fetch live Rooter balance: {e}")
    return None

class AccountManager:
    """Manages multiple Rooter user accounts for concurrent restock sniping."""

    def __init__(self, filepath: Path = ACCOUNTS_FILE):
        self.filepath = filepath
        self.accounts: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Loads accounts with Railway Environment Variables having Master Authority."""
        # 1. Read existing cached accounts from file if present
        cached_map = {}
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for a in data.get("accounts", []):
                        tok = a.get("token")
                        uid = a.get("user_id") or extract_user_id(tok)
                        if uid:
                            cached_map[str(uid)] = a
                        if tok:
                            cached_map[tok] = a
            except Exception as e:
                logger.warning(f"Failed to read {self.filepath}: {e}")

        # 2. Check Railway Environment Variables (ROOTER_TOKEN_1 ... 30, ROOTER_AUTH_TOKENS)
        env_tokens = getattr(config, "ROOTER_AUTH_TOKENS", [])
        if not env_tokens and getattr(config, "ROOTER_AUTH_TOKEN", ""):
            single = config.ROOTER_AUTH_TOKEN.strip()
            if len(single) > 20:
                env_tokens = [single]

        if env_tokens:
            # MASTER AUTHORITY: Railway ENV variables define the active account roster!
            new_accounts = []
            seen_tokens = set()
            for idx, tok in enumerate(env_tokens, start=1):
                clean_tok = tok.strip()
                if clean_tok.lower().startswith("bearer "):
                    clean_tok = clean_tok[7:].strip()
                if clean_tok in seen_tokens:
                    continue
                seen_tokens.add(clean_tok)

                uid = extract_user_id(clean_tok)
                # Check if we have cached balance/label from previous run
                cached = cached_map.get(str(uid)) or cached_map.get(clean_tok) or {}
                cached_bal = float(cached.get("wallet_balance", 0.0))
                cached_label = cached.get("label") or f"Account {idx}"

                acc_obj = {
                    "id": f"acc_{idx}",
                    "label": cached_label,
                    "token": clean_tok,
                    "user_id": uid,
                    "wallet_balance": cached_bal,
                    "is_active": True,
                    "created_at": cached.get("created_at") or datetime.now().isoformat(),
                }
                new_accounts.append(acc_obj)

            self.accounts = new_accounts
            self._save()
            logger.info(f"Loaded {len(self.accounts)} account(s) from Railway Environment Variables.")
            return

        # 3. Fallback: If no ENV tokens set, use cached accounts from file
        if cached_map:
            unique_accs = {}
            for a in cached_map.values():
                aid = a.get("id") or a.get("token")
                unique_accs[aid] = a
            self.accounts = list(unique_accs.values())
        else:
            self.accounts = []

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

    async def refresh_account_balance(self, acc_id: str) -> Optional[float]:
        """Fetches live balance for an account and updates it in memory and on disk."""
        acc = self.get_account(acc_id)
        if not acc or not acc.get("token"):
            return None
        live_bal = await fetch_live_balance_for_token(acc["token"])
        if live_bal is not None:
            acc["wallet_balance"] = live_bal
            self._save()
            return live_bal
        return float(acc.get("wallet_balance", 0.0))

    async def sync_all_balances(self) -> Dict[str, float]:
        """Fetches real-time live balance for all registered accounts concurrently."""
        tasks = []
        for acc in self.accounts:
            tok = acc.get("token", "")
            if tok:
                tasks.append((acc, fetch_live_balance_for_token(tok)))

        if not tasks:
            return {}

        results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        updated = {}
        changed = False
        for (acc, _), res in zip(tasks, results):
            if isinstance(res, (int, float)):
                acc["wallet_balance"] = float(res)
                updated[acc["id"]] = float(res)
                changed = True
            else:
                updated[acc["id"]] = float(acc.get("wallet_balance", 0.0))

        if changed:
            self._save()
        return updated

    async def add_account_async(
        self,
        token: str,
        label: Optional[str] = None,
        wallet_balance: float = 0.0,
    ) -> Dict[str, Any]:
        """Adds a new account and immediately fetches its live wallet balance."""
        clean_tok = token.strip()
        if clean_tok.lower().startswith("bearer "):
            clean_tok = clean_tok[7:].strip()

        # If wallet_balance wasn't passed or is 0, fetch live balance immediately from Rooter API
        if wallet_balance <= 0:
            live_bal = await fetch_live_balance_for_token(clean_tok)
            if live_bal is not None:
                wallet_balance = live_bal

        return self.add_account(token=clean_tok, label=label, wallet_balance=wallet_balance)

# Global singleton
account_manager = AccountManager()

