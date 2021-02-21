"""This app converts images to AV1 Image File Format (AVIF)."""

import logging
import os
import re

from base64 import b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256, sha384
from io import BytesIO
from mimetypes import guess_extension
from pathlib import Path
from subprocess import CalledProcessError, run
from tempfile import NamedTemporaryFile
from time import perf_counter
from urllib.parse import urljoin, urlparse

import requests

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_talisman import Talisman
from google.cloud import storage, exceptions
from werkzeug.middleware.proxy_fix import ProxyFix

CACHE_TIMEOUT = int(os.environ.get("CACHE_TIMEOUT", 43200))
FORCE_HTTPS = bool(os.environ.get("FORCE_HTTPS", ""))
GCP_BUCKET = os.environ.get("GCP_BUCKET")
GET_MAX_SIZE = int(os.environ.get("GET_MAX_SIZE", 20 * 1024 * 1024))
REMOTE_REQUEST_TIMEOUT = float(os.environ.get("REMOTE_REQUEST_TIMEOUT", 10.0))
TITLE = os.environ.get("TITLE", "AVIF Converter")
URL = os.environ.get("URL")
X_FOR = int(os.environ.get("X_FOR", 0))
X_PROTO = int(os.environ.get("X_PROTO", 0))

# "image/*" are always supported.
SUPPORTED_MIMES = ["application/octet-stream", "application/pdf"]


class Cache(object):  # pragma: no cover
    """Cache with Google Cloud Storage"""

    def __init__(self, bucket_name, default_timeout=43200):
        self.bucket = None
        self.cache = {}
        self.default_timeout = default_timeout
        if bucket_name is not None:
            self.client = storage.Client()
            self.bucket = self.client.bucket(bucket_name)

    def get(self, key):
        if self.bucket is None:
            return None

        if key in self.cache:
            return self.cache[key]
        blob = self.bucket.blob(key)
        try:
            value = blob.download_as_bytes()
            if len(self.cache) > 300:
                del self.cache[next(iter(self.cache))]
            self.cache[key] = value
            return value
        except exceptions.NotFound:
            return None

    def set(self, key, value, timeout=None):
        if self.bucket is None:
            return False

        blob = self.bucket.blob(key)
        if timeout is None:
            timeout = self.default_timeout
        if timeout != 0:
            blob.custom_time = datetime.now(timezone.utc) + timedelta(seconds=timeout)
        blob.upload_from_string(value)
        if key not in self.cache and len(self.cache) > 300:
            del self.cache[next(iter(self.cache))]
        self.cache[key] = value
        return True

    def has(self, key):
        if self.bucket is None:
            return False

        if key in self.cache:
            return True
        return storage.Blob(bucket=self.bucket, name=key).exists(self.client)


# Change the format of messages logged to Stackdriver
logging.basicConfig(format="%(message)s", level=logging.INFO)

csp = {"default-src": ["'self'", "cdnjs.cloudflare.com"]}
app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = CACHE_TIMEOUT
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=X_FOR, x_proto=X_PROTO)
talisman = Talisman(app, content_security_policy=csp, force_https=FORCE_HTTPS)
cache = Cache(GCP_BUCKET, CACHE_TIMEOUT)


@app.route("/favicon.ico")
def favicon():
    """Sends legacy favicon."""
    if len(request.args) > 0:
        abort(404)
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/peafowl.jpg")
def peafowl_jpg():
    """Example JPG."""
    if len(request.args) > 0:
        abort(404)
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "peafowl.jpg",
        mimetype="image/jpeg",
    )


@app.route("/peafowl.avif")
def peafowl_avif():
    """Example AVIF."""
    if len(request.args) > 0:
        abort(404)
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "peafowl.avif",
        mimetype="image/avif",
    )


@app.route("/", methods=["GET"])
def index():
    """Shows the main page."""
    if len(request.args) > 0:
        abort(404)
    css_sri = calculate_sri_on_file(os.path.join(app.root_path, "static", "style.css"))
    js_sri = calculate_sri_on_file(
        os.path.join(app.root_path, "static", "javascript.js")
    )
    return render_template("index.html", title=TITLE, css_sri=css_sri, js_sri=js_sri)


@app.route("/api", methods=["GET"])
def api_get():
    """An API endpoint for GET requests."""
    url_hash = None

    url = request.args.get("url")
    if not isinstance(url, str) or len(request.args) != 1:
        abort(400)
    if not url.startswith("https://") and not url.startswith("http://"):
        abort(400)

    # Recursive query
    if (
        url.startswith(url_for("api_get", _external=True))
        or URL
        and url.startswith(urljoin(URL, url_for("api_get")))
    ):
        abort(400)

    url_hash = sha256(url.encode("utf-8")).hexdigest()
    value = cache.get(url_hash)
    if value is not None:
        logging.info("Cache hit URL: %s/%s", GCP_BUCKET, url_hash)
        data_hash = value.decode("utf-8")
        if cache.has(data_hash):
            logging.info("Cache hit data: %s/%s", GCP_BUCKET, data_hash)
            return redirect(url_for("avif_get", image=data_hash))
        else:  # pragma: no cover
            logging.info("Cache miss data: %s/%s", GCP_BUCKET, data_hash)
    else:
        logging.info("Cache miss URL: %s/%s", GCP_BUCKET, url_hash)

    try:
        logging.info("Checking URL: %s", url)
        response = requests.head(url, timeout=REMOTE_REQUEST_TIMEOUT)
        validate_url_headers(response.headers)
        logging.info("Fetching URL: %s", url)
        response = requests.get(url, timeout=REMOTE_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException:
        abort(400)
    if response.status_code != requests.codes.ok:  # pragma: no cover
        abort(400)
    ext = guess_extension(response.headers.get("Content-Type"))
    if not ext or ext == ".a":
        path = urlparse(url).path
        ext = get_extension(path)
    with NamedTemporaryFile(suffix=ext) as tempf:
        tempf.write(response.content)
        return avif_convert(tempf.name, url_hash)


@app.route("/api", methods=["POST"])
def api_post():
    """An API endpoint for POST requests."""
    # check if the post request has the file part
    if "file" not in request.files:
        abort(400)
    file = request.files["file"]
    ext = get_extension(file.filename)
    with NamedTemporaryFile(suffix=ext) as tempf:
        file.save(tempf.name)
        return avif_convert(tempf.name)


@app.route("/<image>", methods=["GET"])
def avif_get(image):
    """Fetches an image from a cache."""
    if len(request.args) > 0:
        abort(404)
    image_pattern = re.compile(r"^[0-9a-f]{64}.avif$")
    match = re.search(image_pattern, image)
    if not match:
        abort(404)
    data_hash = match.group(0)
    image_bytes = cache.get(data_hash)
    if image_bytes is None:
        abort(404)
    return send_avif(image_bytes)


def avif_convert(tempf_in, url_hash=None):
    """Convert an image to AVIF. If a cache is available, forwards to 'avif_get' function."""
    logging.info("Input file size: %d", os.path.getsize(tempf_in))
    data_hash = sha256sum(tempf_in) + ".avif"
    if cache.has(data_hash):
        logging.info("Cache hit data: %s/%s", GCP_BUCKET, data_hash)
        if url_hash is not None:
            logging.info(
                "Setting cache URL hash: %s/%s -> %s", GCP_BUCKET, url_hash, data_hash
            )
            cache.set(url_hash, data_hash.encode("utf-8"))
        return redirect(url_for("avif_get", image=data_hash))
    else:
        logging.info("Cache miss data: %s/%s", GCP_BUCKET, data_hash)

    mime, _error = _run(["magick", "identify", "-format", "%[magick]", tempf_in])
    if mime == "AVIF":
        logging.info("Using original AVIF")
        with open(tempf_in, "rb") as image:
            image_bytes = image.read()
    else:
        logging.info("Converting %s to AVIF", mime)
        with NamedTemporaryFile(suffix=".avif") as tempf:
            tempf_out = tempf.name
            start = perf_counter()
            _result, error = _run(["magick", tempf_in + "[0]", "avif:" + tempf_out])
            if error:
                logging.error("Could not convert %s to AVIF", mime)
                abort(400)
            logging.info("Encoding time: %.4f", perf_counter() - start)
            logging.info("Output file size: %d", os.path.getsize(tempf_out))
            image_bytes = tempf.read()

    if cache.set(data_hash, image_bytes):
        if url_hash is not None:
            logging.info(
                "Setting cache URL hash: %s/%s -> %s",
                GCP_BUCKET,
                url_hash,
                data_hash,
            )
            cache.set(url_hash, data_hash.encode("utf-8"))
        return redirect(url_for("avif_get", image=data_hash))
    return send_avif(image_bytes)


def send_avif(image_bytes):
    """Sends the file with an AVIF MIME type and sets an ETag."""
    response = send_file(
        BytesIO(image_bytes), mimetype="image/avif", cache_timeout=CACHE_TIMEOUT
    )
    response.set_etag(sha256(image_bytes).hexdigest())
    return response


def calculate_sri_on_file(filename):
    """Calculate SRI string."""
    hash_digest = hash_sum(filename, sha384()).digest()
    hash_base64 = b64encode(hash_digest).decode()
    return "sha384-{}".format(hash_base64)


def sha256sum(filename):
    """Compute SHA256 message digest from a file and return it in hex format."""
    return hash_sum(filename, sha256()).hexdigest()


def hash_sum(filename, hash_func):
    """Compute message digest from a file."""
    byte_array = bytearray(128 * 1024)
    memory_view = memoryview(byte_array)
    with open(filename, "rb", buffering=0) as file:
        for block in iter(lambda: file.readinto(memory_view), 0):
            hash_func.update(memory_view[:block])
    return hash_func


def get_extension(path, max_length=16):
    """Extract an extension from a path without possibly dangerous characters."""
    pattern = re.compile(r"[\W]+")
    ext = Path(path).suffix
    ext = pattern.sub("", ext)
    if ext:
        ext = "." + ext[0:max_length]
    return ext


def validate_url_headers(headers, max_size=GET_MAX_SIZE):
    """Check URL's Content-Type and Content-Length."""
    content_type = headers.get("Content-Type")
    if not isinstance(content_type, str) or (
        not content_type.startswith("image/") and content_type not in SUPPORTED_MIMES
    ):
        abort(400)
    content_length = headers.get("Content-Length")
    if isinstance(content_length, str) and int(content_length) > max_size:
        abort(406)
    return content_type


def _run(args):
    output = ""
    error = False
    try:
        result = run(args, capture_output=True, check=True, text=True)
        output = result.stdout
    except CalledProcessError:
        error = True
    return output, error


if __name__ == "__main__":  # pragma: no cover
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
