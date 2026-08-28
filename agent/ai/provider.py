"""
AI Provider Abstraction Layer for Payment Recovery Diagnostics.

Provides pluggable AI model implementations:
1. LocalAIProvider: Fast, deterministic diagnostic model operating on failure semantics & empirical curves.
2. OpenAIProvider: LLM integration using structured JSON schemas (when configured).
3. MockAIProvider: Configurable mock provider for adversarial safety tests and failure simulations.
"""
import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from agent.models import (
    ExtractedFailureData,
    AIDiagnosisResult,
    DecidedAction
)
from db.config import settings

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for all AI diagnostic providers."""

    @abstractmethod
    def diagnose(
        self,
        failure_data: ExtractedFailureData,
        context: Optional[Dict[str, Any]] = None
    ) -> AIDiagnosisResult:
        """
        Diagnoses root cause, estimates recovery probability, and recommends next action.
        """
        pass


class LocalAIProvider(AIProvider):
    """
    Local Diagnostic Model.
    Evaluates failure parameters, error reason taxonomy, bank downtime indicators,
    and historical attempt counts to produce calibrated recovery probabilities.
    Requires ZERO external API keys or cloud dependencies.
    """

    def diagnose(
        self,
        failure_data: ExtractedFailureData,
        context: Optional[Dict[str, Any]] = None
    ) -> AIDiagnosisResult:
        context = context or {}
        error_reason = (failure_data.error_reason or "").lower()
        error_code = (failure_data.error_code or "").lower()
        error_desc = (failure_data.error_description or "").lower()
        attempt_count = context.get("current_attempt_count", 0)

        # 1. RISK / FRAUD DIAGNOSIS
        risk_triggers = [
            "payment_risk_check_failed", "risk_check_failed", "high_risk",
            "fraud_suspected", "card_blacklisted", "stolen_card", "lost_card",
            "restricted_card", "do_not_honor", "security_violation"
        ]
        if any(t in error_reason or t in error_desc for t in risk_triggers):
            return AIDiagnosisResult(
                failure_diagnosis="issuer_security_risk_quarantine",
                recovery_probability=0.0,
                recommended_action=DecidedAction.ESCALATE_TO_HUMAN,
                recommended_delay_hours=0,
                customer_message_strategy="HUMAN_SUPPORT",
                confidence=0.99,
                reasoning="Decline triggered by bank/issuer fraud or risk filter. Automated retries or nudges strictly unsafe.",
                provider_used="local_diagnostic_engine"
            )

        # 2. HARD DECLINE (Credential Invalidation)
        hard_triggers = [
            "expired_card", "invalid_card", "card_inactive", "token_not_eligible",
            "token_deleted", "token_inactive", "mandate_cancelled", "mandate_inactive",
            "customer_mandate_revoked", "account_closed", "subscription_halted"
        ]
        if any(t in error_reason or t in error_desc for t in hard_triggers) or failure_data.event_type == "subscription.halted":
            return AIDiagnosisResult(
                failure_diagnosis="permanent_credential_invalidation",
                recovery_probability=0.08,
                recommended_action=DecidedAction.NUDGE_PAYMENT_UPDATE,
                recommended_delay_hours=0,
                customer_message_strategy="URGENT_CARD_UPDATE",
                confidence=0.96,
                reasoning="Payment instrument or mandate is permanently invalid. Autonomous retries will fail without customer updating credentials.",
                provider_used="local_diagnostic_engine"
            )

        # 3. SOFT DECLINE (Transient Gateway / Funds Deficit)
        is_bank_timeout = any(t in error_reason or t in error_desc for t in ["timeout", "timed_out", "gateway_error", "bank_technical_error", "network_error", "temporary_issuer_down"])
        
        if is_bank_timeout:
            # Short-term network/bank downtime
            prob = max(0.20, 0.88 - (attempt_count * 0.25))
            delay_h = 1 if attempt_count == 0 else 6
            return AIDiagnosisResult(
                failure_diagnosis="transient_banking_gateway_downtime",
                recovery_probability=round(prob, 2),
                recommended_action=DecidedAction.SCHEDULE_RETRY,
                recommended_delay_hours=delay_h,
                customer_message_strategy="NONE",
                confidence=0.92,
                reasoning="Failure caused by transient gateway/issuer network timeout. High probability of success upon backoff retry.",
                provider_used="local_diagnostic_engine"
            )
        else:
            # Liquidity / Insufficient funds
            prob = max(0.15, 0.78 - (attempt_count * 0.22))
            delay_h = 6 if attempt_count == 0 else 24
            msg_strat = "NONE" if attempt_count < 2 else "PAYMENT_LINK_EMAIL"
            return AIDiagnosisResult(
                failure_diagnosis="temporary_liquidity_deficit",
                recovery_probability=round(prob, 2),
                recommended_action=DecidedAction.SCHEDULE_RETRY,
                recommended_delay_hours=delay_h,
                customer_message_strategy=msg_strat,
                confidence=0.89,
                reasoning="Transient debit failure (insufficient balance). Progressive backoff retry recommended.",
                provider_used="local_diagnostic_engine"
            )


class OpenAIProvider(AIProvider):
    """
    OpenAI LLM Diagnostic Provider.
    Invokes external LLM when OPENAI_API_KEY is configured in the environment.
    Falls back gracefully to LocalAIProvider if API call fails or key is missing.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.fallback = LocalAIProvider()

    def diagnose(
        self,
        failure_data: ExtractedFailureData,
        context: Optional[Dict[str, Any]] = None
    ) -> AIDiagnosisResult:
        if not self.api_key:
            logger.info("[AI PROVIDER] No OPENAI_API_KEY set. Seamlessly routing to LocalAIProvider.")
            return self.fallback.diagnose(failure_data, context)

        try:
            import httpx
            system_prompt = (
                "You are an expert payment recovery diagnostician for Razorpay subscriptions. "
                "Analyze payment failure events and output a strict JSON object with: "
                "failure_diagnosis (string), recovery_probability (float 0.0-1.0), "
                "recommended_action (one of: 'SCHEDULE_RETRY', 'NUDGE_PAYMENT_UPDATE', 'ESCALATE_TO_HUMAN'), "
                "recommended_delay_hours (integer), customer_message_strategy ('NONE', 'PAYMENT_LINK_EMAIL', 'URGENT_CARD_UPDATE', 'HUMAN_SUPPORT'), "
                "confidence (float 0.0-1.0), and reasoning (string)."
            )
            user_prompt = json.dumps({
                "event_type": failure_data.event_type,
                "error_code": failure_data.error_code,
                "error_reason": failure_data.error_reason,
                "error_description": failure_data.error_description,
                "attempt_count": context.get("current_attempt_count", 0) if context else 0
            })

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1
            }

            resp = httpx.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=8.0)
            if resp.status_code == 200:
                content = json.loads(resp.json()["choices"][0]["message"]["content"])
                return AIDiagnosisResult(
                    failure_diagnosis=content.get("failure_diagnosis", "unknown_failure"),
                    recovery_probability=float(content.get("recovery_probability", 0.5)),
                    recommended_action=DecidedAction(content.get("recommended_action", "SCHEDULE_RETRY")),
                    recommended_delay_hours=int(content.get("recommended_delay_hours", 1)),
                    customer_message_strategy=content.get("customer_message_strategy", "NONE"),
                    confidence=float(content.get("confidence", 0.8)),
                    reasoning=content.get("reasoning", "LLM diagnostic evaluation"),
                    provider_used=f"openai/{self.model}",
                    raw_model_response=content
                )
            else:
                logger.warning(f"[AI PROVIDER] OpenAI API returned HTTP {resp.status_code}. Using local fallback.")
                return self.fallback.diagnose(failure_data, context)
        except Exception as e:
            logger.warning(f"[AI PROVIDER] OpenAI call error ({e}). Using local fallback.")
            return self.fallback.diagnose(failure_data, context)


class MockAIProvider(AIProvider):
    """
    Configurable Mock AI Provider for adversarial safety testing and fault injection.
    Allows injecting custom diagnosis results or simulating hallucinated actions.
    """

    def __init__(self, override_result: Optional[AIDiagnosisResult] = None):
        self.override_result = override_result
        self.fallback = LocalAIProvider()

    def set_override(self, result: Optional[AIDiagnosisResult]):
        self.override_result = result

    def diagnose(
        self,
        failure_data: ExtractedFailureData,
        context: Optional[Dict[str, Any]] = None
    ) -> AIDiagnosisResult:
        if self.override_result:
            return self.override_result
        return self.fallback.diagnose(failure_data, context)


def get_ai_provider(provider_name: Optional[str] = None) -> AIProvider:
    """Factory to instantiate the configured AI Provider."""
    name = (provider_name or os.environ.get("AI_PROVIDER", "local")).lower()
    if name == "openai":
        return OpenAIProvider()
    elif name == "mock":
        return MockAIProvider()
    return LocalAIProvider()
