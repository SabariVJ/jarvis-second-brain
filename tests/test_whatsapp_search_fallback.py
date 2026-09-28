import sys
import types
import unittest
from contextlib import ExitStack
from unittest.mock import patch

sys.modules.setdefault("psutil", types.ModuleType("psutil"))
sys.modules.setdefault("uiautomation", types.ModuleType("uiautomation"))
from actions import whatsapp_desktop_call as wa
from actions import _whatsapp_semantics as sem


class Node:
    def __init__(self, name="", kind="GroupControl", children=(), role="", hwnd=0):
        self.Name, self.ControlTypeName, self.AriaRole = name, kind, role
        self.IsEnabled, self.IsOffscreen = True, False
        self.NativeWindowHandle = hwnd
        self.parent = None
        self.children = list(children)
        for child in self.children:
            child.parent = self

    def GetChildren(self):
        return self.children

    def GetParentControl(self):
        return self.parent

    def GetRuntimeId(self):
        return [id(self)]

    def SetFocus(self):
        pass


class ExactDirectChatTests(unittest.TestCase):
    def test_observed_webview_gridcells_do_not_duplicate_the_row(self):
        title = Node("Ganesh", "TextControl", role="description")
        cell = Node("Ganesh 1:34 pm", "DataItemControl", [title], role="gridcell")
        row = Node("Ganesh 1:34 pm last message", "DataItemControl", [cell], role="row")
        root = Node("Chat list", "DataGridControl", [row], role="grid")
        with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(root))):
            self.assertIs(wa._find_contact_result(root, "Ganesh"), row)

    def test_group_member_is_not_result_title(self):
        member = Node("Ganesh", "TextControl")
        group = Node("Nanga 5 peru", "ListItemControl", [member])
        direct = Node("Ganesh", "ListItemControl")
        chats = Node("Chats", "ListControl", [group, direct])
        with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(chats))):
            self.assertIs(wa._find_contact_result(chats, "Ganesh"), direct)

    def test_message_and_member_metadata_rejected(self):
        for label in ("Groups", "Messages", "Group members", "Participants"):
            row = Node("Ganesh", "ListItemControl")
            Node(label, "ListControl", [row])
            self.assertFalse(sem.result_matches(row, "Ganesh"))

    def test_group_preview_never_becomes_title(self):
        row = Node("Nanga 5 peru, Ganesh: hello", "ListItemControl",
                   [Node("Nanga 5 peru", "TextControl"), Node("Ganesh", "TextControl")])
        Node("Chats", "ListControl", [row])
        self.assertFalse(sem.result_matches(row, "Ganesh"))

    def test_ambiguous_exact_rows_rejected(self):
        root = Node("Chats", "ListControl", [Node("Ganesh", "ListItemControl"), Node("Ganesh", "ListItemControl")])
        with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(root))):
            self.assertIsNone(wa._find_contact_result(root, "Ganesh"))

    def test_header_member_name_is_not_title(self):
        title = Node("Nanga 5 peru", "ButtonControl")
        member = Node("Ganesh", "TextControl")
        header = Node(children=[title, member, Node("Voice call", "ButtonControl")])
        with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(header))):
            self.assertIsNone(wa._find_chat_header(header, "Ganesh"))

    def test_direct_header_is_structural_not_geometric(self):
        title = Node("Ganesh", "ButtonControl")
        header = Node(children=[title, Node("Voice call", "ButtonControl")])
        with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(header))):
            self.assertIs(wa._find_chat_header(header, "Ganesh"), title)

    def test_group_named_ganesh_still_rejected(self):
        self.assertEqual(sem.info_panel_kind([Node("Group info", "TextControl"), Node("Ganesh", "TextControl")], "Ganesh"), "group")
        self.assertEqual(sem.info_panel_kind([Node("Ganesh", "TextControl")], "Ganesh"), "unknown")
        self.assertEqual(sem.info_panel_kind([Node("Contact info", "TextControl"), Node("Ganesh", "TextControl")], "Ganesh"), "direct")


class NativeSearchTests(unittest.TestCase):
    def test_contenteditable_empty_value_pattern_uses_text_pattern(self):
        control = types.SimpleNamespace(
            GetValuePattern=lambda: types.SimpleNamespace(Value=""),
            GetLegacyIAccessiblePattern=lambda: types.SimpleNamespace(Value=""),
            GetTextPattern=lambda: types.SimpleNamespace(DocumentRange=types.SimpleNamespace(GetText=lambda _: "Ganesh")))
        self.assertEqual(wa._control_value(control), "Ganesh")

    def test_host_and_editor_focus_flags_choose_editor(self):
        search = Node("Search or start a new chat", "EditControl")
        root = Node("", "PaneControl", [search])
        root.HasKeyboardFocus = search.HasKeyboardFocus = True
        with patch.object(wa.auto, "GetFocusedControl", return_value=root, create=True):
            with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(root))):
                self.assertIs(wa._focused_control(root), search)

    def test_missing_search_uses_shortcut_and_verifies_focus(self):
        old = Node("Type a message", "EditControl")
        search = Node("Search", "EditControl")
        root = Node("WhatsApp", "WindowControl", [search], hwnd=42)
        with ExitStack() as stack:
            stack.enter_context(patch.object(wa, "_diagnose"))
            stack.enter_context(patch.object(wa, "_find_search_box", return_value=None))
            stack.enter_context(patch.object(wa, "_webview_content_root", return_value=root))
            stack.enter_context(patch.object(wa, "_foreground_is", return_value=True))
            stack.enter_context(patch.object(wa, "_wait_value", side_effect=lambda fn, **_: fn()))
            stack.enter_context(patch.object(wa.auto, "GetFocusedControl", side_effect=[old, search], create=True))
            shortcut = stack.enter_context(patch.object(wa, "_send_search_shortcut"))
            _, actual, backend = wa._open_verified_search(root, 42, None)
            self.assertIs(actual, search)
            self.assertIn("keyboard/Win32", backend)
            shortcut.assert_called_once_with(42)

    def test_shortcut_does_not_authorize_paste_into_composer(self):
        composer = Node("Type a message", "EditControl")
        root = Node("WhatsApp", "WindowControl", [composer], hwnd=42)
        with ExitStack() as stack:
            for name in ("_diagnose", "_send_search_shortcut"):
                stack.enter_context(patch.object(wa, name))
            stack.enter_context(patch.object(wa, "_find_search_box", return_value=None))
            stack.enter_context(patch.object(wa, "_webview_content_root", return_value=root))
            stack.enter_context(patch.object(wa, "_foreground_is", return_value=True))
            stack.enter_context(patch.object(wa, "_wait_value", side_effect=lambda fn, **_: fn()))
            stack.enter_context(patch.object(wa.auto, "GetFocusedControl", return_value=composer, create=True))
            stack.enter_context(patch.object(wa, "_pywinauto_root", return_value=root))
            paste = stack.enter_context(patch.object(wa, "_set_clipboard_text"))
            with self.assertRaisesRegex(wa._VerificationError, "VERIFY_SEARCH_MODE"):
                wa._open_verified_search(root, 42, None)
            paste.assert_not_called()

    def test_search_value_must_equal_contact_not_contain_it(self):
        search = Node("Search", "EditControl")
        with ExitStack() as stack:
            stack.enter_context(patch.object(wa, "_foreground_is", return_value=True))
            stack.enter_context(patch.object(wa.auto, "GetFocusedControl", return_value=search, create=True))
            stack.enter_context(patch.object(wa, "_set_clipboard_text", return_value=True))
            stack.enter_context(patch.object(wa, "_sendinput_chord"))
            stack.enter_context(patch.object(wa, "_control_value", return_value="Ganesh Kumar"))
            stack.enter_context(patch.object(wa, "_wait_value", side_effect=lambda fn, **_: fn()))
            with self.assertRaisesRegex(wa._VerificationError, "ENTER_CONTACT"):
                wa._enter_verified_contact(None, 42, search, "Ganesh", None, "keyboard/Win32")

    def test_raw_tree_reaches_below_webview_host(self):
        with patch.object(wa.auto, "WalkControl", return_value=iter([]), create=True) as walk:
            list(wa._walk(object(), 8))
            self.assertGreaterEqual(walk.call_args.kwargs["maxDepth"], 48)


class WorkflowGatesTests(unittest.TestCase):
    def fixture(self, stack):
        root = Node("WhatsApp", "WindowControl", hwnd=42)
        row = Node("Ganesh", "ListItemControl")
        title = Node("Ganesh", "ButtonControl")
        values = {"_launch_whatsapp": (True, "detected"), "_find_whatsapp_window": root,
                  "_force_foreground_hwnd": True, "_open_verified_search": (root, object(), "keyboard/Win32"),
                  "_find_contact_result": row, "_find_chat_header": title,
                  "_verify_direct_chat": (root, title), "_find_call_button": object(),
                  "_activate_verified_element": True}
        mocks = {name: stack.enter_context(patch.object(wa, name, return_value=value)) for name, value in values.items()}
        stack.enter_context(patch.object(wa, "_diagnose"))
        stack.enter_context(patch.object(wa, "_enter_verified_contact"))
        stack.enter_context(patch.object(wa.os, "name", "nt"))
        stack.enter_context(patch.object(wa, "_wait_value", side_effect=lambda fn, **_: fn()))
        return mocks

    def test_group_verification_failure_prevents_call_control_activation(self):
        with ExitStack() as stack:
            mocks = self.fixture(stack)
            stack.enter_context(patch.object(wa, "_verify_call_started", return_value=False))
            mocks["_verify_direct_chat"].side_effect = wa._VerificationError("VERIFY_NOT_GROUP", "group conversation rejected")
            result = wa.whatsapp_desktop_call({"contact_name": "Ganesh"})
            self.assertIn("group conversation rejected", result)
            mocks["_find_call_button"].assert_not_called()
            self.assertEqual(mocks["_activate_verified_element"].call_count, 1)

    def test_click_without_active_call_ui_never_succeeds(self):
        with ExitStack() as stack:
            self.fixture(stack)
            stack.enter_context(patch.object(wa, "_verify_call_started", return_value=False))
            result = wa.whatsapp_desktop_call({"contact_name": "Ganesh"})
            self.assertIn("VERIFY_CALL_UI failed", result)
            self.assertNotIn("call started", result)

    def test_success_requires_all_three_call_ui_checks(self):
        with ExitStack() as stack:
            self.fixture(stack)
            check = stack.enter_context(patch.object(wa, "_verify_call_started", side_effect=[False, False, True]))
            result = wa.whatsapp_desktop_call({"contact_name": "Ganesh"})
            self.assertEqual(result, "WhatsApp voice call started with Ganesh.")
            self.assertEqual(check.call_args.args[0], "Ganesh")

    def test_call_ui_for_other_contact_rejected(self):
        hangup = Node("End call", "ButtonControl")
        root = Node("WhatsApp", "WindowControl", [Node("Nanga 5 peru", "TextControl"), hangup])
        with patch.object(wa, "_whatsapp_windows", return_value=[root]):
            with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(root))):
                self.assertFalse(wa._verify_call_started("Ganesh", timeout=0.01))

    def test_call_ui_requires_exact_contact_and_end_call(self):
        hangup = Node("End call", "ButtonControl")
        root = Node("WhatsApp", "WindowControl", [Node("Ganesh", "TextControl"), hangup])
        with patch.object(wa, "_whatsapp_windows", return_value=[root]):
            with patch.object(wa, "_walk", side_effect=lambda *_: iter(sem.subtree(root))):
                self.assertTrue(wa._verify_call_started("Ganesh", timeout=0.01))


if __name__ == "__main__":
    unittest.main()
