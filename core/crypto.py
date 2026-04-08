"""
KAAL Crypto — AES-256-GCM end-to-end encryption for agent payloads.
Uses per-agent keys derived from a master secret via HKDF.
"""
import os
import base64
import hashlib
import hmac
import json
import logging
from typing import Optional, Dict, Any, Tuple

log = logging.getLogger("kaal.crypto")

# Try to import cryptography library; fall back to basic mode if unavailable
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    log.warning("cryptography library not installed — encryption disabled. "
                "Install with: pip install cryptography")


class PayloadCrypto:
    """AES-256-GCM payload encryption with per-agent key derivation."""

    def __init__(self, master_key: Optional[str] = None):
        self.enabled = False
        self.master_key: Optional[bytes] = None
        self._agent_keys: Dict[str, bytes] = {}  # cache derived keys

        if master_key and HAS_CRYPTO:
            # Derive a 32-byte master from the config string
            self.master_key = hashlib.sha256(master_key.encode()).digest()
            self.enabled = True
            log.info("Payload encryption enabled (AES-256-GCM)")
        elif master_key and not HAS_CRYPTO:
            log.error("Master key set but 'cryptography' package not installed!")

    def _derive_agent_key(self, agent_id: str) -> bytes:
        """Derive a unique 256-bit key for an agent using HKDF."""
        if agent_id in self._agent_keys:
            return self._agent_keys[agent_id]

        if not self.master_key:
            raise RuntimeError("No master key configured")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"kaal-agent-{agent_id}".encode(),
        )
        key = hkdf.derive(self.master_key)
        self._agent_keys[agent_id] = key
        return key

    def encrypt(self, agent_id: str, plaintext: str) -> Dict[str, str]:
        """Encrypt a plaintext string for a specific agent.

        Returns dict with {iv, ct, tag} all base64-encoded.
        """
        if not self.enabled:
            raise RuntimeError("Encryption not enabled")

        key = self._derive_agent_key(agent_id)
        aesgcm = AESGCM(key)

        # 96-bit random nonce (recommended for GCM)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # GCM appends 16-byte tag to ciphertext; split them
        ciphertext = ct[:-16]
        tag = ct[-16:]

        return {
            "iv": base64.b64encode(nonce).decode(),
            "ct": base64.b64encode(ciphertext).decode(),
            "tag": base64.b64encode(tag).decode(),
        }

    def decrypt(self, agent_id: str, encrypted: Dict[str, str]) -> str:
        """Decrypt an encrypted payload from a specific agent.

        encrypted must have {iv, ct, tag} (base64-encoded).
        """
        if not self.enabled:
            raise RuntimeError("Encryption not enabled")

        key = self._derive_agent_key(agent_id)
        aesgcm = AESGCM(key)

        nonce = base64.b64decode(encrypted["iv"])
        ciphertext = base64.b64decode(encrypted["ct"])
        tag = base64.b64decode(encrypted["tag"])

        # GCM expects ciphertext + tag concatenated
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
        return plaintext.decode("utf-8")

    def encrypt_payload(self, agent_id: str, payload: Any) -> Dict[str, Any]:
        """Encrypt a payload object (serializes to JSON first)."""
        plaintext = json.dumps(payload) if not isinstance(payload, str) else payload
        enc = self.encrypt(agent_id, plaintext)
        return {"encrypted": True, **enc}

    def decrypt_payload(self, agent_id: str,
                        payload: Dict[str, Any]) -> Any:
        """Decrypt an encrypted payload, returns parsed JSON or string."""
        plaintext = self.decrypt(agent_id, payload)
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, ValueError):
            return plaintext

    def is_encrypted(self, payload: Any) -> bool:
        """Check if a payload dict contains encryption markers."""
        if isinstance(payload, dict):
            return payload.get("encrypted") is True or "iv" in payload
        return False


# Singleton — initialized by server at startup
crypto = PayloadCrypto()
