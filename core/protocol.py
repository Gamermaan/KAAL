"""
KAAL Universal Protocol V4 — Constants and defaults.
"""
from core.models import MessageType

PROTOCOL_VERSION = "1.0"

# Re-export message type strings for backward compat
MESSAGE_TYPES = {t.name: t.value for t in MessageType}

DEFAULT_FLAGS = {
    "ack_required": False,
    "priority": 0,
    "retry": 0,
    "control": False,
    "compression": None,
    "encryption": None,
    "ttl": None,
}

# Capabilities that agents can advertise during registration
DEFAULT_CAPABILITIES = [
    "exec", "ls", "cd", "download", "upload", "screenshot",
    "webcam", "keylog", "revshell", "sysinfo", "process_list",
    "persist", "self_destruct",
]
