from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel

class ThreadCreate(BaseModel):
    title: Optional[str] = None

class MessageCreate(BaseModel):
    role: str  # user | assistant
    text: str
    reply_to: Optional[str] = None

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
