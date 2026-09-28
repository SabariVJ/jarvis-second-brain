"""Structural WhatsApp accessibility predicates. No screen-position assumptions."""
from __future__ import annotations


def prop(control, name, default=""):
    try:
        return getattr(control, name, default)
    except Exception:
        return default


def norm(value):
    return " ".join(str(value or "").casefold().split())


def name(control):
    value = prop(control, "Name")
    if value:
        return str(value).strip()
    try:
        return str(control.GetLegacyIAccessiblePattern().Name or "").strip()
    except Exception:
        return ""


def kind(control):
    return prop(control, "ControlTypeName")


def ancestors(control, limit=32):
    for _ in range(limit):
        try:
            control = control.GetParentControl()
        except Exception:
            return
        if control is None:
            return
        yield control


def children(control):
    try:
        return control.GetChildren()
    except Exception:
        return []


def subtree(root, limit=120, depth=8):
    stack = [(root, 0)]
    count = 0
    while stack and count < limit:
        node, level = stack.pop()
        count += 1
        yield node
        if level < depth:
            stack.extend((c, level + 1) for c in reversed(children(node)))


def visible(control):
    return prop(control, "IsEnabled", False) and not prop(control, "IsOffscreen", True)


def is_row(control):
    role = norm(prop(control, "AriaRole"))
    if role:
        return role in ("row", "listitem", "option")
    return kind(control) in ("ListItemControl", "DataItemControl", "TreeItemControl")


def row_for(control):
    for node in [control, *ancestors(control, 12)]:
        if is_row(node):
            return node
        if kind(node) in ("DocumentControl", "WindowControl"):
            break
    return None


def result_matches(row, contact):
    """Only row titles count. Member labels and message contents never count."""
    if not is_row(row) or not visible(row):
        return False
    parents = list(ancestors(row))
    if any(norm(name(p)) in ("messages", "message results", "groups", "group members", "participants") for p in parents):
        return False
    if not any(kind(p) in ("ListControl", "DataGridControl", "TableControl", "TreeControl") or norm(prop(p, "AriaRole")) in ("grid", "list", "listbox") for p in parents):
        return False
    row_name, wanted = norm(name(row)), norm(contact)
    # Exact row name, or first title text in a row whose aggregate name starts
    # with that same title. Never scan all descendant labels for a substring.
    if row_name == wanted:
        return True
    if row_name and not any(row_name.startswith(wanted + sep) for sep in (",", "\n", " ")):
        return False
    for node in subtree(row):
        if node is row or not visible(node):
            continue
        if kind(node) == "TextControl" or norm(prop(node, "AriaRole")) == "heading":
            title = norm(name(node))
            if title:
                return title == wanted
    return False


def is_call_button(control, video=False):
    labels = ("video call", "start video call") if video else ("voice call", "audio call", "start voice call", "start audio call", "call")
    return visible(control) and kind(control) in ("ButtonControl", "HyperlinkControl") and norm(name(control)) in labels


def header_container(title):
    """A title is actionable and shares a compact header with call controls.

    Exclude every row/list/message context, even when its text equals the target.
    The whole conversation/main document is not accepted as a header.
    """
    if kind(title) not in ("ButtonControl", "TextControl"):
        return None
    parents = list(ancestors(title))
    if any(is_row(p) or kind(p) in ("ListControl", "DataGridControl", "TableControl") for p in parents):
        return None
    if kind(title) == "TextControl":
        # Plain participant text is not a conversation title. Require a named
        # title button or an explicit heading role.
        if norm(prop(title, "AriaRole")) != "heading":
            title_button = next((p for p in parents[:3] if kind(p) == "ButtonControl" and norm(name(p)) == norm(name(title))), None)
            if title_button is None:
                return None
    for parent in parents[:6]:
        if kind(parent) in ("DocumentControl", "WindowControl"):
            break
        nodes = list(subtree(parent, limit=81))
        if len(nodes) >= 81:
            break
        if any(kind(n) in ("EditControl", "ListControl", "DataGridControl", "DocumentControl") or is_row(n) for n in nodes):
            break
        if any(is_call_button(n) or is_call_button(n, video=True) for n in nodes):
            return parent
    return None


def is_search(control, after_shortcut=False):
    if not visible(control):
        return False
    if kind(control) != "EditControl" and norm(prop(control, "AriaRole")) not in ("searchbox", "textbox"):
        return False
    label = norm(name(control))
    parents = list(ancestors(control))
    if any("search messages" in norm(name(p)) or "search in conversation" in norm(name(p)) for p in parents):
        return False
    if label in ("search or start a new chat", "search chats", "search contacts", "search name or number", "search name or number…"):
        return True
    return label == "search" and (after_shortcut or any(norm(name(p)) in ("chats", "new chat", "search chats") for p in parents))


def info_panel_kind(nodes, contact):
    """Positive contact-info evidence is required; absence of 'group' is insufficient."""
    labels = {norm(name(n)) for n in nodes if visible(n)}
    if "group info" in labels:
        return "group"
    if "contact info" in labels and norm(contact) in labels:
        return "direct"
    return "unknown"
