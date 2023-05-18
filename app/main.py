"""This app converts images to AV1 Image File Format (AVIF)."""

import logging
import os
import re

from base64 import b64encode
from hashlib import sha256, sha384
from io import BytesIO
from subprocess import CalledProcessError, run
from tempfile import NamedTemporaryFile
from time import perf_counter
from urllib.parse import urljoin

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
from flask_caching.backends.nullcache import NullCache
from flask_caching.contrib.googlecloudstoragecache import GoogleCloudStorageCache
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix

CACHE_TIMEOUT = int(os.environ.get("CACHE_TIMEOUT", 43200))
DEFAULT_QUALITY = os.environ.get("DEFAULT_QUALITY", "50")
FORCE_HTTPS = bool(os.environ.get("FORCE_HTTPS", ""))
GCP_BUCKET = os.environ.get("GCP_BUCKET")
GET_MAX_SIZE = int(os.environ.get("GET_MAX_SIZE", 20 * 1024 * 1024))
MAX_AGE = int(os.environ.get("MAX_AGE", CACHE_TIMEOUT))
REMOTE_REQUEST_TIMEOUT = float(os.environ.get("REMOTE_REQUEST_TIMEOUT", 10.0))
TITLE = os.environ.get("TITLE", "AVIF Converter")
URL = os.environ.get("URL")
X_FOR = int(os.environ.get("X_FOR", 0))
X_PROTO = int(os.environ.get("X_PROTO", 0))

# "image/*" are always supported.
SUPPORTED_MIMES = ["application/octet-stream", "application/pdf"]


# Change the format of messages logged to Stackdriver
logging.basicConfig(format="%(message)s", level=logging.INFO)

csp = {"default-src": ["'self'", "cdnjs.cloudflare.com"]}
app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = MAX_AGE
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=X_FOR, x_proto=X_PROTO)
talisman = Talisman(app, content_security_policy=csp, force_https=FORCE_HTTPS)
cache = (
    GoogleCloudStorageCache(bucket=GCP_BUCKET, default_timeout=MAX_AGE)
    if GCP_BUCKET
    else NullCache()
)


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
    quality = request.args.get("quality")
    if (
        not isinstance(url, str)
        or len(request.args) != 1
        and quality is None
        or len(request.args) != 2
        and quality is not None
    ):
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
    # Request-URI Too Long
    if len(url) > 2000:
        abort(414)
    quality = validate_quality(quality)
    url_hash = sha256(url.encode("utf-8"))
    if quality is not None:
        logging.info("URL with encoding quality: %s", quality)
        url_hash.update(quality.encode())
    url_hash = url_hash.hexdigest()
    value = cache.get(url_hash)
    if value is not None:
        data_hash = value.decode("utf-8")
        if cache.has(data_hash):
            return redirect(url_for("avif_get", image=data_hash))
    content = get_content_from_url(url)
    with NamedTemporaryFile() as tempf:
        tempf.write(content)
        return avif_convert(tempf.name, url_hash, quality)


@app.route("/api", methods=["POST"])
def api_post():
    """An API endpoint for POST requests."""
    # check if the post request has the file part
    if "file" not in request.files:
        abort(400)
    quality = validate_quality(request.values.get("quality"))
    file = request.files["file"]
    with NamedTemporaryFile() as tempf:
        file.save(tempf.name)
        return avif_convert(tempf.name, quality=quality)


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


def avif_convert(tempf_in, url_hash=None, quality=None):
    """Convert an image to AVIF. If a cache is available, forwards to 'avif_get' function."""
    logging.info("Input file size: %d", os.path.getsize(tempf_in))
    data_hash = hash_sum(tempf_in, sha256())
    if quality is not None:
        logging.info("Encoding quality: %s", quality)
        data_hash.update(quality.encode())
    data_hash = data_hash.hexdigest() + ".avif"
    if cache.has(data_hash):
        if url_hash is not None:
            cache.set(url_hash, data_hash.encode("utf-8"))
        return redirect(url_for("avif_get", image=data_hash))
    mime, _error = _run(["magick", "identify", "-format", "%[magick]", tempf_in])
    logging.info("Converting %s to AVIF", mime)
    with NamedTemporaryFile(suffix=".avif") as tempf:
        tempf_out = tempf.name
        start = perf_counter()
        args = ["magick", tempf_in + "[0]"]
        if quality is not None:
            args += ["-quality", quality]
        _result, error = _run(args + ["avif:" + tempf_out])
        if error:
            logging.error("Could not convert %s to AVIF", mime)
            abort(400)
        logging.info("Encoding time: %.4f", perf_counter() - start)
        logging.info("Output file size: %d", os.path.getsize(tempf_out))
        image_bytes = tempf.read()
    if cache.set(data_hash, image_bytes) and cache.has(data_hash):
        if url_hash is not None:
            cache.set(url_hash, data_hash.encode("utf-8"))
        return redirect(url_for("avif_get", image=data_hash))
    return send_avif(image_bytes)


def send_avif(image_bytes):
    """Sends the file with an AVIF MIME type and sets an ETag."""
    response = send_file(BytesIO(image_bytes), mimetype="image/avif", max_age=MAX_AGE)
    response.set_etag(sha256(image_bytes).hexdigest())
    return response


def calculate_sri_on_file(filename):
    """Calculate SRI string."""
    hash_digest = hash_sum(filename, sha384()).digest()
    hash_base64 = b64encode(hash_digest).decode()
    return "sha384-{}".format(hash_base64)


def hash_sum(filename, hash_func):
    """Compute message digest from a file."""
    byte_array = bytearray(128 * 1024)
    memory_view = memoryview(byte_array)
    with open(filename, "rb", buffering=0) as file:
        for block in iter(lambda: file.readinto(memory_view), 0):
            hash_func.update(memory_view[:block])
    return hash_func


def get_content_from_url(url):
    """Download content from URL."""
    try:
        logging.info("Checking URL: %s", url)
        response = requests.head(url, timeout=REMOTE_REQUEST_TIMEOUT)
        content_type = response.headers.get("Content-Type")
        if not isinstance(content_type, str) or (
            not content_type.startswith("image/")
            and content_type not in SUPPORTED_MIMES
        ):
            abort(400)
        content_length = response.headers.get("Content-Length")
        if isinstance(content_length, str) and int(content_length) > GET_MAX_SIZE:
            abort(406)
        logging.info("Fetching URL: %s", url)
        response = requests.get(url, timeout=REMOTE_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException:
        abort(400)
    if response.status_code != requests.codes.ok:  # pragma: no cover
        abort(400)
    return response.content


def validate_quality(quality):
    quality = quality or DEFAULT_QUALITY
    if quality is not None:
        try:
            quality = int(quality)
            if quality < 0:
                abort(400)
            elif quality > 100:
                abort(400)
            else:
                quality = str(quality)
        except ValueError:
            abort(400)
    return quality


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
