import requests
import subprocess
import unittest
import urllib

from google.cloud import exceptions
from main import app, calculate_sri_on_file, get_extension, sha256sum, URL
from tempfile import NamedTemporaryFile
from unittest.mock import patch

TEST_LOCAL_PNG = 'static/tux.png'
TEST_LOCAL_PNG_HASH = '4358b1e6137fd60a49ad90d108b73c0116738552d78cf4fceb56a89f044c342f'  # sha256sum static/tux.png | head -c 64
TEST_NET_URL = 'https://raw.githubusercontent.com/oittaa/avif-converter/master/test_images/'
TEST_NET_GIF = TEST_NET_URL + 'test.gif'
TEST_NET_JPG = TEST_NET_URL + 'test.jpg'
TEST_NET_JPG_HASH = 'e7273a6e8842280c3e291297f3c6e3f7d94bb4c0993d771341ec5e22532e6411'  # sha256sum test_images/test.jpg | head -c 64
TEST_NET_PNG = TEST_NET_URL + 'test.png'
TEST_NET_BMP = TEST_NET_URL + 'test.bmp'
TEST_NET_PNG_NOEXT = TEST_NET_URL + 'test_png'
TEST_NET_HEIC = TEST_NET_URL + 'test.heic'
TEST_NET_AVIF = TEST_NET_URL + 'test.avif'
TEST_NET_PDF = TEST_NET_URL + 'test.pdf'
TEST_NET_NOT_IMAGE = 'https://www.google.com/'
TEST_NET_TOO_BIG = TEST_NET_URL + 'test_50mb.jpg'
EMPTY_FILE_SRI = 'sha384-OLBgp1GsljhM2TJ+sbHjaiH9txEUvgdDTAzHv2P24donTt6/529l+9Ua0vFImLlb'  # echo -n "" | openssl dgst -sha384 -binary | openssl base64 -A
TEST_STRING = 'alert(\'Hello, world.\');'
TEST_STRING_SRI = 'sha384-H8BRh8j48O9oYatfu5AZzq6A9RINhZO5H16dQZngK7T62em8MUt1FLm52t+eX6xO'  # echo -n "alert('Hello, world.');" | openssl dgst -sha384 -binary | openssl base64 -A

def is_avif(data):
    """Checks if data is AVIF."""
    with NamedTemporaryFile(suffix='.avif') as tempf:
        tempf.write(data)
        result = subprocess.run(['identify', '-format', '%[magick]', tempf.name], capture_output=True, text=True)
        mime = result.stdout
        if mime == 'AVIF':
            return True
        else:
            print('Error: got type {}'.format(mime))
            return False

# https://docs.python.org/3/library/unittest.mock.html#quick-guide
# Note: When you nest patch decorators the mocks are passed in to
# the decorated function in the same order they applied (the normal
# Python order that decorators are applied). This means from the
# bottom up.

@patch('main.GCP_BUCKET', '-testing-')
class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.cache = {}
        self.app = app.test_client()
        self.assertEqual(app.debug, False)

    def download_blob(self, bucket_name, source_blob_name, destination_file_name):
        key = bucket_name + source_blob_name
        if not key in self.cache:
            raise exceptions.NotFound(key)
        with open(destination_file_name, 'wb') as f:
            f.write(self.cache[key])

    def upload_blob(self, bucket_name, source_file_name, destination_blob_name):
        key = bucket_name + destination_blob_name
        with open(source_file_name, 'rb') as f:
            self.cache[key] = f.read()

    def test_main_page(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        response = self.app.get('/favicon.ico')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/vnd.microsoft.icon')

    @patch('main.upload_blob', side_effect=exceptions.NotFound('Test'))
    @patch('main.download_blob', side_effect=exceptions.NotFound('Test'))
    def test_api_post(self, mock_dl, mock_ul):
        response = self.app.post('/api', data={'file': open(TEST_LOCAL_PNG, 'rb')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))
        mock_dl.side_effect = self.download_blob
        mock_ul.side_effect = self.upload_blob
        response = self.app.post('/api', data={'file': open(TEST_LOCAL_PNG, 'rb')}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))
        response = self.app.post('/api', data={'file': open(TEST_LOCAL_PNG, 'rb')}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))

    @patch('main.upload_blob', side_effect=exceptions.NotFound('Test'))
    @patch('main.download_blob', side_effect=exceptions.NotFound('Test'))
    def test_api_get(self, mock_dl, mock_ul):
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_PNG)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_GIF)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_PNG_NOEXT, 'rb')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_PDF, 'rb')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_HEIC, 'rb')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertTrue(is_avif(response.data))
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_AVIF, 'rb')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        r = requests.get(TEST_NET_AVIF)
        self.assertEqual(response.data, r.content)
        mock_dl.side_effect = self.download_blob
        mock_ul.side_effect = self.upload_blob
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_BMP)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        temp_data = response.data
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_BMP)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        self.assertEqual(response.data, temp_data)
        self.cache['-testing-'+TEST_NET_JPG_HASH] = 'FAKEDATA'.encode()
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_JPG)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, 'FAKEDATA'.encode())

    @patch('main.upload_blob', side_effect=exceptions.NotFound('Test'))
    @patch('main.download_blob', side_effect=exceptions.NotFound('Test'))
    def test_api_invalid_requests(self, mock_dl, mock_ul):
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_NOT_IMAGE)))
        self.assertEqual(response.status_code, 400)
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_TOO_BIG)))
        self.assertEqual(response.status_code, 406)
        response = self.app.get('/api?url=invalid')
        self.assertEqual(response.status_code, 400)
        response = self.app.get('/api?url=https%3A//this-address-does-not-exist')
        self.assertEqual(response.status_code, 400)
        response = self.app.post('/api', data={'xx': open(TEST_LOCAL_PNG, 'rb')})
        self.assertEqual(response.status_code, 400)
        response = self.app.post('/api', data={'file': open(__file__, 'rb')})
        self.assertEqual(response.status_code, 400)
        response = self.app.get('/api?invalid=1&url={}'.format(urllib.parse.quote(TEST_NET_PNG)))
        self.assertEqual(response.status_code, 400)
        quoted_url = urllib.parse.quote(TEST_NET_PNG)
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(URL+'api?url='+quoted_url)))
        self.assertEqual(response.status_code, 400)
        response = self.app.get('/api?url={}'.format(TEST_NET_JPG_HASH))
        self.assertEqual(response.status_code, 404)

    def test_sha256sum(self):
        val1 = sha256sum(TEST_LOCAL_PNG)
        self.assertEqual(len(val1), 64)
        self.assertEqual(val1, TEST_LOCAL_PNG_HASH)
        val2 = sha256sum(__file__)
        self.assertNotEqual(val1, val2)

    def test_get_extension(self):
        val = get_extension('/path/to/file.jpg')
        self.assertEqual(val, '.jpg')
        val = get_extension('/path/to/.hidden')
        self.assertEqual(val, '')
        val = get_extension('file.€avif@£$‚{[]')
        self.assertEqual(val, '.avif')

    def test_sri(self):
        with NamedTemporaryFile() as tempf:
            val1 = calculate_sri_on_file(tempf.name)
            tempf.write(TEST_STRING.encode())
            tempf.flush()
            val2 = calculate_sri_on_file(tempf.name)
        self.assertEqual(val1, EMPTY_FILE_SRI)
        self.assertEqual(val2, TEST_STRING_SRI)

if __name__ == '__main__':
    unittest.main()
