import json
import requests

from datetime import datetime, timedelta, timezone
from flask import current_app
from typing import Any
from video2commons.frontend.shared import redisconnection


class WcqsSession:
    """This class manages WCQS sessions and executes SPARQL queries.

    Relevant Documentation:
        https://commons.wikimedia.org/wiki/Commons:SPARQL_query_service/API_endpoint
    """

    def __init__(self):
        self.session = requests.Session()
        self._set_cookies(self._get_cookies())

    def query(self, query: str):
        """Queries the Wikimedia Commons Query Service."""
        retry_after_ts = self._check_retry()
        if retry_after_ts:
            retry_after = int(
                (retry_after_ts - datetime.now(timezone.utc)).total_seconds()
            )
            raise RuntimeError(f"Too many requests, try again in {retry_after} seconds")

        # Make the SPARQL request using the provided query.
        response = self.session.get(
            "https://commons-query.wikimedia.org/sparql",
            params={"query": query},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "video2commons-bot/1.0 (https://video2commons.toolforge.org/)",
            },
            # Set-Cookie session refresh headers get sent with a 307 redirect.
            allow_redirects=True,
            timeout=30,
        )
        self._save_cookies()

        # Respect the rate limit status code and headers.
        #
        # https://wikitech.wikimedia.org/wiki/Robot_policy#Generally_applicable_rules
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After") or 60
            self._set_retry(int(retry_after))

            raise RuntimeError(f"Too many requests, try again in {retry_after} seconds")

        # Handle other unexpected response codes.
        content_type = response.headers.get("Content-Type")
        if (
            response.status_code < 200
            or response.status_code >= 300
            or content_type != "application/sparql-results+json;charset=utf-8"
        ):
            raise RuntimeError(
                f"Got unexpected response from SPARQL ({response.status_code}): {response.text}"
            )

        return response.json()

    def _check_retry(self):
        """Checks if we're rate limited before making SPARQL requests."""
        retry_after = redisconnection.get("wcqs:retry-after")

        if retry_after:
            retry_after_ts = datetime.fromisoformat(retry_after)
            if retry_after_ts > datetime.now(timezone.utc):
                return retry_after_ts

        return None

    def _set_retry(self, retry_after: int):
        """Updates retry-after value in Redis."""
        retry_after_ts = datetime.now(timezone.utc) + timedelta(seconds=retry_after)

        redisconnection.setex(
            "wcqs:retry-after",
            retry_after,
            retry_after_ts.replace(tzinfo=timezone.utc).isoformat(),
        )

    def _get_cookies(self) -> list[dict[str, Any]]:
        """Retrieve cookies from Redis or the filesystem."""
        cookies = redisconnection.get("wcqs:session")
        if cookies:
            return json.loads(cookies)

        current_app.logger.warning("Pulling in WCQS session from file as fallback")
        try:
            # Fallback: Pull in cookies from file. Needed for initial setup.
            with open("/data/project/video2commons/wcqs-session.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            raise RuntimeError("No WCQS session found in Redis or filesystem")

    def _set_cookies(self, cookies: list[dict[str, Any]]):
        """Load authentication cookies into the session."""
        cookie_dict = {(cookie["domain"], cookie["name"]): cookie for cookie in cookies}

        # wcqsOauth is a long lived cookie that wcqs uses to authenticate the
        # user against commons.wikimedia.org. This cookie is used to refresh
        # the wcqsSession cookie.
        wcqsOauth = cookie_dict.get(("commons-query.wikimedia.org", "wcqsOauth"))
        if wcqsOauth:
            self.session.cookies.set(
                name="wcqsOauth",
                value=wcqsOauth["value"],
                domain=wcqsOauth["domain"],
                path=wcqsOauth["path"],
                secure=wcqsOauth["secure"],
                expires=None,  # Intentional as wcqsOauth is long-lived
            )
        else:
            raise RuntimeError("wcqsOauth cookie not found")

        # wcqsSession is a short lived cookie (2 hour lifetime) holding a JWT
        # that grants query access to wcqs. This cookie is provided in a 307
        # redirect to any request that has a valid wcqsOauth cookie but no
        # valid wcqsSession cookie.
        wcqsSession = cookie_dict.get(("commons-query.wikimedia.org", "wcqsSession"))
        if wcqsSession:
            self.session.cookies.set(
                name="wcqsSession",
                value=wcqsSession["value"],
                domain=wcqsSession["domain"],
                path=wcqsSession["path"],
                secure=wcqsSession["secure"],
                expires=int(wcqsSession["expirationDate"]),
            )

    def _save_cookies(self):
        """Save cookies from the session to Redis."""
        cookies = [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expirationDate": cookie.expires,
                "secure": cookie.secure,
            }
            for cookie in self.session.cookies
        ]

        redisconnection.set("wcqs:session", json.dumps(cookies))
