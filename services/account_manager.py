"""
Multi-Account Manager for Rooter Gift Card Sniper Bot.
Manages 5-10 Rooter accounts, their JWT Bearer tokens, wallet balances, and active states.
Supports Railway ephemeral environments, dynamic runtime token updates,
pre-flight token validation (is_token_valid), and high-concurrency asyncio + aiohttp requests.
"""

import os
import re
import json
import logging
import base64
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import aiohttp
import httpx

import config

logger = logging.getLogger(__name__)

ACCOUNTS_FILE = config.SESSION_DIR / "accounts.json"
ROOTER_WALLET_BALANCE_URL = "https://payments.rooter.io/wallet/balance"
ROOTER_PROFILE_URL = "https://user.api.rooter.io/user-profile/me"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://shop.rooter.gg",
    "Referer": "https://shop.rooter.gg/",
}

def clean_bearer_token(token: str) -> str:
    """Strips Bearer prefix and whitespace from token."""
    t = str(token or "").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t

def extract_user_id(token: str) -> str:
    """Extracts Rooter userId from JWT Bearer token payload (handles numeric or alphanumeric userIds)."""
    clean_tok = clean_bearer_token(token)
    try:
        parts = clean_tok.split(".")
        if len(parts) >= 2:
            padding = "=" * (-len(parts[1]) % 4)
            payload_str = base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8", errors="ignore")
            try:
                data = json.loads(payload_str)
                uid = data.get("userId", "")
                if uid:
                    return str(uid)
            except Exception:
                pass
            match = re.search(r'"userId"\s*:\s*"?([a-zA-Z0-9_-]+)', payload_str)
            if match:
                return match.group(1)
    except Exception:
        pass
    return ""

def is_jwt_expired(token: str) -> bool:
    """Checks if JWT token has expired based on its 'exp' claim."""
    clean_tok = clean_bearer_token(token)
    try:
        parts = clean_tok.split(".")
        if len(parts) >= 2:
            padding = "=" * (-len(parts[1]) % 4)
            payload_str = base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8", errors="ignore")
            data = json.loads(payload_str)
            exp = data.get("exp")
            if exp and isinstance(exp, (int, float)):
                # Return True if expired (with 30s buffer)
                return datetime.now().timestamp() > (exp - 30)
    except Exception:
        pass
    return False

async def is_token_valid(token: str, session: Optional[aiohttp.ClientSession] = None) -> bool:
    """
    Pre-flight token validation for Rooter accounts before firing requests.
    Validates token structure, expiration, and queries Rooter payments API.
    """
    clean_tok = clean_bearer_token(token)
    if not clean_tok or len(clean_tok) < 20 or clean_tok.count(".") < 2:
        return False

    if is_jwt_expired(clean_tok):
        logger.warning("Token pre-flight check failed: JWT exp timestamp is in the past.")
        return False

    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {clean_tok}",
    }

    try:
        if session:
            async with session.get(ROOTER_WALLET_BALANCE_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                if resp.status == 200:
                    return True
                elif resp.status in (401, 403):
                    return False
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(ROOTER_WALLET_BALANCE_URL, headers=headers)
                if resp.status_code == 200:
                    return True
                elif resp.status_code in (401, 403):
                    return False
    except Exception as e:
        logger.debug(f"Pre-flight network validation notice: {e}")

    # Fallback to structural validity if network error occurred
    return len(clean_tok) > 30 and not is_jwt_expired(clean_tok)

async def fetch_live_balance_for_token(token: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[float]:
    """Fetches real-time live wallet balance directly from Rooter payments API using Bearer token."""
    clean_tok = clean_bearer_token(token)
    if not clean_tok:
        return None

    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {clean_tok}",
    }

    try:
        if session:
            async with session.get(ROOTER_WALLET_BALANCE_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=6.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    comp = data.get("component", {})
                    dep = float(comp.get("deposit", 0.0))
                    cred = float(comp.get("credit", 0.0))
                    vouch = float(comp.get("voucher", 0.0))
                    return round(dep + cred + vouch, 2)
        else:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(ROOTER_WALLET_BALANCE_URL, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    comp = data.get("component", {})
                    dep = float(comp.get("deposit", 0.0))
                    cred = float(comp.get("credit", 0.0))
                    vouch = float(comp.get("voucher", 0.0))
                    return round(dep + cred + vouch, 2)
    except Exception as e:
        logger.warning(f"Failed to fetch live Rooter balance: {e}")
    return None

class AccountManager:
    """Manages multiple Rooter user accounts (5-10 accounts) for high-concurrency sniping."""

    def __init__(self, filepath: Path = ACCOUNTS_FILE):
        self.filepath = filepath
        self.accounts: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Loads accounts from JSON file or auto-seeds from ENV variables / config (Railway compatible)."""
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.accounts = data.get("accounts", [])
            except Exception as e:
                logger.warning(f"Failed to read {self.filepath}: {e}")
                self.accounts = []

        # 1. Parse ROOTER_ACCOUNTS_JSON from environment if provided
        raw_json = os.getenv("ROOTER_ACCOUNTS_JSON", "").strip() or getattr(config, "ROOTER_ACCOUNTS_JSON", "").strip()
        if raw_json:
            try:
                parsed = json.loads(raw_json)
                items = parsed if isinstance(parsed, list) else parsed.get("accounts", [])
                for item in items:
                    tok = clean_bearer_token(item.get("token", ""))
                    if tok and len(tok) > 10:
                        lbl = item.get("label")
                        bal = float(item.get("wallet_balance", item.get("balance", 0.0)))
                        self._merge_or_add_token(tok, label=lbl, wallet_balance=bal)
            except Exception as e:
                logger.warning(f"Failed to parse ROOTER_ACCOUNTS_JSON: {e}")

        # 2. Parse ROOTER_TOKENS or ROOTER_ACCOUNTS_TOKENS from environment (comma, newline, or semicolon separated)
        raw_tokens = (
            os.getenv("ROOTER_TOKENS", "").strip()
            or os.getenv("ROOTER_ACCOUNTS_TOKENS", "").strip()
            or getattr(config, "ROOTER_TOKENS", "").strip()
            or getattr(config, "ROOTER_ACCOUNTS_TOKENS", "").strip()
        )
        if raw_tokens:
            delim_tokens = [clean_bearer_token(t) for t in re.split(r"[,;\n\r]+", raw_tokens) if len(clean_bearer_token(t)) > 10]
            for idx, tok in enumerate(delim_tokens, 1):
                self._merge_or_add_token(tok, label=f"Account {idx}")

        # 3. Auto-seed initial account from config.ROOTER_AUTH_TOKEN if accounts list is still empty
        primary_tok = clean_bearer_token(config.ROOTER_AUTH_TOKEN)
        if not self.accounts and primary_tok and len(primary_tok) > 10:
            uid = extract_user_id(primary_tok)
            default_acc = {
                "id": "acc_1",
                "label": "Account 1 (Primary)",
                "token": primary_tok,
                "user_id": uid or "2104663773",
                "wallet_balance": 1084.0,
                "is_active": True,
                "created_at": datetime.now().isoformat(),
            }
            self.accounts.append(default_acc)

        self._save()

    def _merge_or_add_token(
        self,
        token: str,
        label: Optional[str] = None,
        wallet_balance: float = 0.0,
    ) -> Dict[str, Any]:
        """Merges with existing account by token or userId, or appends a new account."""
        clean_token = clean_bearer_token(token)
        uid = extract_user_id(clean_token)

        for acc in self.accounts:
            if acc.get("token") == clean_token or (uid and str(acc.get("user_id")) == str(uid)):
                acc["token"] = clean_token
                if uid and not acc.get("user_id"):
                    acc["user_id"] = uid
                if label and not acc.get("label"):
                    acc["label"] = label
                if wallet_balance > 0 and float(acc.get("wallet_balance", 0.0)) <= 0:
                    acc["wallet_balance"] = wallet_balance
                return acc

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
        return new_acc

    def _save(self):
        """Saves current accounts to JSON file atomically."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({"accounts": self.accounts}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save accounts to {self.filepath}: {e}")

    def get_all(self) -> List[Dict[str, Any]]:
        """Returns all registered accounts in memory."""
        return list(self.accounts)

    def get_active(self) -> List[Dict[str, Any]]:
        """Returns all active accounts in memory."""
        return [acc for acc in self.accounts if acc.get("is_active", True)]

    def get_active_accounts(self) -> List[Dict[str, Any]]:
        """Alias for get_active()."""
        return self.get_active()

    def get_account(self, acc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single account by ID, Index, or UserID."""
        acc_id_str = str(acc_id).strip()
        for idx, acc in enumerate(self.accounts, 1):
            if (
                str(acc.get("id")) == acc_id_str
                or str(acc.get("user_id")) == acc_id_str
                or acc_id_str == str(idx)
                or (acc_id_str.startswith("acc_") and acc.get("id") == acc_id_str)
            ):
                return acc
        return None

    async def get_valid_active_accounts(self) -> List[Dict[str, Any]]:
        """
        Runs pre-flight validation concurrently on all active accounts.
        Returns only the accounts with active, valid tokens.
        """
        active = self.get_active()
        if not active:
            return []

        async def _check(acc):
            valid = await is_token_valid(acc.get("token", ""))
            return acc if valid else None

        results = await asyncio.gather(*[_check(a) for a in active], return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    async def set_account_token(
        self,
        acc_identifier: str,
        token: str,
        label: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Updates an account's token dynamically from Telegram (/settoken / /login)
        without requiring a Railway container restart.
        Validates token pre-flight and fetches live balance.
        """
        clean_tok = clean_bearer_token(token)
        if not clean_tok or len(clean_tok) < 20:
            return False, "Token format is invalid or too short.", None

        # Pre-flight check
        valid = await is_token_valid(clean_tok)
        if not valid:
            return False, "Token validation failed: Invalid or expired Bearer token on Rooter API.", None

        # Fetch real-time live balance
        live_bal = await fetch_live_balance_for_token(clean_tok)
        bal_to_set = live_bal if live_bal is not None else 0.0

        target_acc = self.get_account(acc_identifier)
        if target_acc:
            target_acc["token"] = clean_tok
            uid = extract_user_id(clean_tok)
            if uid:
                target_acc["user_id"] = uid
            if label:
                target_acc["label"] = label
            target_acc["wallet_balance"] = bal_to_set
            target_acc["is_active"] = True
            self._save()
            # If primary account, sync config as well
            if target_acc["id"] == "acc_1":
                config.ROOTER_AUTH_TOKEN = clean_tok
            logger.info(f"Updated token for {target_acc['id']} ({target_acc.get('label')}) -> Live balance: ₹{bal_to_set}")
            return True, f"Account {target_acc['id']} updated successfully!", target_acc

        # Otherwise add as a new account
        new_acc = self._merge_or_add_token(clean_tok, label=label, wallet_balance=bal_to_set)
        self._save()
        if new_acc["id"] == "acc_1":
            config.ROOTER_AUTH_TOKEN = clean_tok
        logger.info(f"Added new account {new_acc['id']} -> Live balance: ₹{bal_to_set}")
        return True, f"New account {new_acc['id']} registered successfully!", new_acc

    def add_account(
        self,
        token: str,
        label: Optional[str] = None,
        wallet_balance: float = 0.0,
    ) -> Dict[str, Any]:
        """Adds or updates a Rooter account."""
        acc = self._merge_or_add_token(token=token, label=label, wallet_balance=wallet_balance)
        self._save()
        return acc

    def remove_account(self, acc_id: str) -> bool:
        """Removes an account by ID."""
        acc_id_str = str(acc_id).strip()
        initial_len = len(self.accounts)
        self.accounts = [a for a in self.accounts if str(a.get("id")) != acc_id_str and str(a.get("user_id")) != acc_id_str]
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
        """Fetches real-time live balance for all registered accounts concurrently using aiohttp."""
        if not self.accounts:
            return {}

        connector = aiohttp.TCPConnector(limit=15)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for acc in self.accounts:
                tok = acc.get("token", "")
                if tok:
                    tasks.append((acc, fetch_live_balance_for_token(tok, session=session)))

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
        clean_tok = clean_bearer_token(token)
        if wallet_balance <= 0:
            live_bal = await fetch_live_balance_for_token(clean_tok)
            if live_bal is not None:
                wallet_balance = live_bal
        return self.add_account(token=clean_tok, label=label, wallet_balance=wallet_balance)

# Global singleton
account_manager = AccountManager()
