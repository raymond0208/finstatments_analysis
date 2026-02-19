"""
Validation tests for repository review.
Tests code logic that can be exercised without external API keys.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# --- Tests for get_10k_base.py ---

class TestSecReportFetcher(unittest.TestCase):
    """Tests for SecReportFetcher class."""

    @patch.dict(os.environ, {"FMP_API_KEY": "test_key"})
    def test_init_with_api_key(self):
        """SecReportFetcher initializes when FMP_API_KEY is set."""
        from get_10k_base import SecReportFetcher
        fetcher = SecReportFetcher()
        self.assertEqual(fetcher.fmp_api_key, "test_key")

    @patch.dict(os.environ, {}, clear=True)
    def test_init_without_api_key_raises(self):
        """SecReportFetcher raises ValueError when FMP_API_KEY is missing."""
        # Need to reload module to re-execute __init__ check
        if 'get_10k_base' in sys.modules:
            del sys.modules['get_10k_base']
        from get_10k_base import SecReportFetcher
        with self.assertRaises(ValueError):
            SecReportFetcher()

    @patch.dict(os.environ, {"FMP_API_KEY": "test_key"})
    @patch('get_10k_base.requests.get')
    def test_get_sec_report_http_error(self, mock_get):
        """get_sec_report returns error string on HTTP failure (design issue)."""
        mock_get.return_value = MagicMock(status_code=404)
        from get_10k_base import SecReportFetcher
        fetcher = SecReportFetcher()
        result = fetcher.get_sec_report("AAPL", "2024")
        self.assertIn("Failed to retrieve data", result)
        # NOTE: This is the design issue — returns string instead of raising

    @patch.dict(os.environ, {"FMP_API_KEY": "test_key"})
    @patch('get_10k_base.requests.get')
    def test_get_sec_report_no_matching_year(self, mock_get):
        """get_sec_report returns 'No matching report found' for bad year."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"fillingDate": "2023-03-01", "finalLink": "http://example.com/report"}]
        )
        from get_10k_base import SecReportFetcher
        fetcher = SecReportFetcher()
        result = fetcher.get_sec_report("AAPL", "2020")
        self.assertEqual(result, "No matching report found")

    @patch.dict(os.environ, {"FMP_API_KEY": "test_key"})
    @patch('get_10k_base.requests.get')
    def test_get_sec_report_success(self, mock_get):
        """get_sec_report returns Link and Filing Date on success."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"fillingDate": "2024-03-01", "finalLink": "http://example.com/10k"}]
        )
        from get_10k_base import SecReportFetcher
        fetcher = SecReportFetcher()
        result = fetcher.get_sec_report("AAPL", "2024")
        self.assertIn("Link:", result)
        self.assertIn("http://example.com/10k", result)


# --- Tests for analyze_BS_w_param.py (function-level, no module-level import) ---

class TestCombinePrompt(unittest.TestCase):
    """Tests for combine_prompt function."""

    def setUp(self):
        """Import combine_prompt by patching env vars to avoid module-level crash."""
        self.env_patcher = patch.dict(os.environ, {
            "SEC_API_KEY": "test_sec_key",
            "FMP_API_KEY": "test_fmp_key",
        })
        self.env_patcher.start()
        # Must patch ExtractorApi before importing
        self.extractor_patcher = patch('sec_api.ExtractorApi')
        self.extractor_patcher.start()
        if 'analyze_BS_w_param' in sys.modules:
            del sys.modules['analyze_BS_w_param']
        from analyze_BS_w_param import combine_prompt
        self.combine_prompt = combine_prompt

    def tearDown(self):
        self.env_patcher.stop()
        self.extractor_patcher.stop()

    def test_with_table(self):
        result = self.combine_prompt("analyze this", "10k section text", "Balance: $100")
        self.assertIn("Balance: $100", result)
        self.assertIn("Resource: 10k section text", result)
        self.assertIn("Instruction: analyze this", result)

    def test_without_table(self):
        result = self.combine_prompt("analyze this", "10k section text", None)
        self.assertNotIn("None", result)
        self.assertIn("Resource: 10k section text", result)

    def test_empty_table_string_treated_as_no_table(self):
        """Empty string is falsy, so it should behave like None."""
        result = self.combine_prompt("analyze", "resource", "")
        self.assertNotIn("Balance", result)


class TestSaveToFile(unittest.TestCase):
    """Tests for save_to_file function."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "SEC_API_KEY": "test_sec_key",
            "FMP_API_KEY": "test_fmp_key",
        })
        self.env_patcher.start()
        self.extractor_patcher = patch('sec_api.ExtractorApi')
        self.extractor_patcher.start()
        if 'analyze_BS_w_param' in sys.modules:
            del sys.modules['analyze_BS_w_param']
        from analyze_BS_w_param import save_to_file
        self.save_to_file = save_to_file

    def tearDown(self):
        self.env_patcher.stop()
        self.extractor_patcher.stop()

    def test_save_creates_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            path = f.name
        try:
            self.save_to_file("test content", path)
            with open(path) as f:
                self.assertEqual(f.read(), "test content")
        finally:
            os.unlink(path)

    def test_save_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "output.txt")
            self.save_to_file("nested content", path)
            with open(path) as f:
                self.assertEqual(f.read(), "nested content")


class TestLstripBug(unittest.TestCase):
    """Demonstrates the lstrip bug identified in the review."""

    def test_lstrip_strips_characters_not_substring(self):
        """This proves the lstrip bug: it strips individual chars, not the prefix."""
        # Simulating what the code does
        report_address = "Link: https://www.sec.gov/Archives/edgar/data/123/10k.htm"
        result = report_address.lstrip("Link: ")
        # lstrip("Link: ") strips any char in {'L','i','n','k',':',' '} from the left
        # "https" — 'h' is not in the set, so stripping stops at 'h'
        # In THIS case it happens to work because 'h' isn't in the strip set.
        # But consider a URL starting with a character in the set:
        bad_address = "Link: insurance-data.sec.gov/report"
        bad_result = bad_address.lstrip("Link: ")
        # 'i', 'n' are in the strip set, so "insurance" gets mangled
        self.assertNotEqual(bad_result, "insurance-data.sec.gov/report")
        # The correct approach:
        correct_result = bad_address.removeprefix("Link: ")
        self.assertEqual(correct_result, "insurance-data.sec.gov/report")

    def test_removeprefix_is_correct(self):
        """removeprefix() removes the exact substring."""
        report_address = "Link: https://www.sec.gov/report"
        result = report_address.removeprefix("Link: ")
        self.assertEqual(result, "https://www.sec.gov/report")


class TestSectionValidation(unittest.TestCase):
    """Tests for section validation in get_10k_section."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "SEC_API_KEY": "test_sec_key",
            "FMP_API_KEY": "test_fmp_key",
        })
        self.env_patcher.start()
        self.extractor_patcher = patch('sec_api.ExtractorApi')
        self.extractor_patcher.start()
        if 'analyze_BS_w_param' in sys.modules:
            del sys.modules['analyze_BS_w_param']
        from analyze_BS_w_param import get_10k_section
        self.get_10k_section = get_10k_section

    def tearDown(self):
        self.env_patcher.stop()
        self.extractor_patcher.stop()

    def test_invalid_section_raises(self):
        with self.assertRaises(ValueError):
            self.get_10k_section("AAPL", "2024", "99")

    def test_valid_sections_accepted(self):
        """Valid sections should not raise ValueError (they'll fail on API call instead)."""
        valid_sections = ["1", "1A", "1B", "2", "7", "7A", "8", "9A", "9B", "10", "15"]
        for section in valid_sections:
            try:
                # Will fail at API call stage, but should NOT fail at validation
                self.get_10k_section("AAPL", "2024", section)
            except ValueError:
                self.fail(f"Section '{section}' should be valid but raised ValueError")
            except Exception:
                pass  # Expected — no real API connection

    def test_int_section_converted(self):
        """Integer section should be converted to string and accepted."""
        try:
            self.get_10k_section("AAPL", "2024", 7)
        except ValueError:
            self.fail("Integer section 7 should be valid")
        except Exception:
            pass  # Expected — no real API connection


class TestSilentErrorPropagation(unittest.TestCase):
    """Demonstrates how error strings flow silently through the pipeline."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "SEC_API_KEY": "test_sec_key",
            "FMP_API_KEY": "test_fmp_key",
        })
        self.env_patcher.start()
        self.extractor_patcher = patch('sec_api.ExtractorApi')
        self.extractor_patcher.start()
        if 'analyze_BS_w_param' in sys.modules:
            del sys.modules['analyze_BS_w_param']
        from analyze_BS_w_param import get_10k_section
        self.get_10k_section = get_10k_section

    def tearDown(self):
        self.env_patcher.stop()
        self.extractor_patcher.stop()

    @patch('get_10k_base.requests.get')
    def test_http_error_flows_as_section_text(self, mock_get):
        """When FMP API returns 404, the error string becomes 'section text'."""
        mock_get.return_value = MagicMock(status_code=500)
        # This returns an error message AS IF it were valid section text
        result = self.get_10k_section("AAPL", "2024", "7")
        self.assertIn("Failed to retrieve data", result)
        # This is the bug — caller has no way to know this is an error


if __name__ == "__main__":
    unittest.main(verbosity=2)
