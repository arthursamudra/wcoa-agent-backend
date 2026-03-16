from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any


class DatasetSource(BaseModel):
    type: Literal["azure_blob", "direct_upload", "api_push"]
    sasUrl: Optional[str] = None


class RegisterDatasetRequest(BaseModel):
    tenantId: str = Field(..., min_length=1)
    format: Literal["excel", "xlsx", "json"] = "excel"
    source: DatasetSource
    createdBy: Optional[str] = None
    correlationId: Optional[str] = None
    originalFilename: str = Field(default="dataset.xlsx")


class CreateDatasetRequest(BaseModel):
    tenantId: str = Field(..., min_length=1)
    createdBy: Optional[str] = None
    correlationId: Optional[str] = None
    originalFilename: str = Field(default="dataset.xlsx")


class DatasetRegisterResponse(BaseModel):
    tenantId: str
    datasetId: str
    uploadUrl: Optional[str] = None
    rawObjectKey: Optional[str] = None
    expiresAt: str
    status: str


class CreateDatasetResponse(DatasetRegisterResponse):
    pass


class ProcessDatasetRequest(BaseModel):
    tenantId: str
    datasetId: str
    correlationId: Optional[str] = None
    actor: Optional[str] = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    tenantId: str
    datasetId: Optional[str] = None
    prompt: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    correlationId: Optional[str] = None
    actor: Optional[str] = None
    temperature: Optional[float] = None


class WCOAOption(BaseModel):
    supplier: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    estimatedUnitPrice: Optional[float] = None
    estimatedTotalCost: Optional[float] = None
    paymentTerms: Optional[str] = None
    leadTime: Optional[str] = None
    workingCapitalImpact: Optional[str] = None
    risks: List[str] = Field(default_factory=list)


class WCOAAgentResponse(BaseModel):
    decision: str = Field(..., min_length=1)
    options: List[WCOAOption] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    data_quality_flags: List[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    datasetId: Optional[str] = None
    response: Dict[str, Any]
