import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from jarvis.windows import WindowsTools


class WindowsToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'notes';self.root.mkdir()
        self.pdf=self.root/'report.pdf';self.pdf.write_bytes(b'%PDF')
        self.launch=Mock();self.opened=Mock()
        self.volume=Mock(side_effect=lambda percent:{'changed':True,'percent':percent})
        self.apps={'code':str(self.pdf)}
        self.tools=WindowsTools([self.root],platform_name='Windows',applications=self.apps,
            start_file=self.opened,start_process=self.launch,url_opener=Mock(return_value=True),
            active_window_provider=lambda:{'application':'Code.exe','title':'Report review'},volume_setter=self.volume)

    def test_allowlisted_application_and_public_web_url_use_structured_apis(self):
        self.assertEqual(self.tools.open_application('VS Code')['application'],'code')
        self.launch.assert_called_once_with([str(self.pdf.resolve())],shell=False,close_fds=True)
        self.assertTrue(self.tools.open_url('https://example.org/docs')['opened'])
        self.tools.url_opener.assert_called_once_with('https://example.org/docs',new=2,autoraise=True)
        with self.assertRaisesRegex(ValueError,'allowlist'):self.tools.open_application('PowerShell')
        with self.assertRaises(ValueError):self.tools.open_url('file:///secret')
        with self.assertRaises(ValueError):self.tools.open_url('https://user:pass@example.org')
        with self.assertRaisesRegex(ValueError,'Local network'):self.tools.open_url('http://router.local')

    def test_files_are_restricted_to_safe_types_and_configured_roots(self):
        self.assertTrue(self.tools.open_file(str(self.pdf))['opened'])
        self.opened.assert_called_once_with(str(self.pdf.resolve()))
        external=Path(self.tmp.name)/'outside.pdf';external.write_bytes(b'%PDF')
        with self.assertRaisesRegex(ValueError,'restricted'):self.tools.open_file(str(external))
        script=self.root/'run.ps1';script.write_text('Write-Host x')
        with self.assertRaisesRegex(ValueError,'Executable'):self.tools.open_file(str(script))
        folder=Path(self.tmp.name)/'elsewhere';folder.mkdir()
        with self.assertRaisesRegex(ValueError,'restricted'):self.tools.open_folder(str(folder))

    def test_foreground_reads_are_one_shot_and_screenshot_is_not_saved(self):
        self.assertEqual(self.tools.get_active_application(),{'application':'Code.exe'})
        self.assertEqual(self.tools.get_active_window()['title'],'Report review')
        self.assertEqual(self.tools.get_system_info()['platform'],'Windows')
        with self.assertRaisesRegex(ValueError,'transient'):self.tools.capture_screenshot()
        self.assertEqual(self.tools.set_volume(40),{'changed':True,'percent':40});self.volume.assert_called_once_with(40)
        with self.assertRaisesRegex(ValueError,'0 to 100'):self.tools.set_volume(140)

    def test_non_windows_host_fails_closed(self):
        tools=WindowsTools([self.root],platform_name='Linux',applications=self.apps)
        with self.assertRaisesRegex(ValueError,'unavailable on this platform'):tools.open_file(str(self.pdf))


if __name__=='__main__':unittest.main()
