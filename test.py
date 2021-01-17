import unittest
import urllib

from main import app, sha256sum

TEST_LOCAL_JPG = 'static/flowers.jpg'
TEST_NET_BMP = 'https://www.w3.org/People/mimasa/test/imgformat/img/w3c_home.bmp'

class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.assertEqual(app.debug, False)

    def test_main_page(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)

    def test_api_post(self):
        response = self.app.post('/api', data={'file': open(TEST_LOCAL_JPG, 'rb')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        response = self.app.post('/api', data={'file': open(__file__, 'rb')})
        self.assertEqual(response.status_code, 400)

    def test_api_get(self):
        response = self.app.get('/api?url={}'.format(urllib.parse.quote(TEST_NET_BMP)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'image/avif')
        response = self.app.get('/api?url=invalid')
        self.assertEqual(response.status_code, 400)

    def test_sha256sum(self):
        val1 = sha256sum(TEST_LOCAL_JPG)
        self.assertEqual(len(val1), 64)
        val2 = sha256sum(__file__)
        self.assertNotEqual(val1, val2)

if __name__ == '__main__':
    unittest.main()
