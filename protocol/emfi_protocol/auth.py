"""Small shared helpers for scoped bearer-token auth.

The apps intentionally keep auth opt-in for local lab development. When
``EMFI_AUTH_TOKENS`` is set, it contains JSON mapping token identifiers to
scope grants:

    {
      "plain-dev-token": {"name": "local-agent", "scopes": ["control:read"]},
      "sha256:<hex-digest>": ["campaign:*", "target:flash"]
    }

Plain tokens are convenient for local testing. Hash entries avoid storing the
actual token in process environment on production hosts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable


class AuthConfigError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    name: str
    scopes: frozenset[str]


def _normalize_scopes(value: Any) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
        raise AuthConfigError("token scopes must be a list of strings")
    return frozenset(value)


def load_token_config(env_name: str = "EMFI_AUTH_TOKENS") -> dict[str, Principal]:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthConfigError(f"{env_name} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AuthConfigError(f"{env_name} must be a JSON object")

    out: dict[str, Principal] = {}
    for token_id, grant in parsed.items():
        if not isinstance(token_id, str) or not token_id:
            raise AuthConfigError("token identifiers must be non-empty strings")
        if isinstance(grant, list):
            out[token_id] = Principal(name=token_id[:12], scopes=_normalize_scopes(grant))
        elif isinstance(grant, dict):
            scopes = _normalize_scopes(grant.get("scopes"))
            name = grant.get("name", token_id[:12])
            if not isinstance(name, str) or not name:
                raise AuthConfigError("token name must be a non-empty string")
            out[token_id] = Principal(name=name, scopes=scopes)
        else:
            raise AuthConfigError("token grants must be a scope list or object")
    return out


def authenticate_bearer(token: str, config: dict[str, Principal]) -> Principal | None:
    digest_id = "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()
    for token_id, principal in config.items():
        if token_id.startswith("sha256:"):
            if hmac.compare_digest(token_id, digest_id):
                return principal
        elif hmac.compare_digest(token_id, token):
            return principal
    return None


def has_scope(principal: Principal, required: str) -> bool:
    if "*" in principal.scopes or required in principal.scopes:
        return True
    prefix = required.split(":", 1)[0] + ":*"
    return prefix in principal.scopes


def missing_scope(principal: Principal, required: str | Iterable[str]) -> str | None:
    if isinstance(required, str):
        return None if has_scope(principal, required) else required
    for scope in required:
        if has_scope(principal, scope):
            return None
    return next(iter(required), "")
