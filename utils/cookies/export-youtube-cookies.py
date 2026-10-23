#!/usr/bin/env python3

"""Export YouTube session cookies in Netscape format using a headed browser."""

import os
import tempfile

from patchright.sync_api import Cookie, Playwright, sync_playwright

LOGIN_URL = (
    "https://accounts.google.com/ServiceLogin"
    "?service=youtube&passive=true"
    "&continue=https://www.youtube.com/"
)

# Using a fixed path instead of tempfile.mkdtemp() as the upload script
# needs to be able to locate it.
OUTPUT_FILE = "/tmp/youtube-cookies.txt"


def netscape_cookies(cookies: list[Cookie]) -> str:
    """Convert a list of cookie objects to a Netscape cookies.txt file."""

    lines = [
        "# Netscape HTTP Cookie File",
        "# https://curl.haxx.se/rfc/cookie_spec.html",
        "# This is a generated file! Do not edit.",
        "",
    ]

    for cookie in cookies:
        if not (domain := cookie.get("domain")):
            print(f"WARN: Skipping cookie with no domain: {cookie}")
            continue
        elif not (path := cookie.get("path")):
            print(f"WARN: Skipping cookie with no path: {cookie}")
            continue
        elif not (name := cookie.get("name")):
            print(f"WARN: Skipping cookie with no name: {cookie}")
            continue
        elif not (value := cookie.get("value")):
            print(f"WARN: Skipping cookie with no value: {cookie}")
            continue

        # Skip cookies that don't belong to YouTube, such as Google cookies.
        if domain != ".youtube.com":
            continue

        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if cookie.get("secure") else "FALSE"

        if (expiry := int(cookie.get("expires", -1))) < 0:
            expiry = 0

        lines.append(
            f"{domain}"
            f"\t{include_subdomains}"
            f"\t{path}"
            f"\t{secure}"
            f"\t{expiry}"
            f"\t{name}"
            f"\t{value}"
        )

    return "\n".join(lines) + "\n"


def interactively_login(playwright: Playwright) -> list[Cookie]:
    """Interactively log in to a Google/YouTube account and return cookies."""

    # Patchright requires launch_persistent_context to apply its anti-detection
    # patches, so a throwaway profile directory is needed.
    with tempfile.TemporaryDirectory() as user_data_dir:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            no_viewport=True,
        )

        try:
            page = context.new_page()
            page.goto(LOGIN_URL)

            input(
                "Instructions: Log in to your Google/YouTube account in the browser, "
                "then press [Enter] here to save your session cookies..."
            )

            return context.cookies()
        finally:
            context.close()


def main():
    with sync_playwright() as playwright:
        cookies = interactively_login(playwright)

    # Write the cookies using permissions that restrict other users from
    # reading the cookie file so if for whatever reason it doesn't get cleaned
    # up by the upload script it won't be accessible by anyone else.
    fd = os.open(OUTPUT_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

    with os.fdopen(fd, "w") as f:
        f.write(netscape_cookies(cookies))

        print(f"Wrote {len(cookies)} cookies to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
