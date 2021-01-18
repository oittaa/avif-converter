import unittest
import urllib

from google.cloud import exceptions
from main import app, sha256sum
from unittest.mock import patch

TEST_LOCAL_JPG = 'static/flowers.jpg'
TEST_NET_BMP = 'https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.bmp'
TEST_NET_NOT_IMAGE = 'https://www.google.com/'
TEST_NET_TOO_BIG = 'https://effigis.com/wp-content/uploads/2015/02/Airbus_Pleiades_50cm_8bit_RGB_Yogyakarta.jpg'

@patch('main.GCP_BUCKET', '-testing-')
@patch('main.upload_blob', side_effect=exceptions.NotFound('Test'))
@patch('main.download_blob', side_effect=exceptions.NotFound('Test'))
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

    def test_main_page(self, mock_dl, mock_ul):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        response = self.app.get('/favicon.ico')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/vnd.microsoft.icon')

    def test_api_post(self, mock_dl, mock_ul):
        response = self.app.post('/api', data={'file': open(TEST_LOCAL_JPG, 'rb')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        response = self.app.post('/api', data={'xx': open(TEST_LOCAL_JPG, 'rb')})
        self.assertEqual(response.status_code, 400)
        response = self.app.post('/api', data={'file': open(__file__, 'rb')})
        self.assertEqual(response.status_code, 400)

    def test_api_get(self, mock_dl, mock_ul):
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_NOT_IMAGE)))
        self.assertEqual(response.status_code, 400)
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_TOO_BIG)))
        self.assertEqual(response.status_code, 406)
        response = self.app.get('/api?url=invalid')
        self.assertEqual(response.status_code, 400)
        mock_dl.side_effect = self.download_blob
        mock_ul.side_effect = self.upload_blob
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_BMP)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_BMP)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')

    def test_sha256sum(self, mock_dl, mock_ul):
        val1 = sha256sum(TEST_LOCAL_JPG)
        self.assertEqual(len(val1), 64)
        val2 = sha256sum(__file__)
        self.assertNotEqual(val1, val2)

if __name__ == '__main__':
    unittest.main()
