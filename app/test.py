import os
import subprocess
import unittest
import urllib

from hashlib import sha256
from tempfile import NamedTemporaryFile
from time import sleep
from unittest.mock import patch

from main import app, calculate_sri_on_file, hash_sum
from gcp_storage_emulator.server import create_server
from flask_caching.contrib.googlecloudstoragecache import (
    GoogleCloudStorageCache as Cache,
)

TEST_BUCKET = "test"
TEST_LOCAL_PNG = "static/tux.png"
# sha256sum static/tux.png | head -c 64
TEST_LOCAL_PNG_HASH = "4358b1e6137fd60a49ad90d108b73c0116738552d78cf4fceb56a89f044c342f"
TEST_NET_URL = (
    "https://raw.githubusercontent.com/oittaa/avif-converter/master/test_images/"
)
TEST_NET_GIF = TEST_NET_URL + "test.gif"
TEST_NET_JPG = TEST_NET_URL + "test.jpg"
# sha256sum test_images/test.jpg | head -c 64
TEST_NET_JPG_HASH = "e7273a6e8842280c3e291297f3c6e3f7d94bb4c0993d771341ec5e22532e6411"
TEST_NET_PNG = TEST_NET_URL + "test.png"
TEST_NET_BMP = TEST_NET_URL + "test.bmp"
TEST_NET_PNG_NOEXT = TEST_NET_URL + "test_png"
TEST_NET_HEIC = TEST_NET_URL + "test.heic"
TEST_NET_AVIF = TEST_NET_URL + "test.avif"
TEST_NET_PDF = TEST_NET_URL + "test.pdf"
TEST_NET_TIF = TEST_NET_URL + "test.tif"
TEST_NET_NOT_IMAGE = "https://www.google.com/"
TEST_NET_TOO_BIG = TEST_NET_URL + "test_50mb.jpg"
# echo -n "" | openssl dgst -sha384 -binary | openssl base64 -A
EMPTY_FILE_SRI = (
    "sha384-OLBgp1GsljhM2TJ+sbHjaiH9txEUvgdDTAzHv2P24donTt6/529l+9Ua0vFImLlb"
)
TEST_STRING = "alert('Hello, world.');"
# echo -n "alert('Hello, world.');" | openssl dgst -sha384 -binary | openssl base64 -A
TEST_STRING_SRI = (
    "sha384-H8BRh8j48O9oYatfu5AZzq6A9RINhZO5H16dQZngK7T62em8MUt1FLm52t+eX6xO"
)
TEST_BASE_URL = "https://www.example.com/"

os.environ["STORAGE_EMULATOR_HOST"] = "http://localhost:9023"


def get_mime(data):
    """Get MIME from image."""
    with NamedTemporaryFile(suffix=".avif") as tempf:
        tempf.write(data)
        result = subprocess.run(
            ["magick", "identify", "-format", "%[magick]", tempf.name],
            capture_output=True,
            text=True,
        )
        return result.stdout


# https://docs.python.org/3/library/unittest.mock.html#quick-guide
# Note: When you nest patch decorators the mocks are passed in to
# the decorated function in the same order they applied (the normal
# Python order that decorators are applied). This means from the
# bottom up.


@patch("main.URL", TEST_BASE_URL)
class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._server = create_server(
            "localhost", 9023, in_memory=True, default_bucket=TEST_BUCKET
        )
        cls._server.start()

    @classmethod
    def tearDownClass(cls):
        cls._server.stop()

    def setUp(self):
        self.app = app.test_client()
        self.assertEqual(app.debug, False)

    def test_main_page(self):
        response = self.app.get("/")
        self.assertEqual(response.status_code, 200)
        response = self.app.get("/favicon.ico")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Content-Type"), "image/vnd.microsoft.icon"
        )
        response = self.app.get("/peafowl.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "image/jpeg")
        response = self.app.get("/peafowl.avif")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "image/avif")
        response = self.app.get("/?test")
        self.assertEqual(response.status_code, 404)
        response = self.app.get("/favicon.ico?test")
        self.assertEqual(response.status_code, 404)
        response = self.app.get("/peafowl.jpg?test")
        self.assertEqual(response.status_code, 404)
        response = self.app.get("/peafowl.avif?test")
        self.assertEqual(response.status_code, 404)

    def test_api_post(self):
        data = {"file": open(TEST_LOCAL_PNG, "rb")}
        response = self.app.post("/api", data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "image/avif")
        self.assertEqual(get_mime(response.data), "AVIF")
        temp_data = response.data
        # ImageMagick's default quality is 50. 0 is also "default".
        quality_list = ["0", "50"]
        for q in quality_list:
            data = {"file": open(TEST_LOCAL_PNG, "rb")}
            response = self.app.post("/api?quality=" + q, data=data)
            self.assertEqual(temp_data, response.data)
        prev_len = 0
        quality_list = ["40", "85", "100"]
        for q in quality_list:
            data = {"file": open(TEST_LOCAL_PNG, "rb"), "quality": q}
            response = self.app.post("/api", data=data)
            current_len = len(response.data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            self.assertLess(prev_len, current_len)
            self.assertNotEqual(temp_data, response.data)
            prev_len = current_len

    def test_api_get(self):
        response = self.app.get(
            "/api?url={}".format(urllib.parse.quote(TEST_NET_PNG)),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "image/avif")
        self.assertEqual(get_mime(response.data), "AVIF")

    def test_api_get_with_cache(self):
        with patch("main.cache", Cache(bucket=TEST_BUCKET, anonymous=True)):
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_PNG)),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_GIF)),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_PNG_NOEXT, "rb")),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_PDF, "rb")),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_TIF, "rb")),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_HEIC, "rb")),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_AVIF, "rb")),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(get_mime(response.data), "AVIF")
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_BMP)),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            temp_data = response.data
            response = self.app.get(
                "/api?url={}".format(urllib.parse.quote(TEST_NET_BMP)),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "image/avif")
            self.assertEqual(response.data, temp_data)
            response = self.app.get(
                "/api?quality=80&url={}".format(urllib.parse.quote(TEST_NET_PNG)),
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)

    def test_api_invalid_requests(self):
        response = self.app.get(
            "/api?url={}".format(urllib.parse.quote(TEST_NET_NOT_IMAGE))
        )
        self.assertEqual(response.status_code, 400)
        response = self.app.get(
            "/api?url={}".format(urllib.parse.quote(TEST_NET_TOO_BIG))
        )
        self.assertEqual(response.status_code, 406)
        response = self.app.get("/api?url=invalid")
        self.assertEqual(response.status_code, 400)
        response = self.app.get("/api?url=https%3A//this-address-does-not-exist")
        self.assertEqual(response.status_code, 400)
        response = self.app.post("/api", data={"xx": open(TEST_LOCAL_PNG, "rb")})
        self.assertEqual(response.status_code, 400)
        response = self.app.post("/api", data={"file": open(__file__, "rb")})
        self.assertEqual(response.status_code, 400)
        response = self.app.get(
            "/api?invalid=1&url={}".format(urllib.parse.quote(TEST_NET_PNG))
        )
        self.assertEqual(response.status_code, 400)
        quoted_url = urllib.parse.quote(TEST_NET_PNG)
        response = self.app.get(
            "/api?url={}".format(
                urllib.parse.quote(TEST_BASE_URL + "api?url=" + quoted_url)
            )
        )
        self.assertEqual(response.status_code, 400)
        response = self.app.get(
            "/api?url={}".format(urllib.parse.quote("https://" + "a" * 2000 + ".com"))
        )
        self.assertEqual(response.status_code, 414)
        response = self.app.get("/{}.avif".format(TEST_NET_JPG_HASH))
        self.assertEqual(response.status_code, 404)
        response = self.app.get("/{}.avif?invalid".format(TEST_NET_JPG_HASH))
        self.assertEqual(response.status_code, 404)
        response = self.app.get("/invalid.avif")
        self.assertEqual(response.status_code, 404)
        response = self.app.get(
            "/api?quality=-1&url={}".format(urllib.parse.quote(TEST_NET_PNG)),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 400)
        response = self.app.get(
            "/api?quality=101&url={}".format(urllib.parse.quote(TEST_NET_PNG)),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 400)
        response = self.app.get(
            "/api?quality=test&url={}".format(urllib.parse.quote(TEST_NET_PNG)),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 400)
        response = self.app.get(
            "/api?quality=80&invalid=true&url={}".format(
                urllib.parse.quote(TEST_NET_PNG)
            ),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_sha256sum(self):
        val1 = hash_sum(TEST_LOCAL_PNG, sha256()).hexdigest()
        self.assertEqual(len(val1), 64)
        self.assertEqual(val1, TEST_LOCAL_PNG_HASH)
        val2 = hash_sum(__file__, sha256()).hexdigest()
        self.assertNotEqual(val1, val2)

    def test_sri(self):
        with NamedTemporaryFile() as tempf:
            val1 = calculate_sri_on_file(tempf.name)
            tempf.write(TEST_STRING.encode("utf-8"))
            tempf.flush()
            val2 = calculate_sri_on_file(tempf.name)
        self.assertEqual(val1, EMPTY_FILE_SRI)
        self.assertEqual(val2, TEST_STRING_SRI)

    def test_cache(self):
        cache = Cache(bucket=TEST_BUCKET, anonymous=True)
        for i in range(10):
            cache.set(str(i), i)
        for i in range(10):
            self.assertEqual(cache.get(str(i)), i)
        cache.set("key", "message", 3)
        self.assertEqual(cache.get("key"), "message")
        sleep(5)
        self.assertEqual(cache.get("key"), None)


if __name__ == "__main__":
    unittest.main()
