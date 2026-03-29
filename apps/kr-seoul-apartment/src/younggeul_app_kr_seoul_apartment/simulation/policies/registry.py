from __future__ import annotations

from .heuristic import BrokerPolicy, BuyerPolicy, InvestorPolicy, LandlordPolicy, TenantPolicy
from .protocol import ParticipantPolicy

_POLICY_MAP: dict[str, ParticipantPolicy] = {
    "buyer": BuyerPolicy(),
    "investor": InvestorPolicy(),
    "tenant": TenantPolicy(),
    "landlord": LandlordPolicy(),
    "broker": BrokerPolicy(),
}


def get_default_policy(role: str) -> ParticipantPolicy:
    policy = _POLICY_MAP.get(role)
    if policy is None:
        raise ValueError(f"No default policy for role: {role}")
    return policy
