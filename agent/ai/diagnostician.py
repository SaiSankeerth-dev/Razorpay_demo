"""
AI Diagnostician Orchestrator.

Invokes the configured AIProvider to assess failure semantics, predict
recovery probabilities, and formulate structured recovery recommendations.
"""
import time
import logging
from typing import Dict, Any, Optional

from agent.models import ExtractedFailureData, AIDiagnosisResult, DecidedAction
from agent.ai.provider import AIProvider, get_ai_provider

logger = logging.getLogger(__name__)


class AIDiagnostician:
    """
    AI Diagnostician for Payment Recovery.
    Provides automated root cause diagnosis, recovery probability calculation,
    and recommended recovery strategy.
    """

    def __init__(self, provider: Optional[AIProvider] = None):
        self.provider = provider or get_ai_provider()

    def diagnose_failure(
        self,
        failure_data: ExtractedFailureData,
        context: Optional[Dict[str, Any]] = None
    ) -> AIDiagnosisResult:
        """
        Executes AI diagnosis on a payment failure event.

        Args:
            failure_data: Normalized failure metadata from webhook.
            context: Additional runtime context (attempt count, previous actions).

        Returns:
            AIDiagnosisResult with validated probability, recommendation, and reasoning.
        """
        t0 = time.perf_counter()
        sub_id = failure_data.subscription_id or "unknown_sub"
        
        try:
            result = self.provider.diagnose(failure_data=failure_data, context=context)
        except Exception as e:
            logger.error(f"[AI DIAGNOSTICIAN] Provider error on '{sub_id}': {e}. Applying safe fallback.")
            # Failsafe fallback
            result = AIDiagnosisResult(
                failure_diagnosis="unclassified_error_failsafe",
                recovery_probability=0.5,
                recommended_action=DecidedAction.SCHEDULE_RETRY,
                recommended_delay_hours=1,
                customer_message_strategy="NONE",
                confidence=0.5,
                reasoning=f"AI provider encountered error ({str(e)}). Default safe retry recommendation generated.",
                provider_used="failsafe_local"
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            f"[AI DIAGNOSIS] Sub: '{sub_id}' | Cause: '{result.failure_diagnosis}' | "
            f"P(rec): {result.recovery_probability:.2f} | Action: {result.recommended_action.value} | "
            f"Confidence: {result.confidence:.2f} | Latency: {elapsed_ms:.1f}ms"
        )
        return result
