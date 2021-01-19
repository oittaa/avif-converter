import logging
import magic
import multiprocessing
import os
import requests
import subprocess
import time

from flask import Flask, abort, redirect, render_template, request, send_file, send_from_directory
from google.cloud import storage, exceptions
from hashlib import sha256
from tempfile import NamedTemporaryFile

SUPPORTED_MIMES = ['image/jpeg', 'image/png']
TITLE = os.environ.get('TITLE', 'AVIF Converter')
URL = os.environ.get('URL', 'https://example.com/')
CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 43200))
GET_MAX_SIZE = int(os.environ.get('GET_MAX_SIZE', 20*1024*1024))
GCP_BUCKET = os.environ.get('GCP_BUCKET')

# Change the format of messages logged to Stackdriver
logging.basicConfig(format='%(message)s', level=logging.INFO)

app = Flask(__name__)


if GCP_BUCKET:  # pragma: no cover
    storage_client = storage.Client()

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', title=TITLE, url=URL)

@app.route('/api', methods=['GET'])
def api_get():
    url_hash = None

    url = request.args.get('url')
    if not isinstance(url, str) or (not url.startswith('https://') and not url.startswith('http://')):
        abort(400)

    if GCP_BUCKET:
        url_hash = sha256(url.encode('utf-8')).hexdigest()
        with NamedTemporaryFile() as tempf:
            try:
                download_blob(GCP_BUCKET, url_hash, tempf.name)
                logging.info('Cache hit URL: {}/{}'.format(GCP_BUCKET, url_hash))
                return send_avif(tempf.name)
            except exceptions.NotFound:
                logging.info('Cache miss URL: {}/{}'.format(GCP_BUCKET, url_hash))

    try:
        r = requests.head(url)
        content_type = r.headers.get('Content-Type')
        if not isinstance(content_type, str) or (not content_type.startswith('image/') and not content_type == 'application/octet-stream'):
            abort(400)
        content_length = r.headers.get('Content-Length')
        if isinstance(content_length, str) and int(content_length) > GET_MAX_SIZE:
            abort(406)
        logging.info('Fetching URL: %s', url)
        r = requests.get(url)
    except requests.exceptions.RequestException as e:
        abort(400)
    if r.status_code != requests.codes.ok:
        abort(400)
    with NamedTemporaryFile() as tempf:
        tempf.write(r.content)
        return avif_convert(tempf.name, url_hash)

@app.route('/api', methods=['POST'])
def api_post():
    # check if the post request has the file part
    if 'file' not in request.files:
        abort(400)
    f = request.files['file']
    with NamedTemporaryFile() as tempf:
        f.save(tempf.name)
        return avif_convert(tempf.name)

def avif_convert(tempf_in, url_hash=None):
    logging.info('Input file size: %d', os.path.getsize(tempf_in))
    if GCP_BUCKET:
        data_hash = sha256sum(tempf_in)
        with NamedTemporaryFile() as tempf:
            try:
                download_blob(GCP_BUCKET, data_hash, tempf.name)
                logging.info('Cache hit data: {}/{}'.format(GCP_BUCKET, data_hash))
                if url_hash:
                    upload_blob(GCP_BUCKET, tempf.name, url_hash)
                return send_avif(tempf.name)
            except exceptions.NotFound:
                logging.info('Cache miss data: {}/{}'.format(GCP_BUCKET, data_hash))
    with NamedTemporaryFile() as tempf:
        tempf_out = tempf.name
        mime = magic.from_file(tempf_in, mime=True)
        if mime not in SUPPORTED_MIMES:
            result = subprocess.run(['convert', tempf_in+'[0]', 'png:'+tempf_out])
            if result.returncode == 0:
                tempf_in, tempf_out = tempf_out, tempf_in
            else:
                logging.error('Could not convert {} to PNG'.format(mime))
        start = time.perf_counter()
        result = subprocess.run(['avifenc', '-j', str(multiprocessing.cpu_count()), tempf_in, tempf_out])
        logging.info('Encoding time: {:.4f}'.format(time.perf_counter() - start))
        if result.returncode != 0:
            logging.error('avifenc error')
            abort(400)
        logging.info('Output file size: %d', os.path.getsize(tempf_out))
        if GCP_BUCKET:
            try:
                upload_blob(GCP_BUCKET, tempf_out, data_hash)
                if url_hash:
                    upload_blob(GCP_BUCKET, tempf_out, url_hash)
            except exceptions.NotFound:
                logging.error('Could not update cache: {}/{}'.format(GCP_BUCKET, data_hash))
        return send_avif(tempf_out)

def send_avif(f):
    response = send_file(f, mimetype='image/avif', cache_timeout=CACHE_TIMEOUT)
    response.set_etag(sha256sum(f))
    return response

def sha256sum(filename):
    h  = sha256()
    b  = bytearray(128*1024)
    mv = memoryview(b)
    with open(filename, 'rb', buffering=0) as f:
        for n in iter(lambda : f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()

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

    print(
        "Blob {} downloaded to {}.".format(
            source_blob_name, destination_file_name
        )
    )

def upload_blob(bucket_name, source_file_name, destination_blob_name):  # pragma: no cover
    """Uploads a file to the bucket."""
    # bucket_name = "your-bucket-name"
    # source_file_name = "local/path/to/file"
    # destination_blob_name = "storage-object-name"

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)

    print(
        "File {} uploaded to {}.".format(
            source_file_name, destination_blob_name
        )
    )

if __name__ == '__main__':  # pragma: no cover
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
