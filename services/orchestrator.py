"""
Central Multi-Agent Orchestrator for FINFLOW AI.
Coordinates 5 specialized agents in strict sequence with shared context:
Intake Agent -> Verification Agent -> Financial Intelligence Agent -> Workflow Agent -> Reporting Agent.
Handles failures gracefully, prevents duplicate processing, and records immutable runs in SQLite.
"""

import uuid
import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
from database.db import get_db_connection
from services.orchestration_context import OrchestrationContext, AgentExecutionStep
from agents.intake_agent import IntakeAgent
from agents.verification_agent import VerificationAgent
from agents.fin_intel_agent import FinancialIntelligenceAgent
from agents.workflow_agent import WorkflowAgent
from agents.reporting_agent import ReportingAgent
from agents.base_agent import InvoiceExtractionResult


class Orchestrator:
    def __init__(
        self,
        db_path: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        mock_mode: bool = False,
    ):
        self.db_path = db_path
        self.intake_agent = IntakeAgent(api_key=api_key, model=model, mock_mode=mock_mode)
        self.verification_agent = VerificationAgent(db_path=db_path)
        self.fin_intel_agent = FinancialIntelligenceAgent(db_path=db_path)
        self.workflow_agent = WorkflowAgent(db_path=db_path)
        self.reporting_agent = ReportingAgent(db_path=db_path)

    def process_invoice_document(
        self,
        pdf_bytes: bytes,
        filename: str,
        allow_reprocessing: bool = False,
    ) -> OrchestrationContext:
        """
        Executes the autonomous 5-agent sequence:
        Invoice Upload -> Intake -> Verification -> Fin Intel -> Workflow -> Reporting -> Final Status.
        """
        run_id = f"RUN-{uuid.uuid4().hex[:10].upper()}"
        start_time = datetime.now(timezone.utc).isoformat()

        context = OrchestrationContext(
            run_id=run_id,
            file_name=filename,
            current_stage="INTAKE",
            workflow_status="RUNNING",
            timestamps={"started_at": start_time},
        )

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Step 0: Initial run log in SQLite
        cursor.execute(
            """
            INSERT INTO orchestrator_runs (run_id, file_name, workflow_status, stage, started_at)
            VALUES (?, ?, 'RUNNING', 'INTAKE', ?);
            """,
            (run_id, filename, start_time),
        )
        conn.commit()

        # =========================================================
        # STAGE 1: INTAKE AGENT
        # =========================================================
        intake_step = context.start_agent_step("Intake Agent", "INTAKE")
        extraction: Optional[InvoiceExtractionResult] = None
        file_hash = ""

        try:
            extraction, file_hash, raw_text = self.intake_agent.process(pdf_bytes, filename)
            context.file_hash = file_hash
            context.invoice_number = extraction.invoice_number
            context.invoice_data = extraction.model_dump()
            context.extraction_status = "COMPLETED"

            # Check duplicate invoice unless explicit reprocessing
            if not allow_reprocessing:
                cursor.execute(
                    """
                    SELECT id, invoice_number, vendor_name, total_amount, status 
                    FROM invoices 
                    WHERE (file_hash = ? AND file_hash != '') 
                       OR (invoice_number = ? AND LOWER(vendor_name) = ?);
                    """,
                    (file_hash, extraction.invoice_number, extraction.vendor_name.lower()),
                )
                dup_row = cursor.fetchone()
                if dup_row:
                    context.invoice_id = dup_row["id"]
                    context.workflow_status = "BLOCKED"
                    context.exceptions.append(
                        f"DUPLICATE_PROCESSING: Invoice #{extraction.invoice_number} ({extraction.vendor_name}) already processed (DB Record #{dup_row['id']}, Status: {dup_row['status']})."
                    )
                    context.complete_agent_step(
                        intake_step,
                        status="COMPLETED",
                        summary=f"Extracted #{extraction.invoice_number}, but duplicate record detected.",
                        output_data={"duplicate_id": dup_row["id"]},
                    )
                    self._finalize_run(context, cursor, conn)
                    conn.close()
                    return context

            # Insert invoice record into SQLite
            cursor.execute(
                """
                INSERT INTO invoices (
                    invoice_number, vendor_name, po_number, file_name, file_hash, 
                    invoice_date, due_date, subtotal, tax_amount, total_amount, 
                    currency, status, payment_terms, extraction_raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'EXTRACTED', ?, ?);
                """,
                (
                    extraction.invoice_number,
                    extraction.vendor_name,
                    extraction.po_number,
                    filename,
                    file_hash,
                    extraction.invoice_date,
                    extraction.due_date,
                    extraction.subtotal,
                    extraction.tax_amount,
                    extraction.total_amount,
                    extraction.currency,
                    extraction.payment_terms,
                    extraction.model_dump_json(),
                ),
            )
            invoice_id = cursor.lastrowid
            context.invoice_id = invoice_id

            # Insert line items
            for item in extraction.line_items:
                amt = item.amount if hasattr(item, "amount") and item.amount else item.total_price
                cursor.execute(
                    """
                    INSERT INTO invoice_items (invoice_id, item_description, quantity, unit_price, total_price)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (invoice_id, item.description, item.quantity, item.unit_price, amt),
                )
            conn.commit()

            context.complete_agent_step(
                intake_step,
                status="COMPLETED",
                summary=f"Extracted invoice #{extraction.invoice_number} from '{filename}' (Vendor: {extraction.vendor_name}, Amount: ${extraction.total_amount:,.2f}).",
                output_data={"confidence": extraction.confidence_score, "items_count": len(extraction.line_items)},
            )
            self.reporting_agent.record_audit(
                invoice_id=invoice_id,
                agent_name="Intake Agent",
                action="INVOICE_EXTRACTED",
                message=intake_step.summary,
                level="SUCCESS",
                actor="Intake Agent",
                previous_status="RECEIVED",
                new_status="EXTRACTED",
                category="INTAKE",
            )

        except Exception as e:
            err_msg = str(e)
            context.extraction_status = "FAILED"
            context.workflow_status = "FAILED"
            context.error_detail = err_msg
            context.exceptions.append(f"INTAKE_EXTRACTION_FAILURE: {err_msg}")
            context.complete_agent_step(
                intake_step,
                status="FAILED",
                summary="Invoice extraction failed.",
                error_message=err_msg,
            )
            self.reporting_agent.record_audit(
                invoice_id=context.invoice_id,
                agent_name="Intake Agent",
                action="EXTRACTION_FAILED",
                message=f"Failed to process '{filename}': {err_msg}",
                level="ERROR",
                actor="Intake Agent",
                previous_status="RECEIVED",
                new_status="FAILED",
                category="INTAKE",
            )
            # Stop downstream processing on extraction failure
            self._finalize_run(context, cursor, conn)
            conn.close()
            return context

        # =========================================================
        # STAGE 2: VERIFICATION AGENT
        # =========================================================
        verif_step = context.start_agent_step("Verification Agent", "VERIFICATION")
        try:
            verification = self.verification_agent.verify(extraction)
            context.verification_results = verification.model_dump()

            if verification.vendor_id:
                cursor.execute("UPDATE invoices SET vendor_id = ? WHERE id = ?;", (verification.vendor_id, context.invoice_id))
                conn.commit()

            # Append exceptions from verification
            if verification.reasons and not verification.vendor_verified:
                context.exceptions.extend(verification.reasons)

            verif_status = "COMPLETED" if (verification.vendor_verified and verification.po_matched and not verification.amount_mismatch) else "NEEDS_REVIEW"
            if verification.vendor_status == "BLOCKED":
                verif_status = "FAILED"

            context.complete_agent_step(
                verif_step,
                status=verif_status,
                summary=f"Vendor status: {verification.vendor_status}. PO {verification.po_number or 'N/A'} matched: {verification.po_matched}. Amount mismatch: {verification.amount_mismatch}.",
                output_data=context.verification_results,
            )
            self.reporting_agent.record_audit(
                invoice_id=context.invoice_id,
                agent_name="Verification Agent",
                action="VENDOR_AND_PO_VERIFIED",
                message=verif_step.summary,
                level="WARNING" if verif_status != "COMPLETED" else "INFO",
                actor="Verification Agent",
                previous_status="EXTRACTED",
                new_status="VERIFIED" if verif_status == "COMPLETED" else "NEEDS_REVIEW",
                category="VERIFICATION",
            )

        except Exception as e:
            err_msg = str(e)
            context.exceptions.append(f"VERIFICATION_AGENT_ERROR: {err_msg}")
            context.complete_agent_step(
                verif_step,
                status="FAILED",
                summary="Verification engine error.",
                error_message=err_msg,
            )

        # =========================================================
        # STAGE 3: FINANCIAL INTELLIGENCE AGENT
        # =========================================================
        fin_intel_step = context.start_agent_step("Financial Intelligence Agent", "FIN_INTEL")
        try:
            fin_intel = self.fin_intel_agent.analyze(
                extraction=extraction,
                file_hash=file_hash,
                verification=verification,
                current_invoice_id=context.invoice_id,
            )
            context.financial_risk_results = fin_intel.model_dump()
            if fin_intel.anomaly_flags:
                context.exceptions.extend(fin_intel.anomaly_flags)

            fin_status = "COMPLETED" if not fin_intel.is_suspicious else "NEEDS_REVIEW"
            if fin_intel.risk_score >= 0.90:
                fin_status = "FAILED"

            context.complete_agent_step(
                fin_intel_step,
                status=fin_status,
                summary=f"Risk Score: {fin_intel.risk_score * 100:.0f}%. Duplicate: {fin_intel.is_duplicate}. Math/Tax Anomaly: {fin_intel.math_error or fin_intel.tax_error}.",
                output_data=context.financial_risk_results,
            )
            self.reporting_agent.record_audit(
                invoice_id=context.invoice_id,
                agent_name="Financial Intelligence Agent",
                action="FINANCIAL_INTELLIGENCE_ASSESSMENT",
                message=fin_intel_step.summary,
                level="WARNING" if fin_intel.is_suspicious else "INFO",
                actor="Financial Intelligence Agent",
                previous_status="VERIFIED",
                new_status="NEEDS_REVIEW" if fin_intel.is_suspicious else "VERIFIED",
                category="VERIFICATION",
            )

        except Exception as e:
            err_msg = str(e)
            context.exceptions.append(f"FIN_INTEL_AGENT_ERROR: {err_msg}")
            context.complete_agent_step(
                fin_intel_step,
                status="FAILED",
                summary="Financial intelligence analysis error.",
                error_message=err_msg,
            )

        # =========================================================
        # STAGE 4: WORKFLOW AGENT
        # =========================================================
        wf_step = context.start_agent_step("Workflow Agent", "WORKFLOW")
        try:
            next_status, created_exceptions = self.workflow_agent.evaluate_and_route(
                invoice_id=context.invoice_id,
                extraction=extraction,
                verification=verification,
                fin_intel=fin_intel,
            )

            # Map next_status to orchestrator workflow_status
            if verification.vendor_status == "BLOCKED" or fin_intel.risk_score >= 0.95 or fin_intel.is_duplicate:
                context.workflow_status = "BLOCKED"
            elif next_status == "EXCEPTION" or context.exceptions:
                context.workflow_status = "NEEDS_REVIEW"
            else:
                context.workflow_status = "COMPLETED"

            context.complete_agent_step(
                wf_step,
                status="COMPLETED",
                summary=f"Evaluated approval policy: Routed to '{next_status}' (Workflow state: {context.workflow_status}). Generated {len(created_exceptions)} policy exceptions.",
                output_data={"next_status": next_status, "exceptions_count": len(created_exceptions)},
            )
            self.reporting_agent.record_audit(
                invoice_id=context.invoice_id,
                agent_name="Workflow Agent",
                action="WORKFLOW_DECISION",
                message=wf_step.summary,
                level="WARNING" if context.workflow_status != "COMPLETED" else "SUCCESS",
                actor="Workflow Agent",
                previous_status="VERIFYING",
                new_status=next_status,
                category="WORKFLOW",
            )

        except Exception as e:
            err_msg = str(e)
            context.workflow_status = "FAILED"
            context.exceptions.append(f"WORKFLOW_ROUTING_ERROR: {err_msg}")
            context.complete_agent_step(
                wf_step,
                status="FAILED",
                summary="Workflow routing error.",
                error_message=err_msg,
            )

        # =========================================================
        # STAGE 5: REPORTING AGENT
        # =========================================================
        rep_step = context.start_agent_step("Reporting Agent", "REPORTING")
        try:
            kpis = self.reporting_agent.get_kpi_summary()
            total_duration = sum(s.duration_ms for s in context.agent_execution_history)
            context.complete_agent_step(
                rep_step,
                status="COMPLETED",
                summary=f"Compiled consolidated processing report. Total pipeline duration: {total_duration:.1f}ms. Active AP volume: ${kpis['pipeline_volume']:,.2f}.",
                output_data={"kpis": kpis, "duration_ms": total_duration},
            )
            self.reporting_agent.record_audit(
                invoice_id=context.invoice_id,
                agent_name="Reporting Agent",
                action="PROCESSING_REPORT_COMPILED",
                message=rep_step.summary,
                level="SUCCESS",
            )
        except Exception as e:
            context.complete_agent_step(
                rep_step,
                status="COMPLETED",
                summary="Reporting summary compiled with default metrics.",
            )

        # Complete Orchestration Run
        context.current_stage = "DONE"
        context.timestamps["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._finalize_run(context, cursor, conn)
        conn.close()

        return context

    def _finalize_run(self, context: OrchestrationContext, cursor, conn):
        """Persists the final orchestration run snapshot to SQLite."""
        try:
            completed_at = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                UPDATE orchestrator_runs 
                SET invoice_id = ?, invoice_number = ?, file_hash = ?, 
                    workflow_status = ?, stage = ?, context_json = ?, error_message = ?, 
                    completed_at = ?
                WHERE run_id = ?;
                """,
                (
                    context.invoice_id,
                    context.invoice_number,
                    context.file_hash,
                    context.workflow_status,
                    context.current_stage,
                    context.model_dump_json(),
                    context.error_detail,
                    completed_at,
                    context.run_id,
                ),
            )
            conn.commit()
        except Exception as e:
            print(f"[Orchestrator] Error updating orchestrator_runs: {e}")

    def get_recent_runs(self, limit: int = 10) -> list:
        """Retrieves recent orchestrator execution runs from SQLite."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, run_id, invoice_id, invoice_number, file_name, 
                   workflow_status, stage, error_message, started_at, completed_at
            FROM orchestrator_runs 
            ORDER BY id DESC LIMIT ?;
            """,
            (limit,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
