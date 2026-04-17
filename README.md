# Gradescope scraper (Python + Playwright)

This tool logs into Gradescope with a real browser session, discovers your visible courses/assignments, and downloads each available **Download Graded Copy** PDF into a local archive.

Default base URL is **`https://www.gradescope.ca`**. If you need another region/domain, pass `--base-url`.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Install Playwright browser binaries:
   ```powershell
   python -m playwright install chromium
   ```

## Usage

First run (interactive login and state capture):

```powershell
python -m scraper --out archive
```

If you only want to refresh auth state:

```powershell
python -m scraper --login-only
```

Headless rerun with saved session:

```powershell
python -m scraper --out archive --headless
```

Filter to specific course IDs:

```powershell
python -m scraper --course-id 12345 --course-id 67890
```

Force redownloads:

```powershell
python -m scraper --force
```

Use a non-Canadian domain explicitly:

```powershell
python -m scraper --base-url https://www.gradescope.com
```

Increase timeout for large files/slower network:

```powershell
python -m scraper --timeout-ms 180000 --max-retries 4
```

## Output layout

Artifacts are stored as:

`archive/<course>/<assignment>/<attempt>/<file>`

The manifest is written to `archive/manifest.json` (or `--manifest` path) and tracks downloaded files for resume/deduping.

## Notes and limitations

- Interactive login is expected for first run, including 2FA/CAPTCHA.
- Gradescope UI/DOM changes can break selectors over time.
- Graded-copy PDFs depend on instructor/course settings and may not exist for every assignment/submission.
- A single file failure no longer stops the full run; failed URLs are printed and the run continues.
- Use responsibly and respect your institution and platform terms.
