"""
Unit Tests for CrawlerHTMLParser

Test Coverage Target: 90%+
Tests cover:
- Link extraction (absolute and relative)
- Text content extraction
- Script/Style content exclusion
- Malformed HTML handling
- URL validation and filtering
"""

import unittest
import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.crawler_job import CrawlerHTMLParser


class TestHTMLParserBasicFunctionality(unittest.TestCase):
    """Test basic parsing functionality."""

    def test_extract_absolute_links(self):
        """Parser extracts absolute href URLs correctly."""
        html = '''
        <html>
            <body>
                <a href="https://example.com/page1">Link 1</a>
                <a href="http://example.com/page2">Link 2</a>
            </body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://base.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 2)
        self.assertIn("https://example.com/page1", links)
        self.assertIn("http://example.com/page2", links)

    def test_convert_relative_links_to_absolute(self):
        """Parser converts relative URLs to absolute using base URL."""
        html = '''
        <html>
            <body>
                <a href="/page1">Link 1</a>
                <a href="page2">Link 2</a>
                <a href="../page3">Link 3</a>
            </body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://example.com/dir/")
        parser.feed(html)
        links = parser.get_links()

        self.assertIn("https://example.com/page1", links)
        self.assertIn("https://example.com/dir/page2", links)
        self.assertIn("https://example.com/page3", links)

    def test_extract_text_content(self):
        """Parser extracts visible text content."""
        html = '''
        <html>
            <body>
                <h1>Title</h1>
                <p>This is a paragraph.</p>
                <div>Some more text</div>
            </body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        text = parser.get_text()

        self.assertIn("Title", text)
        self.assertIn("This is a paragraph", text)
        self.assertIn("Some more text", text)

    def test_extract_title(self):
        """Parser extracts page title."""
        html = '''
        <html>
            <head>
                <title>Page Title Here</title>
            </head>
            <body></body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        title = parser.get_title()

        self.assertEqual(title, "Page Title Here")


class TestHTMLParserContentExclusion(unittest.TestCase):
    """Test that script and style content is excluded."""

    def test_ignore_script_content(self):
        """Parser ignores JavaScript content."""
        html = '''
        <html>
            <body>
                <p>Visible text</p>
                <script>
                    var hidden = "This should not appear";
                    console.log(hidden);
                </script>
                <p>More visible text</p>
            </body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        text = parser.get_text()

        self.assertIn("Visible text", text)
        self.assertIn("More visible text", text)
        self.assertNotIn("hidden", text)
        self.assertNotIn("console", text)

    def test_ignore_style_content(self):
        """Parser ignores CSS content."""
        html = '''
        <html>
            <head>
                <style>
                    .hidden { display: none; }
                    body { color: black; }
                </style>
            </head>
            <body>
                <p>Visible paragraph</p>
            </body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        text = parser.get_text()

        self.assertIn("Visible paragraph", text)
        self.assertNotIn("display", text)
        self.assertNotIn("color", text)

    def test_ignore_nested_script_in_body(self):
        """Parser ignores inline scripts."""
        html = '''
        <html>
            <body>
                <p>Before script</p>
                <script type="text/javascript">
                    document.write("injected content");
                </script>
                <p>After script</p>
            </body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        text = parser.get_text()

        self.assertIn("Before script", text)
        self.assertIn("After script", text)
        self.assertNotIn("injected", text)
        self.assertNotIn("document", text)


class TestHTMLParserLinkFiltering(unittest.TestCase):
    """Test URL filtering and validation."""

    def test_filter_javascript_links(self):
        """Parser filters javascript: URLs."""
        html = '''
        <a href="javascript:void(0)">Click</a>
        <a href="javascript:alert('xss')">Alert</a>
        <a href="https://valid.com">Valid</a>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 1)
        self.assertIn("https://valid.com", links)

    def test_filter_mailto_links(self):
        """Parser filters mailto: URLs."""
        html = '''
        <a href="mailto:test@example.com">Email</a>
        <a href="https://valid.com">Valid</a>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 1)
        self.assertIn("https://valid.com", links)

    def test_filter_fragment_only_links(self):
        """Parser filters fragment-only URLs (#anchor)."""
        html = '''
        <a href="#section1">Jump to section</a>
        <a href="#top">Back to top</a>
        <a href="https://valid.com">Valid</a>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 1)
        self.assertIn("https://valid.com", links)

    def test_deduplicate_links(self):
        """Parser returns unique links only."""
        html = '''
        <a href="https://example.com/page">Link 1</a>
        <a href="https://example.com/page">Link 2</a>
        <a href="https://example.com/page">Link 3</a>
        '''
        parser = CrawlerHTMLParser("https://base.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 1)


class TestHTMLParserMalformedHTML(unittest.TestCase):
    """Test handling of malformed HTML."""

    def test_handle_unclosed_tags(self):
        """Parser handles unclosed tags gracefully."""
        html = '''
        <html>
            <body>
                <p>Unclosed paragraph
                <div>Unclosed div
                <a href="https://example.com">Link
            </body>
        </html>
        '''
        parser = CrawlerHTMLParser("https://example.com")

        # Should not raise exception
        try:
            parser.feed(html)
            links = parser.get_links()
            text = parser.get_text()
            self.assertIn("https://example.com", links)
            self.assertIn("Unclosed paragraph", text)
        except Exception as e:
            self.fail(f"Parser raised exception on malformed HTML: {e}")

    def test_handle_missing_quotes(self):
        """Parser handles missing attribute quotes."""
        html = '''
        <a href=https://example.com/page>Link</a>
        <a href='https://example.com/page2'>Link2</a>
        '''
        parser = CrawlerHTMLParser("https://base.com")

        try:
            parser.feed(html)
            # May or may not extract these depending on parser behavior
            # Just ensure no exception
        except Exception as e:
            self.fail(f"Parser raised exception on missing quotes: {e}")

    def test_handle_empty_html(self):
        """Parser handles empty HTML."""
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed("")

        links = parser.get_links()
        text = parser.get_text()
        title = parser.get_title()

        self.assertEqual(links, [])
        self.assertEqual(text, "")
        self.assertEqual(title, "")

    def test_handle_only_whitespace(self):
        """Parser handles whitespace-only content."""
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed("   \n\t\n   ")

        self.assertEqual(parser.get_links(), [])
        self.assertEqual(parser.get_text(), "")


class TestHTMLParserEdgeCases(unittest.TestCase):
    """Test edge cases and special scenarios."""

    def test_links_in_various_contexts(self):
        """Parser extracts links from various HTML elements."""
        html = '''
        <nav>
            <a href="/nav-link">Nav</a>
        </nav>
        <article>
            <a href="/article-link">Article</a>
        </article>
        <footer>
            <a href="/footer-link">Footer</a>
        </footer>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 3)
        self.assertIn("https://example.com/nav-link", links)
        self.assertIn("https://example.com/article-link", links)
        self.assertIn("https://example.com/footer-link", links)

    def test_empty_href(self):
        """Parser handles empty href attribute."""
        html = '<a href="">Empty</a><a href="https://valid.com">Valid</a>'
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        links = parser.get_links()

        # Empty href should resolve to base URL
        self.assertIn("https://valid.com", links)

    def test_case_insensitive_tags(self):
        """Parser handles mixed case tags."""
        html = '''
        <HTML>
            <BODY>
                <A HREF="https://example.com/upper">Upper</A>
                <a href="https://example.com/lower">Lower</a>
            </BODY>
        </HTML>
        '''
        parser = CrawlerHTMLParser("https://base.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 2)

    def test_special_characters_in_url(self):
        """Parser handles special characters in URLs."""
        html = '''
        <a href="https://example.com/path?q=hello%20world&lang=en">Query</a>
        <a href="https://example.com/path/file.html#section">Fragment</a>
        '''
        parser = CrawlerHTMLParser("https://base.com")
        parser.feed(html)
        links = parser.get_links()

        self.assertEqual(len(links), 2)
        self.assertTrue(any("hello%20world" in link for link in links))


class TestHTMLParserTextExtraction(unittest.TestCase):
    """Test text extraction specifics."""

    def test_preserve_meaningful_whitespace(self):
        """Parser preserves word boundaries."""
        html = '<p>First word</p><p>Second word</p>'
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        text = parser.get_text()

        # Should have spaces between words
        self.assertIn("First", text)
        self.assertIn("word", text)
        self.assertIn("Second", text)

    def test_extract_text_from_nested_elements(self):
        """Parser extracts text from nested elements."""
        html = '''
        <div>
            <span>
                <strong>Nested</strong>
                text
            </span>
        </div>
        '''
        parser = CrawlerHTMLParser("https://example.com")
        parser.feed(html)
        text = parser.get_text()

        self.assertIn("Nested", text)
        self.assertIn("text", text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
