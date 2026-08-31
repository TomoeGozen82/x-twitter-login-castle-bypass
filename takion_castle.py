import urllib.parse
from http.cookies import SimpleCookie

import requests
from requests.cookies import RequestsCookieJar
from requests.models import Response

GENERATE_URL = "https://castle.takionapi.tech/generate"
TLS_URL = "https://castle.takionapi.tech/tls"


def proxy_url(proxy: str) -> str:
    value = (proxy or "").strip()
    if "://" in value:
        return value
    parts = value.split(":")
    # host:port:user:pass is checked before the "@" form because a password may itself
    # contain an "@", and testing for "@" first passes the whole thing through unparsed.
    if len(parts) >= 4 and "@" not in ":".join(parts[:3]):
        host, port, user = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])
        user = urllib.parse.quote(user, safe="")
        password = urllib.parse.quote(password, safe="")
        return f"http://{user}:{password}@{host}:{port}"
    if "@" in value:
        return f"http://{value}"
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    raise ValueError(f"Unsupported proxy format: {value}")


def normalize_proxy(proxy: str) -> str:
    value = (proxy or "").strip()
    if not value:
        return value
    if "://" in value:
        value = value.split("://", 1)[1]
    if "@" in value:
        credentials, host_port = value.split("@", 1)
        user, _, password = credentials.partition(":")
        host, _, port = host_port.partition(":")
        return f"{host}:{port}:{user}:{password}"
    return value


class TakionCastle:
    # One instance is one browser session. The __cuid cookie, the cookie jar, the TLS
    # fingerprint and the proxy stay pinned together, Castle scores the session and not the
    # single request.
    def __init__(self, api_key: str, proxy: str = False, client_hello: str = "chrome151") -> None:
        self.api_key = api_key
        self.proxy = normalize_proxy(proxy) if proxy else False
        self.client_hello = client_hello
        self.cookiejar = RequestsCookieJar()
        self.cuid = None

    def set_proxy(self, proxy: str) -> None:
        self.proxy = normalize_proxy(proxy) if proxy else False

    def generate_token(self, website: str = "twitter", tries: int = 4) -> str:
        params = {
            "website": website,
            "api_key": self.api_key,
        }
        # Carry the __cuid the session already has so the token and the cookie describe the
        # same device. The first call has none yet, the service mints one and hands it back.
        if self.cuid:
            params["__cuid"] = self.cuid
        # The service now and then answers with a transient generation error, retry a few
        # times before giving up so one hiccup doesn't derail the whole run.
        last_error = None
        for _ in range(tries):
            response = requests.get(
                GENERATE_URL,
                params=params,
                timeout=30,
            )
            data = response.json()
            # The service can hand back a different __cuid. The cookie and the token have to
            # keep matching or Castle reads the two as separate devices.
            if cuid := data.get("__cuid"):
                self.cuid = cuid
                self.cookiejar.set("__cuid", cuid)
                params["__cuid"] = cuid
            token = data.get("token")
            if token:
                return token
            last_error = data.get("error") or f"empty token [{response.status_code}]"
        raise RuntimeError(f"/generate failed: {last_error}")

    def _store_cookies(self, headers: dict) -> None:
        set_cookie = headers.get("Set-Cookie")
        if not set_cookie:
            return
        if isinstance(set_cookie, list):
            set_cookies = set_cookie
        elif isinstance(set_cookie, str):
            set_cookies = [set_cookie]
        else:
            set_cookies = [str(set_cookie)]

        for cookie_header in set_cookies:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            for key, morsel in cookie.items():
                self.cookiejar.set(
                    key,
                    morsel.value,
                    domain=morsel["domain"] or "",
                    path=morsel["path"] or "/",
                )

    def _cookie_header(self) -> str:
        cookies = [f"{cookie.name}={cookie.value}" for cookie in self.cookiejar]
        return "; ".join(cookies) if cookies else ""

    def _send_request(
        self,
        method: str,
        url: str,
        headers: dict = None,
        json: dict = None,
        data: str = None,
        params: dict = None,
        allow_redirects: bool = None,
    ) -> Response:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

        headers = headers.copy() if headers else {}
        cookie_header = self._cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header

        payload = {
            "verify": False,
            "http2": True,
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "data": data,
            "proxy": self.proxy,
            "params": params,
        }
        if self.client_hello:
            payload["client_hello"] = self.client_hello
        if allow_redirects is not None:
            payload["allow_redirects"] = allow_redirects

        tls_response = requests.post(
            TLS_URL,
            json=payload,
            headers={"X-API-Key": self.api_key},
            timeout=90,
        ).json()
        if error := tls_response.get("error"):
            raise RuntimeError(f"/tls failed: {error}")

        response = Response()
        response.status_code = tls_response.get("status_code", 0)
        response.headers = tls_response.get("headers", {})
        response.encoding = "utf-8"
        # X's onboarding endpoints answer binary JetFuel, keep the bytes intact for jetfuel.py.
        response._content = tls_response.get("body", "").encode("latin-1", errors="ignore")

        self._store_cookies(response.headers)
        response.cookies = self.cookiejar.copy()
        return response

    def get(self, url: str, headers: dict = None, params: dict = None, allow_redirects: bool = None) -> Response:
        return self._send_request("GET", url, headers, params=params, allow_redirects=allow_redirects)

    def post(self, url: str, headers: dict = None, json: dict = None, data: str = None, params: dict = None, allow_redirects: bool = None) -> Response:
        return self._send_request("POST", url, headers, json, data, params, allow_redirects=allow_redirects)

    def put(self, url: str, headers: dict = None, json: dict = None, data: str = None, params: dict = None) -> Response:
        return self._send_request("PUT", url, headers, json, data, params)

    def patch(self, url: str, headers: dict = None, json: dict = None, data: str = None, params: dict = None) -> Response:
        return self._send_request("PATCH", url, headers, json, data, params)

    def delete(self, url: str, headers: dict = None, json: dict = None, data: str = None, params: dict = None) -> Response:
        return self._send_request("DELETE", url, headers, json, data, params)
