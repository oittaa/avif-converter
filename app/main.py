"""This app converts images to AV1 Image File Format (AVIF)."""

import datetime
import logging
import os
import pathlib
import re
import subprocess
import time

from base64 import b64encode
from hashlib import sha256, sha384
from mimetypes import guess_extension
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin, urlparse

import requests

from flask import Flask, abort, redirect, render_template, request, send_file, \
    send_from_directory, url_for
from flask_talisman import Talisman
from google.cloud import storage, exceptions
from werkzeug.middleware.proxy_fix import ProxyFix

CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 43200))
FORCE_HTTPS = bool(os.environ.get('FORCE_HTTPS', ''))
GCP_BUCKET = os.environ.get('GCP_BUCKET')
GET_MAX_SIZE = int(os.environ.get('GET_MAX_SIZE', 20*1024*1024))
REMOTE_REQUEST_TIMEOUT = float(os.environ.get('REMOTE_REQUEST_TIMEOUT', 10.0))
TITLE = os.environ.get('TITLE', 'AVIF Converter')
URL = os.environ.get('URL')
X_FOR = int(os.environ.get('X_FOR', 0))
X_PROTO = int(os.environ.get('X_PROTO', 0))

# "image/*" are always supported.
SUPPORTED_MIMES = ['application/octet-stream', 'application/pdf']

# Change the format of messages logged to Stackdriver
logging.basicConfig(format='%(message)s', level=logging.INFO)

csp = {
 'default-src': [
        '\'self\'',
        'cdnjs.cloudflare.com'
    ]
}
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = CACHE_TIMEOUT
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=X_FOR, x_proto=X_PROTO)
talisman = Talisman(
    app,
    content_security_policy=csp,
    force_https=FORCE_HTTPS
)

if GCP_BUCKET:  # pragma: no cover
    storage_client = storage.Client()

@app.route('/favicon.ico')
def favicon():
    """Sends legacy favicon."""
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/', methods=['GET'])
def index():
    """Shows the main page."""
    if len(request.args) > 0:
        abort(404)
    css_sri = calculate_sri_on_file(os.path.join(app.root_path, 'static', 'style.css'))
    js_sri = calculate_sri_on_file(os.path.join(app.root_path, 'static', 'javascript.js'))
    return render_template('index.html', title=TITLE, css_sri=css_sri, js_sri=js_sri)

@app.route('/api', methods=['GET'])
def api_get():
    """An API endpoint for GET requests."""
    url_hash = None

    url = request.args.get('url')
    if not isinstance(url, str) or len(request.args) != 1:
        abort(400)
    if not url.startswith('https://') \
        and not url.startswith('http://'):
        abort(400)

    # Recursive query
    if url.startswith(url_for('api_get', _external=True)) \
        or URL and url.startswith(urljoin(URL, url_for('api_get'))):
        abort(400)

    if GCP_BUCKET:
        url_hash = sha256(url.encode('utf-8')).hexdigest()
        with NamedTemporaryFile() as tempf:
            try:
                download_blob(GCP_BUCKET, url_hash, tempf.name)
                logging.info('Cache hit URL: %s/%s', GCP_BUCKET, url_hash)
                data_hash = tempf.read()
                data_hash = data_hash.decode('utf-8')
                if blob_exists(GCP_BUCKET, data_hash):
                    return redirect(url_for('avif_get', image=data_hash))
            except exceptions.NotFound:
                logging.info('Cache miss URL: %s/%s', GCP_BUCKET, url_hash)

    try:
        response = requests.head(url, timeout=REMOTE_REQUEST_TIMEOUT)
        content_type = response.headers.get('Content-Type')
        if not isinstance(content_type, str) or (not content_type.startswith('image/') \
            and not content_type in SUPPORTED_MIMES):
            abort(400)
        content_length = response.headers.get('Content-Length')
        if isinstance(content_length, str) and int(content_length) > GET_MAX_SIZE:
            abort(406)
        logging.info('Fetching URL: %s', url)
        response = requests.get(url, timeout=REMOTE_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException:
        abort(400)
    if response.status_code != requests.codes.ok: #pylint: disable=no-member
        abort(400)
    ext = guess_extension(content_type)
    if not ext or ext == '.a':
        path = urlparse(url).path
        ext = get_extension(path)
    with NamedTemporaryFile(suffix=ext) as tempf:
        tempf.write(response.content)
        return avif_convert(tempf.name, url_hash)

@app.route('/api', methods=['POST'])
def api_post():
    """An API endpoint for POST requests."""
    # check if the post request has the file part
    if 'file' not in request.files:
        abort(400)
    file = request.files['file']
    ext = get_extension(file.filename)
    with NamedTemporaryFile(suffix=ext) as tempf:
        file.save(tempf.name)
        return avif_convert(tempf.name)

@app.route('/<image>', methods=['GET'])
def avif_get(image):
    """Fetches an image from a cache."""
    if len(request.args) > 0 or not GCP_BUCKET:
        abort(404)
    image_pattern = re.compile(r'^[0-9a-f]{64}.avif$')
    match = re.search(image_pattern, image)
    if not match:
        abort(404)
    data_hash = match.group(0)
    with NamedTemporaryFile() as tempf:
        try:
            download_blob(GCP_BUCKET, data_hash, tempf.name)
            return send_avif(tempf.name)
        except exceptions.NotFound:
            abort(404)

def avif_convert(tempf_in, url_hash=None):
    """Convert an image to AVIF. If a cache is available, forwards to 'avif_get' function."""
    logging.info('Input file size: %d', os.path.getsize(tempf_in))
    if GCP_BUCKET:
        data_hash = sha256sum(tempf_in) + '.avif'
        if blob_exists(GCP_BUCKET, data_hash):
            logging.info('Cache hit data: %s/%s', GCP_BUCKET, data_hash)
            if url_hash:
                with NamedTemporaryFile() as tempf:
                    tempf.write(data_hash.encode('utf-8'))
                    tempf.flush()
                    try:
                        upload_blob(GCP_BUCKET, tempf.name, url_hash)
                    except exceptions.NotFound:
                        logging.error('Could not update cache: %s/%s', GCP_BUCKET, url_hash)
            return redirect(url_for('avif_get', image=data_hash))
        logging.info('Cache miss data: %s/%s', GCP_BUCKET, data_hash)
    with NamedTemporaryFile(suffix='.avif') as tempf:
        tempf_out = tempf.name
        try:
            result = subprocess.run(['identify', '-format', '%[magick]', tempf_in], \
                capture_output=True, check=True, text=True)
            mime = result.stdout
        except subprocess.CalledProcessError:
            mime = ''
        if mime == 'AVIF':
            logging.info('Using original AVIF')
            tempf_out = tempf_in
        else:
            logging.info('Converting %s to AVIF', mime)
            start = time.perf_counter()
            try:
                result = subprocess.run(['convert', tempf_in+'[0]', 'avif:'+tempf_out], check=True)
            except subprocess.CalledProcessError:
                logging.error('Could not convert %s to AVIF', mime)
                abort(400)
            logging.info('Encoding time: %.4f', time.perf_counter() - start)
            logging.info('Output file size: %d', os.path.getsize(tempf_out))
        if GCP_BUCKET:
            try:
                upload_blob(GCP_BUCKET, tempf_out, data_hash)
                if url_hash:
                    with NamedTemporaryFile() as tempf_url:
                        tempf_url.write(data_hash.encode('utf-8'))
                        tempf_url.flush()
                        upload_blob(GCP_BUCKET, tempf_url.name, url_hash)
                return redirect(url_for('avif_get', image=data_hash))
            except exceptions.NotFound:
                logging.error('Could not update cache: %s/%s', GCP_BUCKET, data_hash)
        return send_avif(tempf_out)

def send_avif(file):
    """Sends the file with an AVIF MIME type and sets an ETag."""
    response = send_file(file, mimetype='image/avif', cache_timeout=CACHE_TIMEOUT)
    response.set_etag(sha256sum(file))
    return response

def calculate_sri_on_file(filename):
    """Calculate SRI string."""
    hash_digest = hash_sum(filename, sha384()).digest()
    hash_base64 = b64encode(hash_digest).decode()
    return 'sha384-{}'.format(hash_base64)

def sha256sum(filename):
    """Compute SHA256 message digest from a file and return it in hex format."""
    return hash_sum(filename, sha256()).hexdigest()

def hash_sum(filename, hash_func):
    """Compute message digest from a file."""
    byte_array  = bytearray(128*1024)
    memory_view = memoryview(byte_array)
    with open(filename, 'rb', buffering=0) as file:
        for block in iter(lambda : file.readinto(memory_view), 0):
            hash_func.update(memory_view[:block])
    return hash_func

def get_extension(path, max_length=16):
    """Extract an extension from a path without possibly dangerous characters."""
    pattern = re.compile(r'[\W]+')
    ext =  pathlib.Path(path).suffix
    ext = pattern.sub('', ext)
    if ext:
        ext = '.' + ext[0:max_length]
    return ext

def download_blob(bucket_name, source_blob_name, destination_file_name):  # pragma: no cover
    """Downloads a blob from the bucket."""
    # bucket_name = "your-bucket-name"
    # source_blob_name = "storage-object-name"
    # destination_file_name = "local/path/to/file"

    bucket = storage_client.bucket(bucket_name)

    # Construct a client side representation of a blob.
    # Note `Bucket.blob` differs from `Bucket.get_blob` as it doesn't retrieve
    # any content from Google Cloud Storage. As we don't need additional data,
    # using `Bucket.blob` is preferred here.
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)
    update_blob_custom_time(bucket_name, source_blob_name)
    logging.debug("Blob %s downloaded to %s.", source_blob_name, destination_file_name)

def upload_blob(bucket_name, source_file_name, destination_blob_name):  # pragma: no cover
    """Uploads a file to the bucket."""
    # bucket_name = "your-bucket-name"
    # source_file_name = "local/path/to/file"
    # destination_blob_name = "storage-object-name"

    now = datetime.datetime.utcnow()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.custom_time = now

    blob.upload_from_filename(source_file_name)
    logging.debug(
        "File %s uploaded to %s.", source_file_name, destination_blob_name)

def update_blob_custom_time(bucket_name, blob_name):  # pragma: no cover
    """Update a blob's Custom-Time metadata."""
    # bucket_name = "your-bucket-name"
    # blob_name = "storage-object-name"

    now = datetime.datetime.utcnow()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.get_blob(blob_name)
    blob.custom_time = now
    try:
        blob.patch()
        logging.debug("The Custom-Time for the blob %s is %s", blob.name, blob.custom_time)
    except (exceptions.BadRequest, exceptions.Conflict) as error:
        logging.error("Could not edit the blob %s - Custom-Time %s - %s", \
            blob.name, blob.custom_time, error)

def blob_exists(bucket_name, blob_name):  # pragma: no cover
    """Check if a blob exists in a bucket."""
    # bucket_name = "your-bucket-name"
    # blob_name = "storage-object-name"

    bucket = storage_client.bucket(bucket_name)
    return storage.Blob(bucket=bucket, name=blob_name).exists(storage_client)

if __name__ == '__main__':  # pragma: no cover
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
