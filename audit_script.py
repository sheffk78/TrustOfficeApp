import requests
from bs4 import BeautifulSoup
import random
import re
from datetime import datetime

# --- Configuration ---
BASE_DOMAIN = "https://truejoybirthing.com" # Assuming truejoybirthing.com is the base domain
SUPPORT_PATH = "/birth-support/"
NUM_CITIES = 3
SLUG_SOURCE = [
    "austin",
    "boston",
    "philadelphia",
    "sanfrancisco",
    "dallas",
    "seattle",
]

def check_city_page(slug: str):
    """Checks a single city page for status, title tag, and H1."""
    url = f"{BASE_DOMAIN}{SUPPORT_PATH}{slug}/"
    print(f"--- Checking URL: {url} ---")
    results = {"slug": slug, "url": url, "status": None, "title": None, "h1": "Not found", "valid": False}

    try:
        # Use an appropriate User-Agent to mimic a browser
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        results["status"] = response.status_code

        if response.status_code != 200:
            print(f"  [FAIL] Status Code: {response.status_code}. Not a 200 OK.")
            return results # Early exit if status is bad

        # Parse content for title and H1
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check Title Tag
        title_tag = soup.find('title')
        results["title"] = title_tag.get_text(strip=True) if title_tag else "Title tag missing"

        # Check H1 Tag
        h1_tag = soup.find('h1')
        if h1_tag:
            results["h1"] = h1_tag.get_text(strip=True)
        else:
            print("  [WARN] No H1 tag found.")

        # Basic validation check for expected patterns (This assumes "City Name" in Title/H1 and general content)
        title_match = re.search(r'\b\w+\s*\w*', results["title"], re.IGNORECASE)
        h1_match = re.search(r'The main guide to \w+', results["h1"], re.IGNORECASE) # Highly specific assumed pattern

        if title_match and h1_match:
             results["valid"] = True
        else:
            # If it returned 200 but the content looks generic or wrong, mark as a soft failure.
            results["valid"] = False

    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] An exception occurred during request: {e}")
        results["error"] = str(e)
    except Exception as e:
        print(f"  [CRITICAL ERROR] Unexpected error processing page: {e}")
        results["error"] = str(e)

    return results


def main():
    """Main execution function."""
    # Select 3 unique random slugs from the defined list
    unique_slugs = random.sample(SLUG_SOURCE, k=min(NUM_CITIES, len(SLUG_SOURCE)))

    print("\\n" + "="*50)
    print("CITY PAGE SEO & STATUS AUDIT REPORT".center(50))
    print(f"RUNNING ON {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(50))
    print("="*50 + "\\n")

    all_reports = []
    for slug in unique_slugs:
        report = check_city_page(slug)
        all_reports.append(report)

    # --- Final Summary Report ---
    print("\\n" + "="*70)
    print("FINAL AUDIT SUMMARY REPORT".center(70))
    print("="*70)

    failed_count = 0
    successful_slugs = []

    for report in all_reports:
        status_indicator = "✅ PASS" if report['valid'] and report['status'] == 200 else (f"❌ FAIL ({report['status']})" if report['status'] != 200 else "⚠️ ISSUE DETECTED")
        
        if not report['error']:
            print(f"\n[{status_indicator}] {report['slug'].upper()}")
            print(f"  URL: {report['url']}")
            print(f"  Status Code: {report['status'] if report['status'] else 'N/A'}")
            print(f"  <title>: {report['title'][:80]}...") 
            print(f"  H1: {report['h1'][:80]}")
        elif "❌ FAIL" in status_indicator:
             failed_count += 1
             print(f"\n[FAILURE] {report['slug'].upper()}")
             print(f"  URL: {report['url']}")
             print(f"  ERROR/Status Code: {report.get('status', 'N/A')}")
             print(f"  Reason: {report.get('error', 'Unknown error during request.')[:150]}")

        if report.get("valid") and report["status"] == 200:
            successful_slugs.append(report['slug'])


    summary = f"\\n\\n=== OVERALL CONCLUSION ===\n- Tested Pages: {len(all_reports)}\\n";
    if failed_count > 0:
        summary += f"- Total Failures (Non-200 or Bad Content): {failed_count}\n"
    else:
        summary += "- All tested pages returned status 200 and appeared to contain basic title/H1 tags.\n"
        
    if not successful_slugs:
         summary += "ACTION REQUIRED: No pages passed validation. Check the error logs above.\n"
    elif failed_count > 0:
         summary += f"WARNING: {len(successful_slugs)} pages passed status check, but {failed_count} pages require immediate review due to failed status or content mismatch.\n"
    else:
        summary += "Success. No obvious structural issues found on the tested slugs based on basic criteria.\n"

    print(summary)

if __name__ == "__main__":
    main()