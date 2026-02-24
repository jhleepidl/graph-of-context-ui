from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel

class ThreadCreate(BaseModel):
    title: Optional[str] = None

class MessageCreate(BaseModel):
    role: str  # user | assistant
    text: str
    reply_to: Optional[str] = None

class ResourceNodeCreate(BaseModel):
    name: str
    summary: Optional[str] = None
    resource_kind: str = "file"  # file | link | image | table | doc | code | other
    mime_type: Optional[str] = None
    uri: Optional[str] = None
    source: Literal["chatgpt_upload", "manual", "link", "unknown"] = "chatgpt_upload"
    attach_to: Optional[str] = None
    context_set_id: Optional[str] = None
    auto_activate: bool = True

class ContextSetCreate(BaseModel):
    thread_id: str
    name: str = "default"

class ActivateNodes(BaseModel):
    node_ids: List[str]

class FoldCreate(BaseModel):
    thread_id: str
    member_node_ids: List[str]
    title: Optional[str] = None

class RunCreate(BaseModel):
    context_set_id: str
    user_message: str

class SearchResponseItem(BaseModel):
    node_id: str
    score: float
    node_type: str
    snippet: str


class NodePositionUpdate(BaseModel):
    id: str
    x: float
    y: float


class NodeLayoutUpdate(BaseModel):
    positions: List[NodePositionUpdate]


class EdgeCreate(BaseModel):
    from_id: str
    to_id: str
    type: str = "NEXT"


class ActiveOrderUpdate(BaseModel):
    node_ids: List[str]


class ChatGPTImportRequest(BaseModel):
    raw_text: str
    context_set_id: Optional[str] = None
    reply_to: Optional[str] = None
    source: Literal["chatgpt_web", "unknown"] = "unknown"
    auto_activate: Optional[bool] = None


class TokenEstimateRequest(BaseModel):
    text: str
    model: Optional[str] = None


SplitStrategy = Literal["auto", "tagged", "heading", "bullets", "paragraph", "sentences", "custom"]


class SplitNodeRequest(BaseModel):
    strategy: SplitStrategy = "auto"
    custom_text: Optional[str] = None
    child_type: Optional[str] = None
    context_set_id: Optional[str] = None
    replace_in_active: bool = False
    inherit_reply_to: bool = True
    target_chars: Optional[int] = 900
    max_chars: Optional[int] = 2000


class SplitNodeResponse(BaseModel):
    ok: bool = True
    parent_id: str
    created_ids: List[str]
    strategy_used: str


class HierarchyPreviewRequest(BaseModel):
    context_set_id: Optional[str] = None
    node_ids: Optional[List[str]] = None
    max_leaf_size: int = 6
