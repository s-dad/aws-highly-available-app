#!/usr/bin/env python3
"""SafeClick v0: a small website safety checker.

Uses only the Python standard library, so a fresh EC2 instance can start it
from user data in seconds with nothing to install. Compatible with the
Python 3.9 that ships with Amazon Linux 2023.
"""
import html
import http.client
import ipaddress
import json
import os
import socket
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TIMEOUT = 5
MAX_URL_LENGTH = 2048
USER_AGENT = "SafeClick/0.1 (website safety checker)"

SECURITY_HEADERS = [
    ("strict-transport-security", "HSTS", True,
     "Tells browsers to always use HTTPS, so the connection can't be quietly downgraded."),
    ("content-security-policy", "Content Security Policy", True,
     "Limits where scripts can load from, which blocks many cross-site scripting attacks."),
    ("x-frame-options", "X-Frame-Options", False,
     "Stops other sites from hiding this page inside a frame to trick you into clicking (clickjacking)."),
    ("x-content-type-options", "X-Content-Type-Options", False,
     "Stops the browser from guessing file types, which attackers can abuse."),
    ("referrer-policy", "Referrer-Policy", False,
     "Controls how much of your browsing path is shared with other sites."),
    ("permissions-policy", "Permissions-Policy", False,
     "Limits access to features like the camera, microphone, and location."),
]


class ScanError(Exception):
    """A problem with the link the user entered, safe to show to the user."""


# ---------------------------------------------------------------- instance info

def get_instance_info():
    """Return (instance_id, availability_zone) from EC2 metadata (IMDSv2)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = "http://169.254.169.254/latest"
    try:
        token_req = urllib.request.Request(
            base + "/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"})
        token = opener.open(token_req, timeout=1).read().decode()

        def meta(path):
            req = urllib.request.Request(
                base + "/meta-data/" + path,
                headers={"X-aws-ec2-metadata-token": token})
            return opener.open(req, timeout=1).read().decode()

        return meta("instance-id"), meta("placement/availability-zone")
    except Exception:
        return "local-dev", "local"


# ---------------------------------------------------------------- validation

def resolve_target(raw):
    """Validate a user-supplied link and resolve it to one public IPv4 address.

    Blocks private, loopback, link-local (including the EC2 metadata service
    at 169.254.169.254), and other non-public addresses so the scanner can't
    be used to probe the network it runs in (SSRF protection). Returns
    (hostname, ip). The scan then connects to that exact IP, so a second DNS
    lookup can't swap in an internal address (DNS rebinding).
    """
    raw = (raw or "").strip()
    if not raw:
        raise ScanError("Enter a link to scan.")
    if len(raw) > MAX_URL_LENGTH:
        raise ScanError("That link is too long.")
    if "://" not in raw:
        raw = "https://" + raw

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ScanError("Only http and https links can be scanned.")
    host = parsed.hostname
    if not host:
        raise ScanError("That doesn't look like a valid link.")
    try:
        port = parsed.port
    except ValueError:
        raise ScanError("That link has an invalid port.")
    if port not in (None, 80, 443):
        raise ScanError("Only standard web ports (80 and 443) can be scanned.")

    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise ScanError("Couldn't find that domain. Check the spelling.")

    addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    for addr in addresses:
        if not addr.is_global:
            raise ScanError(
                "That link points to a private or internal address, "
                "so SafeClick won't scan it.")

    ipv4 = sorted(str(a) for a in addresses if a.version == 4)
    if not ipv4:
        raise ScanError("That site has no IPv4 address SafeClick can reach.")
    return host.lower(), ipv4[0]


# ---------------------------------------------------------------- checks

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection to a fixed IP that still sends the real hostname (SNI)."""

    def __init__(self, host, ip, context):
        super().__init__(host, 443, timeout=TIMEOUT, context=context)
        self._pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class PinnedHTTPConnection(http.client.HTTPConnection):
    """Plain HTTP connection to a fixed IP with the real Host header."""

    def __init__(self, host, ip):
        super().__init__(host, 80, timeout=TIMEOUT)
        self._pinned_ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


def check_certificate(host, ip):
    context = ssl.create_default_context()
    try:
        with socket.create_connection((ip, 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                tls_version = tls.version()
    except ssl.SSLCertVerificationError as err:
        reason = getattr(err, "verify_message", "") or str(err)
        return {
            "status": "fail",
            "title": "Certificate is not trusted",
            "detail": "The site's security certificate failed verification (" + reason + "). "
                      "Your browser would show a warning. Don't enter passwords or payment details.",
        }
    except (socket.timeout, TimeoutError):
        return {
            "status": "warn",
            "title": "HTTPS timed out",
            "detail": "The site didn't answer on its secure port in time, so the certificate couldn't be checked.",
        }
    except OSError:
        return {
            "status": "fail",
            "title": "No HTTPS",
            "detail": "The site doesn't offer a secure (HTTPS) connection. Anything you type could be read in transit.",
        }

    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), timezone.utc)
    days_left = (expires - datetime.now(timezone.utc)).days
    issuer = dict(item[0] for item in cert.get("issuer", ()))
    issuer_name = issuer.get("organizationName") or issuer.get("commonName") or "Unknown"

    status = "pass"
    notes = []
    if days_left < 14:
        status = "warn"
        notes.append("It expires very soon.")
    if tls_version in ("TLSv1", "TLSv1.1"):
        status = "warn"
        notes.append(tls_version + " is outdated.")

    return {
        "status": status,
        "title": "Valid certificate" if status == "pass" else "Certificate needs attention",
        "detail": ("Issued by " + issuer_name + ", expires " + expires.strftime("%b %d, %Y")
                   + " (" + str(days_left) + " days). Connection uses " + str(tls_version) + ". "
                   + " ".join(notes)).strip(),
    }


def fetch_headers(host, ip):
    """Request the home page and return (scheme, status, headers). Redirects are not followed."""
    insecure = ssl.create_default_context()
    insecure.check_hostname = False
    insecure.verify_mode = ssl.CERT_NONE  # trust is judged by check_certificate()
    request_headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}

    for scheme, conn in (("https", PinnedHTTPSConnection(host, ip, insecure)),
                         ("http", PinnedHTTPConnection(host, ip))):
        try:
            conn.request("GET", "/", headers=request_headers)
            resp = conn.getresponse()
            headers = {k.lower(): v for k, v in resp.getheaders()}
            return scheme, resp.status, headers
        except (OSError, http.client.HTTPException):
            continue
        finally:
            conn.close()
    raise ScanError("Couldn't connect to that site.")


def check_headers(headers):
    results = []
    for key, label, important, why in SECURITY_HEADERS:
        present = key in headers
        if key == "x-frame-options" and not present:
            present = "frame-ancestors" in headers.get("content-security-policy", "")
        results.append({
            "header": label,
            "present": present,
            "important": important,
            "why": why,
        })
    return results


def scan(raw_url):
    host, ip = resolve_target(raw_url)
    certificate = check_certificate(host, ip)
    scheme, status_code, headers = fetch_headers(host, ip)
    header_results = check_headers(headers)

    present = sum(1 for h in header_results if h["present"])
    missing_important = [h["header"] for h in header_results if h["important"] and not h["present"]]

    if certificate["status"] == "fail":
        verdict, summary = "red", "Risky. Avoid entering any personal information on this site."
    elif certificate["status"] == "warn" or present < 3 or missing_important:
        verdict, summary = "yellow", "Use caution. The connection is secure, but some protections are missing."
    else:
        verdict, summary = "green", "Looks well configured. The connection is secure and key protections are in place."

    location = headers.get("location")
    return {
        "host": host,
        "ip": ip,
        "verdict": verdict,
        "summary": summary,
        "certificate": certificate,
        "headers": header_results,
        "headers_present": present,
        "headers_total": len(header_results),
        "http_status": status_code,
        "served_over": scheme,
        "redirects_to": location if 300 <= status_code < 400 else None,
        "scanned_by": INSTANCE_ID,
        "disclaimer": "SafeClick checks how a site is configured. A well-configured site can still be a scam, so trust your instincts too.",
    }


# ---------------------------------------------------------------- web server

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SafeClick</title>
<style>
  :root { --ink:#14213d; --muted:#5c677d; --bg:#f4f6fb; --card:#fff; --line:#dde2ec;
          --green:#1b8a5a; --yellow:#b7791f; --red:#c53030; --accent:#2f5bea; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }
  main { max-width:760px; margin:0 auto; padding:48px 16px; }
  h1 { margin:0; font-size:2rem; letter-spacing:-0.02em; }
  h1 span { color:var(--accent); }
  .tag { color:var(--muted); margin:6px 0 28px; }
  form { display:flex; gap:8px; }
  input { flex:1; min-width:0; padding:14px 16px; font-size:1rem; border:1px solid var(--line); border-radius:10px; }
  button { padding:14px 22px; font-size:1rem; border:0; border-radius:10px; background:var(--accent); color:#fff; cursor:pointer; }
  button:disabled { opacity:.6; cursor:wait; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:22px; margin-top:24px; }
  .verdict { border-left:6px solid var(--muted); }
  .verdict.green { border-color:var(--green); } .verdict.yellow { border-color:var(--yellow); } .verdict.red { border-color:var(--red); }
  .verdict h2 { margin:0 0 6px; font-size:1.25rem; }
  .pill { display:inline-block; font-size:.75rem; font-weight:600; padding:2px 10px; border-radius:99px; color:#fff; margin-right:6px; }
  .pass,.green .pill { background:var(--green); } .warn { background:var(--yellow); } .fail { background:var(--red); }
  ul { list-style:none; padding:0; margin:12px 0 0; }
  li { padding:10px 0; border-top:1px solid var(--line); }
  li small { display:block; color:var(--muted); margin-top:2px; }
  .muted { color:var(--muted); font-size:.9rem; }
  .error { color:var(--red); }
  footer { margin-top:40px; font-size:.85rem; color:var(--muted); border-top:1px solid var(--line); padding-top:14px; }
  footer code { color:var(--ink); }
</style>
</head>
<body>
<main>
  <h1>Safe<span>Click</span></h1>
  <p class="tag">Check a link before you trust it.</p>
  <form id="scan-form">
    <input id="url" name="url" placeholder="example.com" autocomplete="off" required>
    <button id="go" type="submit">Scan</button>
  </form>
  <div id="result"></div>
  <footer>
    <div>Instance ID: <code>__INSTANCE_ID__</code></div>
    <div>Availability Zone: <code>__AZ__</code></div>
  </footer>
</main>
<script>
const form = document.getElementById("scan-form");
const out = document.getElementById("result");
const btn = document.getElementById("go");
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const label = { green:"Looks safe", yellow:"Use caution", red:"Risky" };

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  btn.disabled = true; btn.textContent = "Scanning...";
  out.innerHTML = "";
  try {
    const res = await fetch("/api/scan?url=" + encodeURIComponent(document.getElementById("url").value));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Scan failed.");
    const c = data.certificate;
    const headers = data.headers.map(h => `<li><span class="pill ${h.present ? "pass" : (h.important ? "fail" : "warn")}">${h.present ? "Present" : "Missing"}</span>${esc(h.header)}<small>${esc(h.why)}</small></li>`).join("");
    out.innerHTML = `
      <div class="card verdict ${data.verdict}">
        <h2>${label[data.verdict]}: ${esc(data.host)}</h2>
        <div>${esc(data.summary)}</div>
        ${data.redirects_to ? `<p class="muted">This page redirects to ${esc(data.redirects_to)}</p>` : ""}
      </div>
      <div class="card">
        <strong>Certificate</strong>
        <ul><li><span class="pill ${c.status}">${c.status.toUpperCase()}</span>${esc(c.title)}<small>${esc(c.detail)}</small></li></ul>
      </div>
      <div class="card">
        <strong>Security headers (${data.headers_present} of ${data.headers_total})</strong>
        <ul>${headers}</ul>
      </div>
      <p class="muted">${esc(data.disclaimer)} Scanned by ${esc(data.scanned_by)}.</p>`;
  } catch (err) {
    out.innerHTML = `<div class="card"><p class="error">${esc(err.message)}</p></div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Scan";
  }
});
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "SafeClick/0.1"

    def _send(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        # SafeClick follows its own advice.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, "ok", "text/plain")
        elif parsed.path == "/":
            self._send(200, RENDERED_PAGE, "text/html; charset=utf-8")
        elif parsed.path == "/api/scan":
            url = parse_qs(parsed.query).get("url", [""])[0]
            try:
                self._json(200, scan(url))
            except ScanError as err:
                self._json(400, {"error": str(err)})
            except Exception as err:  # never crash the worker on a bad site
                self.log_message("scan error for %r: %s", url, err)
                self._json(502, {"error": "Something went wrong while scanning that site."})
        else:
            self._json(404, {"error": "Not found"})

    def log_message(self, fmt, *args):
        # Goes to stdout, then journald, so it's visible with journalctl -u safeclick
        sys.stdout.write("[%s] %s %s\n" % (INSTANCE_ID, self.address_string(), fmt % args))
        sys.stdout.flush()


INSTANCE_ID, AVAILABILITY_ZONE = get_instance_info()
RENDERED_PAGE = (PAGE.replace("__INSTANCE_ID__", html.escape(INSTANCE_ID))
                     .replace("__AZ__", html.escape(AVAILABILITY_ZONE)))


def main():
    port = int(os.environ.get("PORT", "80"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("SafeClick listening on port %d (instance %s, %s)" % (port, INSTANCE_ID, AVAILABILITY_ZONE), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
