# X (Twitter) Login Castle Bypass
<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square" alt="Status: Active">
  <img src="https://img.shields.io/badge/Type-Reverse%20Engineering-blue?style=flat-square" alt="Type: Reverse Engineering">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License: MIT">
  <img src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white&style=flat-square" alt="Python">
  <a href="https://github.com/glizzykingdreko/x-twitter-login-castle-bypass"><img src="https://img.shields.io/github/stars/glizzykingdreko/x-twitter-login-castle-bypass?style=flat-square&logo=github" alt="GitHub stars"></a>
  <br />
</div>

<div align="center">
  <a href="https://takionapi.tech/"><img src="https://takionapi.tech/badge?text=Powered+by+TakionAPI&theme=dark" alt="TakionAPI"></a>
  <br />
</div>

Log into an X / Twitter account through the new JetFuel onboarding flow on `jf.x.com`, bypassing **Castle**. The antibot part is handled by [TakionAPI](https://takionapi.tech).

This is the working code behind my login flow reconstruction series, [Episode 1, Headers generation](https://takionapi.tech/blog/x-former-twitter-login-flow-reconstruction-episode-1-headers-generation) and [Episode 2, UI Metrics](https://takionapi.tech/blog/x-former-twitter-login-flow-reconstruction-episode-2-ui-metrics).

Check as well the [RockstarGames Castle bypass](https://github.com/glizzykingdreko/rockstargames-castle-bypass) for creating rockstar accounts.

## Table of Contents
- [Quick Start](#quick-start)
- [Important Notes](#important-notes)
- [How to Bypass Castle](#how-to-bypass-castle)
  - [The Castle Token](#the-castle-token)
  - [TLS Fingerprint Matching](#tls-fingerprint-matching)
  - [Session Fingerprinting](#session-fingerprinting)
  - [IP and Proxy Management](#ip-and-proxy-management)
- [Interacting with X](#interacting-with-x)
  - [The Guest Token](#the-guest-token)
  - [Headers](#headers)
  - [Login Flow](#login-flow)
  - [JetFuel Responses](#jetfuel-responses)
  - [X-Client-Transaction-Id and ui_metrics](#x-client-transaction-id-and-ui_metrics)
  - [What Comes After the Password](#what-comes-after-the-password)
- [TakionAPI Solution](#takionapi-solution)
  - [Getting an API Key](#getting-an-api-key)
  - [Generating Castle Tokens](#generating-castle-tokens)
  - [TLS Endpoint](#tls-endpoint)
- [FAQ](#faq)
- [Connect with me](#connect-with-me)

## Quick Start

Create a free account on the [TakionAPI Dashboard](https://takionapi.tech/trial) to start your trial and get your `TAKION_API_KEY`.

```bash
git clone https://github.com/glizzykingdreko/x-twitter-login-castle-bypass.git
cd x-twitter-login-castle-bypass
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, fill it in, drop your proxies into `proxies.txt` (one per line, `ip:port` or `ip:port:user:pass`), and run:

```bash
python x_login.py
```

Every script reads its account from `.env`, or you can pass it on the command line and skip the env entirely:

```bash
python x_login.py --username you@mail.com --password 'yourpass'
python x_login.py --username you@mail.com --password 'yourpass' --lang en-US --timezone America/New_York
```

## Important Notes

Everything runs on one client, [`takion_castle.py`](./takion_castle.py). It keeps the `__cuid` cookie, the cookie jar, the TLS fingerprint and the proxy pinned together for the whole session. This matters more than it looks: Castle scores the **session**, not the single request. Generate a token on one proxy and fire it from another, or swap the User-Agent halfway through, and you're flagged before X even reads your credentials.

I keep this repo up to date with changes to the login flow. Always refer to it for a working example.

## How to Bypass Castle

This part is general. It's about **Castle** on any site that uses it, not just X. If you're on a different Castle target the same ideas carry over, only the endpoints and the body change.

### The Castle Token

The whole thing hinges on one value, the Castle token. On X it rides inside the form body as `$castle_token`, on other Castle targets you'll find it in a header like `x-castle-request-token`. Either way it's an encrypted bundle of device and session signals that Castle scores server-side. You can't hand-craft it, it comes from the SDK running against a real, consistent session. And it's married to the `__cuid` cookie: generate the token without carrying the matching `__cuid` and Castle reads the two as two different devices. Give it credit, the session model is simple but effective.

### TLS Fingerprint Matching

Castle checks the **TLS fingerprint** of the connection. The site expects a real Chrome hello, so your client hello has to match the Chrome your `User-Agent` claims to be. Send a shiny Chrome 151 UA over a plain Python `requests` stack and the JA3/JA4 won't line up, and you're scored before the form is even submitted. Obv Python's TLS won't fake a real Chrome on its own.

This example pins `client_hello="chrome151"` and lets TakionAPI's TLS layer produce the matching fingerprint. Want to check yours? Hit `https://tls.peet.ws/api/all` through the same client:

```python
response = solver.get("https://tls.peet.ws/api/all").json()
print(f"JA4: {response['tls']['ja4']}")
print(f"JA3: {response['tls']['ja3_hash']}")
```

### Session Fingerprinting

Castle doesn't grade one request in isolation, it builds a profile over the session:

- **Device consistency**, the same TLS, UA and `__cuid` on every request
- **Token freshness**, a token generated for this session and this proxy, not a recycled one
- **Header ordering**, headers in the exact order the browser sends them
- **Cookie continuity**, the guest cookies you pick up on the first page load have to travel with the rest of the flow

Change the UA mid-session or reorder the headers and it's flagged instantly. Consistency is the whole game.

### IP and Proxy Management

Castle is strict on IP reputation. Once an IP is dirty the session gets refused before your credentials are even read. So:

- **Different proxy per session**, never reuse a burnt IP
- **Generation lock**, the proxy you generate the token on is the proxy you send the request from
- **Residential or mobile**, not datacenter

The example flags a refused session with `[BLOCKED]` and tells you to rotate. Retrying on the same proxy just hands you the same refusal, so don't bother.

## Interacting with X

### The Guest Token

Before the login form does anything, the page needs a **guest token**. In [Episode 1](https://takionapi.tech/blog/x-former-twitter-login-flow-reconstruction-episode-1-headers-generation) I minted it the direct way, a `POST https://api.x.com/1.1/guest/activate.json`. Here I take the cheaper route: load `https://x.com/` and X hands you a `guest_id` cookie and embeds the guest token in the HTML as `gt=<digits>`, mirrored into a `gt` cookie, so one page load gets you both. Every onboarding call after that carries it in the `x-guest-token` header. No guest token, no onboarding, so step 1 of the example does nothing but load the homepage and read those two out.

### Headers

The JetFuel onboarding XHRs share one header set. A few carry the weight:

```json
{
    "authorization": "Bearer AAAAAAAA...<the public web app bearer>",
    "x-guest-token": "<from the homepage>",
    "x-jf-v": "JP-5",
    "x-jf-client-theme": "dark",
    "x-twitter-active-user": "yes",
    "x-twitter-client-language": "en-GB"
}
```

I reversed this whole header set in [Episode 1, Headers generation](https://takionapi.tech/blog/x-former-twitter-login-flow-reconstruction-episode-1-headers-generation), the full study and its Python module are in [twitter-generator](https://github.com/glizzykingdreko/twitter-generator) ([LEARN.md](https://github.com/glizzykingdreko/twitter-generator/blob/main/LEARN.md)). The `authorization` Bearer is not a secret, it ships in x.com's own JavaScript and it's identical for every session, the real per-session auth is the guest token plus the Castle token. Order matters though. Castle reads header order as part of the fingerprint, so keep it exactly as the example sends it, don't sort it. This is also why `user-agent` and `sec-ch-ua` live inline in the header builder instead of some constant at the top of the file, the browser identity belongs right there in the headers you're reading.

### Login Flow

Login is a short walk on one session:

```
homepage (guest token) -> onboarding warmup -> begin_login ($castle_token) -> login_enter_password ($castle_token)
```

`begin_login` takes the username and the first Castle token and answers with a `session_token`. `login_enter_password` takes the password, that `session_token` and a fresh Castle token, and on a clean pass X drops the `auth_token` cookie, which is the logged-in session. A wrong password comes back with an error string and no `auth_token`, which means the bypass worked and the account just didn't match. See [`x_login.py`](./x_login.py).

### JetFuel Responses

Here's the X-specific twist. The `jf.x.com/onboarding/web` endpoints don't answer JSON, they answer **JetFuel**, a binary stream of length-prefixed frames carrying varint-length key/value pairs. There's no schema in the response, so [`jetfuel.py`](./jetfuel.py) doesn't decode the whole thing, it scans the bytes for the handful of keys the flow needs (`session_token`, `errors`, `missing_account`) and reads the value that follows each one, plus the `/onboarding/web/actions/...` path that names the next subtask.

```python
import jetfuel

result = jetfuel.parse_response(response.content)
# {"session_token": "...", "next_action": "/onboarding/web/actions/login_enter_password", "error_message": None}
```

A missing account isn't returned as an error string, it comes back under its own `missing_account` key, so the parser surfaces it as `user_not_found:<handle>` rather than letting `begin_login` look like it silently gave nothing back.

### X-Client-Transaction-Id and ui_metrics

If you've read the blog series you're waiting for these two, so here's where they sit. The classic X automation path goes through `https://api.x.com/1.1/onboarding/task.json`, and that endpoint asks for both:

- **`x-client-transaction-id`** on every request, the whole of [Episode 1, Headers generation](https://takionapi.tech/blog/x-former-twitter-login-flow-reconstruction-episode-1-headers-generation). Full study and Python module in [twitter-generator](https://github.com/glizzykingdreko/twitter-generator).
- **`ui_metrics`**, the subject of [Episode 2, UI Metrics](https://takionapi.tech/blog/x-former-twitter-login-flow-reconstruction-episode-2-ui-metrics). During a username check the response carries a `LoginJSInstrumentationSubtask`, which tells the SDK to load and run the obfuscated script at `https://twitter.com/i/js_inst?c_name=ui_metrics`. That script does some bitwise math over a handful of numeric variables and writes a hidden `ui_metrics` input holding a JSON `{rf, s}`, the `rf` computed values and the `s` static signature. I solved it in Node, Go and Python in [x-twitter-ui-metrics](https://github.com/glizzykingdreko/x-twitter-ui-metrics).

The `x-client-transaction-id` from Episode 1 is a hash over the request method and path, a fingerprint read off a `twitter-site-verification` meta tag and the animation of a dynamic `ondemand.s` script, and the current timestamp:

```python
def _generate_transaction_id(self, method: str, path: str) -> str:
    time_now = floor((time() * 1000 - 1682924400000) / 1000)
    time_now_bytes = [(time_now >> (i * 8)) & 0xFF for i in range(4)]
    hash_val = sha256(f"{method}!{path}!{time_now}obfiowerehiring{self.animation_key}".encode()).digest()
    random_num = randint(0, 255)
    bytes_arr = [*self.key_bytes, *time_now_bytes, *list(hash_val)[:16], 3]
    return b64encode(bytearray([random_num, *[b ^ random_num for b in bytes_arr]])).decode().rstrip("=")
```

This example takes the newer JetFuel route on `jf.x.com` instead, where the Castle token carries the signal load and the flow doesn't send an `x-client-transaction-id` or a `ui_metrics` field, so it isn't wired in here on purpose, adding a header the real JetFuel client never sends is just one more thing for Castle to notice. If you're building on the `task.json` flow, that's where the two generators go.

### What Comes After the Password

A password login that lands the `auth_token` cookie is done. If instead the password is accepted but no `auth_token` shows up, the account has another subtask left, 2FA, an ACID email/phone check, a captcha step, and the JetFuel response names it in `next_action`. Each one is answered the same way, a fresh Castle token on the same session posted against that action path, so the example prints the `next_action` and hands you the thread to keep pulling.

## TakionAPI Solution

![TakionAPI](assets/castle.png)

Unless you want to start deobfuscating Castle, understanding it, and, the annoying part, keeping it up to date every time it changes, we at [TakionAPI](https://takionapi.tech) already do that for you. Same for the TLS client, which goes stale the moment Chrome ships a new hello. You focus on your business logic, we handle the bypass.

[`takion_castle.py`](./takion_castle.py) is the whole client, ready to drop in.

- [TakionAPI Docs](https://docs.takionapi.tech)
- [TakionAPI Trial](https://dashboard.takionapi.tech)
- [TakionAPI Discord](https://takionapi.tech/discord) for custom development and support.

### Getting an API Key

Start with a free trial at [takionapi.tech](https://takionapi.tech/demo) to get a key with some tokens in it. Nothing more than an email required, run your tests and reach out for anything.

### Generating Castle Tokens

```bash
curl -X GET 'https://castle.takionapi.tech/generate?website=twitter&api_key=TAKION_API_XXX'
```

Or with the included client, which keeps the returned `__cuid` synced to the cookie jar for you:

```python
from takion_castle import TakionCastle

solver = TakionCastle("TAKION_API_XXX", "ip:port:user:pass", client_hello="chrome151")
token = solver.generate_token("twitter")
```

### TLS Endpoint

The same client sends TLS-matched requests through Castle's TLS layer, so the fingerprint stays correct and the cookie jar rides along automatically:

```python
response = solver.get(
    "https://x.com/",
    headers={...},
)
print(response.status_code, response.text[:100])
```

That's it. Now go build the actual thing.

## FAQ

> begin_login or the password call comes back refused, what's wrong?

That's Castle refusing the session, not a bad password. The IP is flagged. Rotate to a clean proxy and make sure the token was generated on the same proxy you send from.

> The password is accepted but I never get an auth_token.

The account has another subtask (2FA, an ACID check, a captcha). Read [What Comes After the Password](#what-comes-after-the-password), the `next_action` in the JetFuel response tells you which one, and you answer it on the same session with a fresh Castle token.

> Do I need the x-client-transaction-id or ui_metrics from the blog posts?

Not for this flow. Those belong to the `api.x.com/1.1/onboarding/task.json` path. The JetFuel `jf.x.com` flow this example uses leans on the Castle token instead. See [X-Client-Transaction-Id and ui_metrics](#x-client-transaction-id-and-ui_metrics).

> Can I use another Python TLS library?

Only if it produces the exact JA4/JA3 a real Chrome does, and most are too outdated for that. Use TakionAPI's TLS endpoint if you want to be sure.

> The response looks like garbage bytes, not JSON.

That's JetFuel, X's binary onboarding format. Don't `.json()` it, pass `response.content` to `jetfuel.parse_response`. See [JetFuel Responses](#jetfuel-responses).

> I'm on a different Castle-protected site, do you support it?

Change the `website` parameter and you're most of the way there. Not sure about your target's flow? Hit me on Discord.

## Connect with me

If you found this project helpful or interesting, consider starring the repo and following me for more security research and tools, or buy me a coffee to keep me up

<p align="center">
  <a href="https://github.com/GlizzyKingDreko"><img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"></a>
  <a href="https://twitter.com/GlizzyKingDreko"><img src="https://img.shields.io/badge/Twitter-1DA1F2?style=for-the-badge&logo=twitter&logoColor=white" alt="Twitter"></a>
  <a href="https://medium.com/@GlizzyKingDreko"><img src="https://img.shields.io/badge/Medium-12100E?style=for-the-badge&logo=medium&logoColor=white" alt="Medium"></a>
  <a href="https://discord.com/users/GlizzyKingDreko"><img src="https://img.shields.io/badge/Discord-7289DA?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="mailto:glizzykingdreko@protonmail.com"><img src="https://img.shields.io/badge/ProtonMail-8B89CC?style=for-the-badge&logo=protonmail&logoColor=white" alt="Email"></a>
  <a href="https://buymeacoffee.com/glizzykingdreko"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-yellow?style=for-the-badge&logo=buy-me-a-coffee&logoColor=white" alt="Buy Me a Coffee"></a>
</p>
