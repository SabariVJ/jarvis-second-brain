import json
import ctypes
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from jarvis.focus import FocusLock, active_windows_window


class FakeClock:
    def __init__(self): self.value=1000
    def __call__(self): return self.value
    def advance(self, seconds): self.value+=seconds


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.clock=FakeClock();self.window={'process':'code.exe','title':'Project - Visual Studio Code'}
        self.focus=FocusLock(Path(self.tmp.name)/'focus.json',sampler=lambda:self.window.copy(),clock=self.clock,worker=False,interval=5)

    def test_session_controls_counts_and_keeps_no_window_title(self):
        status=self.focus.start(90,'Coding',['code.exe'],['instagram','youtube'])
        self.assertEqual(status['state'],'ACTIVE');self.clock.advance(5);self.focus.sample_once()
        self.assertEqual(self.focus.status()['focused_seconds'],5)
        self.window={'process':'chrome.exe','title':'Instagram — Chrome'};self.clock.advance(5);self.focus.sample_once()
        status=self.focus.status();self.assertEqual(status['distraction_count'],1)
        self.assertIn('Instagram can wait.',status['warning'])
        raw=Path(self.tmp.name,'focus.json').read_text(encoding='utf-8')
        self.assertNotIn('Instagram — Chrome',raw);self.assertNotIn('code.exe - Project',raw)
        self.focus.pause();self.clock.advance(30);paused=self.focus.status()['remaining_seconds']
        self.assertEqual(paused,90*60-10)
        self.focus.resume();self.clock.advance(10);stopped=self.focus.stop()
        self.assertEqual(stopped['state'],'STOPPED');self.assertEqual(stopped['pause_count'],1)
        loaded=FocusLock(Path(self.tmp.name)/'focus.json',sampler=lambda:None,clock=self.clock,worker=False)
        self.assertEqual(loaded.status()['distraction_count'],1)
        self.assertEqual(loaded.status()['recent_sessions'][-1]['result'],'stopped')

    def test_duration_rules_and_command_state_validation(self):
        for minutes in (0,481,'x'):
            with self.subTest(minutes=minutes),self.assertRaises(ValueError):self.focus.start(minutes)
        with self.assertRaises(ValueError):self.focus.start(25,'')
        with self.assertRaises(ValueError):self.focus.pause()
        with self.assertRaises(ValueError):self.focus.resume()
        with self.assertRaises(ValueError):self.focus.stop()

    def test_expiration_and_windows_sampler_fallback(self):
        self.focus.start(1);self.clock.advance(60)
        self.assertEqual(self.focus.status()['state'],'COMPLETED')
        with patch('jarvis.focus.os.name','posix'):
            self.assertIsNone(active_windows_window())

    def test_windows_sampler_reads_only_foreground_process_and_title(self):
        user=Mock();kernel=Mock();user.GetForegroundWindow.return_value=7;user.GetWindowTextLengthW.return_value=18
        user.GetWindowTextW.side_effect=lambda hwnd,buf,n:setattr(buf,'value','Instagram - Chrome')
        user.GetWindowThreadProcessId.side_effect=lambda hwnd,pid:setattr(pid._obj,'value',42)
        kernel.OpenProcess.return_value=11
        kernel.QueryFullProcessImageNameW.side_effect=lambda h,f,buf,size:setattr(buf,'value',r'C:\Browser\chrome.exe') or True
        with patch('jarvis.focus.os.name','nt'),patch.object(ctypes,'windll',NS(user32=user,kernel32=kernel),create=True):
            sample=active_windows_window()
        self.assertEqual(sample,{'process':'chrome.exe','title':'Instagram - Chrome'})
        user.GetForegroundWindow.assert_called_once_with();kernel.CloseHandle.assert_called_once_with(11)


if __name__=='__main__':unittest.main()
