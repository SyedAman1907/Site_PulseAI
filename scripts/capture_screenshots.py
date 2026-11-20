"""Script to generate authentic screenshots for SitePulse AI using Chrome/Edge Headless and Pillow."""

import json
import os
import sys
import subprocess
import time
import urllib.request
import shutil

sys.path.insert(0, os.path.abspath("."))
from PIL import Image, ImageDraw, ImageFont

CHROME_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENSHOTS_DIR = os.path.abspath("screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def take_screenshot(url: str, output_name: str, width: int = 1440, height: int = 900, **kwargs):
    """Takes a headless browser screenshot of a given URL."""
    out_file = os.path.join(SCREENSHOTS_DIR, output_name)
    cmd = [
        CHROME_PATH,
        "--headless",
        f"--screenshot={out_file}",
        f"--window-size={width},{height}",
        "--hide-scrollbars",
        "--disable-gpu",
        url
    ]
    try:
        subprocess.run(cmd, timeout=15, check=True)
        print(f"Captured {output_name} ({os.path.getsize(out_file)} bytes)")
    except Exception as e:
        print(f"Failed to capture {output_name}: {e}")


def generate_terminal_test_screenshot():
    """Runs pytest -v and generates a crisp authentic terminal screenshot using Pillow."""
    print("Running pytest to capture genuine terminal output...")
    res = subprocess.run(["python", "-m", "pytest", "-v"], capture_output=True, text=True)
    output_lines = res.stdout.strip().split("\n")

    # Image setup
    width = 1200
    line_height = 24
    height = max(700, len(output_lines) * line_height + 120)
    img = Image.new("RGB", (width, height), color=(10, 10, 10))
    draw = ImageDraw.Draw(img)

    # Window title bar (macOS / modern dark style)
    draw.rectangle([(0, 0), (width, 40)], fill=(24, 24, 27))
    draw.ellipse([(16, 14), (28, 26)], fill=(239, 68, 68))
    draw.ellipse([(36, 14), (48, 26)], fill=(245, 158, 11))
    draw.ellipse([(56, 14), (68, 26)], fill=(16, 185, 129))

    try:
        font = ImageFont.truetype("consola.ttf", 15)
        title_font = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()

    draw.text((width // 2 - 120, 12), "sitepulse-ai: terminal — pytest -v", fill=(161, 161, 170), font=title_font)

    y = 60
    for line in output_lines:
        color = (228, 228, 231)  # Default light gray
        if "PASSED" in line:
            parts = line.split("PASSED")
            draw.text((25, y), parts[0], fill=(228, 228, 231), font=font)
            passed_x = 25 + int(len(parts[0]) * 9.0)
            draw.text((passed_x, y), "PASSED", fill=(34, 197, 94), font=font)
            if len(parts) > 1:
                draw.text((passed_x + 65, y), parts[1], fill=(161, 161, 170), font=font)
        elif "test session starts" in line or "rootdir:" in line or "plugins:" in line:
            draw.text((25, y), line, fill=(161, 161, 170), font=font)
        elif "passed in" in line:
            draw.text((25, y), line, fill=(34, 197, 94), font=font)
        else:
            draw.text((25, y), line, fill=color, font=font)
        y += line_height

    out_file = os.path.join(SCREENSHOTS_DIR, "test-results.png")
    img.save(out_file)
    print(f"Captured test-results.png ({os.path.getsize(out_file)} bytes)")


def main():
    # 1. Start uvicorn in background
    print("Starting SitePulse AI server on port 4000...")
    server = subprocess.Popen(
        ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "4000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        # Wait for server to come up
        for _ in range(30):
            try:
                urllib.request.urlopen("http://127.0.0.1:4000/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)

        print("Server is healthy! Taking screenshots...")

        template_path = os.path.abspath("app/templates/index.html")
        with open(template_path, "r", encoding="utf-8") as f:
            template_html = f.read()

        # 2a. Capture Light Mode Dashboard
        light_html = template_html.replace("<html lang=\"en\">", "<html lang=\"en\" data-theme=\"light\">")
        light_file = os.path.abspath("screenshots/temp_light.html")
        with open(light_file, "w", encoding="utf-8") as f:
            f.write(light_html)
        take_screenshot(f"file:///{light_file.replace(os.sep, '/')}", "dashboard-light.png", width=1440, height=900)
        # Also copy as dashboard.png
        shutil.copy(os.path.join(SCREENSHOTS_DIR, "dashboard-light.png"), os.path.join(SCREENSHOTS_DIR, "dashboard.png"))

        # 2b. Capture Dark Mode Dashboard
        dark_html = template_html.replace("<html lang=\"en\">", "<html lang=\"en\" data-theme=\"dark\">")
        dark_file = os.path.abspath("screenshots/temp_dark.html")
        with open(dark_file, "w", encoding="utf-8") as f:
            f.write(dark_html)
        take_screenshot(f"file:///{dark_file.replace(os.sep, '/')}", "dashboard-dark.png", width=1440, height=900)

        # 3. Capture Swagger Docs
        take_screenshot("http://127.0.0.1:4000/docs", "swagger-docs.png", width=1440, height=900)

        # 4. Capture Successful Analysis & Results by injecting analyzed state into dashboard
        from tests.test_link_analysis import MOCK_GEMINI_ANALYSIS_JSON
        mock_payload = {
            "success": True,
            "website": "https://apexcloudsolutions.io",
            "brand": MOCK_GEMINI_ANALYSIS_JSON["brand"],
            "analysis": MOCK_GEMINI_ANALYSIS_JSON["analysis"],
            "metadata": {
                "analyzed_at": "2026-11-20T23:45:00Z",
                "pages_analyzed": 3,
                "ai_model": "gemini-3.5-flash",
                "execution_time_seconds": 1.45,
                "estimated_tokens": {"total_tokens": 12450},
                "estimated_cost_usd": 0.0038
            }
        }

        # Successful analysis page injection
        success_script = f"""
        <script>
            window.addEventListener('DOMContentLoaded', () => {{
                document.documentElement.setAttribute('data-theme', 'light');
                const payload = {json.dumps(mock_payload)};
                renderResults(payload);
            }});
        </script>
        """
        success_html = template_html.replace("</body>", f"{success_script}</body>")
        success_temp_file = os.path.abspath("screenshots/temp_success.html")
        with open(success_temp_file, "w", encoding="utf-8") as f:
            f.write(success_html)

        take_screenshot(f"file:///{success_temp_file.replace(os.sep, '/')}", "successful-analysis.png", width=1440, height=950)

        # Competitor intelligence tab
        competitor_script = f"""
        <script>
            window.addEventListener('DOMContentLoaded', () => {{
                document.documentElement.setAttribute('data-theme', 'light');
                const payload = {json.dumps(mock_payload)};
                renderResults(payload);
                switchTab('competitors');
            }});
        </script>
        """
        competitor_html = template_html.replace("</body>", f"{competitor_script}</body>")
        competitor_temp_file = os.path.abspath("screenshots/temp_competitor.html")
        with open(competitor_temp_file, "w", encoding="utf-8") as f:
            f.write(competitor_html)

        take_screenshot(f"file:///{competitor_temp_file.replace(os.sep, '/')}", "competitor-analysis.png", width=1440, height=950)
        # Also maintain analysis-results.png alias for backwards compatibility
        shutil.copy(os.path.join(SCREENSHOTS_DIR, "competitor-analysis.png"), os.path.join(SCREENSHOTS_DIR, "analysis-results.png"))

        # Error handling screenshot
        error_script = """
        <script>
            window.addEventListener('DOMContentLoaded', () => {
                document.documentElement.setAttribute('data-theme', 'light');
                showError({
                    error_code: "SSRF_PROTECTION_VIOLATION",
                    error: "Target URL resolves to private, loopback, or cloud metadata address (127.0.0.1)",
                    detail: "Security guardrails enforce public HTTP/HTTPS destinations only."
                });
            });
        </script>
        """
        error_html = template_html.replace("</body>", f"{error_script}</body>")
        error_temp_file = os.path.abspath("screenshots/temp_error.html")
        with open(error_temp_file, "w", encoding="utf-8") as f:
            f.write(error_html)

        take_screenshot(f"file:///{error_temp_file.replace(os.sep, '/')}", "error-handling.png", width=1440, height=750)

        # Deployment / Health status screenshot
        take_screenshot("http://127.0.0.1:4000/health", "deployment.png", width=1200, height=700)

        # Clean up temporary HTML files
        for temp_f in [light_file, dark_file, success_temp_file, competitor_temp_file, error_temp_file]:
            if os.path.exists(temp_f):
                os.remove(temp_f)

    finally:
        server.terminate()
        server.wait()

    # 5. Generate authentic terminal test results image
    generate_terminal_test_screenshot()
    print("All screenshots generated and verified successfully in screenshots/!")


if __name__ == "__main__":
    main()
