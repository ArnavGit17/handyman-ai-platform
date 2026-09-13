import re
from dataclasses import dataclass

from ..schemas import SERVICES


@dataclass
class UnderstoodRequest:
    service_type: str
    required_skills: list[str]
    urgency: str
    area: str
    source: str = "local-fallback"


class AIProvider:
    def understand(self, description: str, area: str | None = None) -> UnderstoodRequest:
        raise NotImplementedError


class LocalAIProvider(AIProvider):
    SERVICE_RULES = {
        "Plumbing": ("pipe repair", "sink repair", "leak repair", ("plumb", "pipe", "sink", "tap", "faucet", "water", "leak")),
        "Electrical": ("electrical installation", "fan installation", "electrical repair", ("electric", "fan", "switch", "light", "wiring", "socket")),
        "Carpentry": ("furniture repair", "woodwork", "cupboard repair", ("carpent", "wood", "cupboard", "furniture", "door", "shelf")),
        "Cleaning": ("house cleaning", "deep cleaning", "sanitation", ("clean", "house", "dust", "sanitize")),
        "Painting": ("wall painting", "surface preparation", "painting", ("paint", "wall", "colour", "color")),
        "Appliance Repair": ("appliance diagnostics", "washing machine repair", "appliance repair", ("appliance", "washing machine", "refrigerator", "fridge", "microwave", "repair")),
    }

    def understand(self, description: str, area: str | None = None, service_hint: str | None = None) -> UnderstoodRequest:
        text = description.lower()
        scores = {service: sum(1 for keyword in rules[3] if keyword in text) for service, rules in self.SERVICE_RULES.items()}
        service = service_hint or max(scores, key=scores.get)
        if service not in self.SERVICE_RULES:
            raise ValueError(f"Unsupported service: {service}")
        if not service_hint and scores[service] == 0:
            raise ValueError("We could not identify a service from that request. Mention plumbing, electrical, carpentry, cleaning, painting, or an appliance.")
        primary, secondary, fallback, _ = self.SERVICE_RULES[service]
        skill = secondary if any(word in text for word in ("fan", "cupboard", "washing machine", "sink")) else primary
        urgency = "emergency" if re.search(r"\b(urgent|urgently|emergency|immediately|now|burst|flooding)\b", text) else "normal"
        return UnderstoodRequest(service, [skill, primary], urgency, area or self._find_area(text), "local-fallback")

    @staticmethod
    def _find_area(text: str) -> str:
        match = re.search(r"\b(area\s+[a-e])\b", text, re.IGNORECASE)
        return match.group(1).title() if match else "Area A"


def get_request_understanding_provider() -> AIProvider:
    # A configured provider can be added behind this interface without making the demo depend on it.
    return LocalAIProvider()


class RequestUnderstandingService:
    def __init__(self, provider: AIProvider | None = None):
        self.provider = provider or get_request_understanding_provider()

    def understand(self, description: str, area: str | None = None, service_hint: str | None = None) -> UnderstoodRequest:
        return self.provider.understand(description, area, service_hint)
