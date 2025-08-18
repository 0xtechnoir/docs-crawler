# Docs Scraper

A simple, fast Python script for scraping technical documentation from websites and generating clean, formatted output perfect for NotebookLM or other AI ingestion.

## Features

- **Universal Compatibility**: Works with any documentation site that has a sitemap (GitBook, Docusaurus, ReadTheDocs, etc.)
- **Fast & Efficient**: Crawls documentation sites using sitemaps for optimal speed
- **Smart Content Extraction**: Automatically finds and extracts main content from various site structures
- **Clean Output**: Extracts only the essential content, removing navigation, ads, and other noise
- **Multiple Formats**: Generates markdown, HTML, and PDF outputs
- **NotebookLM Ready**: Creates clean markdown files perfect for AI documentation analysis
- **Preserves Structure**: Maintains the original sitemap order for logical document flow
- **Beautiful PDFs**: Professional formatting with Water.css styling

## Requirements

- Python 3.11+
- `uv` (for dependency management)
- pandoc (for HTML generation)
- weasyprint (for PDF generation)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd docs_scraper
   ```

2. **Install `uv` (if not already installed):**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Install pandoc (if not already installed):**
   ```bash
   # macOS
   brew install pandoc

   # Ubuntu/Debian
   sudo apt-get install pandoc

   # Windows
   # Download from https://pandoc.org/installing.html
   ```

## Usage

### Basic Usage

Run the scraper with your target documentation site:

```bash
uv run docs-crawler.py https://docs.example.com/
```

This will:
1. Crawl the specified site's sitemap (or fall back to crawling if no sitemap exists). Note - if no sitemap exists the ordering of pages with each section may not be correct.
2. Extract clean content from all pages
3. Generate three output files:
   - `doc_dump.md` - Clean markdown for NotebookLM
   - `doc_dump.html` - Beautiful HTML with Water.css styling
   - `doc_dump.pdf` - Professional PDF document

### Examples

```bash
# Scrape Cartridge documentation
uv run docs-crawler.py https://docs.cartridge.gg/

# Scrape any other documentation site
uv run docs-crawler.py https://docs.yom.net/

# Works with or without trailing slash
uv run docs-crawler.py https://docs.example.com
```

### Advanced Configuration

For advanced customization, you can still edit the configuration variables in `docs-crawler.py`:

```python
# ---------- CONFIG ----------
UA            = "Your-crawler-name/1.0"       # Customize user agent
OUT_FILE      = Path("your_output_name")      # Change output filename
CONCURRENCY   = 6                             # Adjust concurrent requests
MAX_RETRIES   = 3                             # Retry failed requests
TIMEOUT       = 30                            # Request timeout in seconds
# ----------------------------
```

### Output Files

- **`doc_dump.md`**: Clean markdown file perfect for importing into NotebookLM or other AI tools
- **`doc_dump.html`**: Beautifully formatted HTML file that can be opened in any browser
- **`doc_dump.pdf`**: Professional PDF document with proper styling and page breaks

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `base_url` | Base URL of the documentation site (command line argument) | Required |
| `UA` | User agent string for requests | `NotebookLM-prep-crawler/1.1` |
| `OUT_FILE` | Base name for output files | `doc_dump` |
| `CONCURRENCY` | Number of concurrent requests | `6` |
| `MAX_RETRIES` | Number of retries for failed requests | `3` |
| `TIMEOUT` | Request timeout in seconds | `30` |

## How It Works

1. **Sitemap Discovery**: Fetches and parses the sitemap.xml to discover all documentation pages
2. **Content Extraction**: Crawls each page and extracts clean content using BeautifulSoup
3. **Noise Removal**: Removes navigation, headers, footers, ads, and other non-content elements
4. **Markdown Conversion**: Converts HTML content to clean markdown format
5. **Format Generation**: Creates multiple output formats using pandoc and weasyprint

## Troubleshooting

### Import Errors
If you get import errors, make sure you're running the script with UV:
```bash
uv run docs-crawler.py
```

### PDF Generation Issues
If PDF generation fails, the script will still create the HTML file which you can open in a browser and print to PDF manually.

### Network Issues
If some pages fail to load, the script will continue with the successful pages and mark failed ones as "Failed to fetch."

## Dependencies

- **aiohttp**: Asynchronous HTTP client for fast crawling
- **beautifulsoup4**: HTML parsing and content extraction
- **markdownify**: HTML to markdown conversion
- **tqdm**: Progress bar display
- **weasyprint**: PDF generation from HTML
- **lxml**: Fast XML/HTML parsing

## License

This project is open source. Feel free to modify and distribute as needed.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Example Output

The script generates clean, structured documentation that looks like:

```markdown
# docs.yom.net — Snapshot (2025-08-01)

> Clean documentation content extracted from sitemap.

## Introduction | YOM Docs

**Source:** https://docs.yom.net

Gaming has transformed dramatically over the last decades...

## What is YOM? | YOM Docs

**Source:** https://docs.yom.net/manifesto/what-is-yom

YOM is at the forefront of decentralized cloud gaming...
```

Perfect for importing into NotebookLM or other AI documentation analysis tools!
