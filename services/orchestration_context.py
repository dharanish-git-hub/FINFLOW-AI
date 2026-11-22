"""
Structured Shared Context for FinFlow AI Multi-Agent Orchestrator.
Maintains state across Intake -> Verification -> Financial Intelligence -> Workflow -> Reporting.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentExecutionStep(BaseModel):
    agent_name: str
    stage: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, NEEDS_REVIEW, SKIPPED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    summary: str = ""
    error_message: Optional[str] = None
    output_data: Optional[Dict[str, Any]] = None


class OrchestrationContext(BaseModel):
    run_id: str
    invoice_id: Optional[int] = None
    invoice_number: str = ""
    file_name: str = ""
    file_hash: str = ""
    current_stage: str = "INTAKE"  # INTAKE, VERIFICATION, FIN_INTEL, WORKFLOW, REPORTING, DONE
    workflow_status: str = "PENDING"  # PENDING, COMPLETED, NEEDS_REVIEW, BLOCKED, FAILED
    extraction_status: str = "PENDING"  # PENDING, COMPLETED, FAILED, SCANNED
    invoice_data: Optional[Dict[str, Any]] = None
    verification_results: Optional[Dict[str, Any]] = None
    financial_risk_results: Optional[Dict[str, Any]] = None
    exceptions: List[str] = Field(default_factory=list)
    agent_execution_history: List[AgentExecutionStep] = Field(default_factory=list)
    timestamps: Dict[str, str] = Field(default_factory=dict)
    error_detail: Optional[str] = None

    def start_agent_step(self, agent_name: str, stage: str) -> AgentExecutionStep:
        step = AgentExecutionStep(
            agent_name=agent_name,
            stage=stage,
            status="RUNNING",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.current_stage = stage
        self.agent_execution_history.append(step)
        return step

    def complete_agent_step(
        self,
        step: AgentExecutionStep,
        status: str = "COMPLETED",
        summary: str = "",
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        step.status = status
        step.completed_at = datetime.now(timezone.utc).isoformat()
        step.summary = summary
        step.output_data = output_data or {}
        step.error_message = error_message
        if step.started_at:
            start_dt = datetime.fromisoformat(step.started_at)
            end_dt = datetime.fromisoformat(step.completed_at)
            step.duration_ms = round((end_dt - start_dt).total_seconds() * 1000, 2)

    def __getitem__(self, item: str):
        """Allows dictionary-style subscripting for backward compatibility with earlier services and tests."""
        if item == "status":
            return "PENDING_APPROVAL" if self.workflow_status == "COMPLETED" else self.workflow_status
        if hasattr(self, item):
            return getattr(self, item)
        if item == "verification":
            return self.verification_results
        if item == "fin_intel":
            return self.financial_risk_results
        if item == "extraction":
            return self.invoice_data
        raise KeyError(item)

    def get(self, item: str, default=None):
        try:
            return self[item]
        except KeyError:
            return default
