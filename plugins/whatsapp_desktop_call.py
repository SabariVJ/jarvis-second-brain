"""WhatsApp Desktop call tool; navigation is owned by actions.whatsapp_desktop_call."""
from actions.whatsapp_desktop_call import whatsapp_desktop_call

PLUGIN = {
    "name": "whatsapp_desktop_call",
    "description": "Start a verified WhatsApp Desktop voice or video call to an exact saved contact.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "intent": {"type": "STRING", "description": "voice_call or video_call"},
            "contact_name": {"type": "STRING", "description": "Exact saved contact name"},
        },
        "required": ["intent", "contact_name"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    intent = str(parameters.get("intent") or "voice_call").casefold()
    if intent not in ("voice_call", "video_call"):
        return "Unsupported WhatsApp call intent."
    return whatsapp_desktop_call(parameters, player=player, session_memory=session_memory)
