# avif-converter docker image

![CI](https://github.com/oittaa/avif-converter/workflows/CI/badge.svg)
[![codecov](https://codecov.io/gh/oittaa/avif-converter/branch/master/graph/badge.svg?token=JZ2GFR3RPZ)](https://codecov.io/gh/oittaa/avif-converter)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

To build and use avif-converter locally in a Debian Docker container with all dependencies,
change into `app` directory and run:

    docker-compose up --build avif-converter

This should install all necessary dependencies, including manually building and installing all
supported codecs as shared libraries. It will then start a web server attached to port 8080.

*Note: This build process will take a while.*

## Caching with Google Cloud Platform

If you're using the Docker container with [Cloud Run][cloud-run], you can optionally enable caching. This way you don't have to regenerate the same images every time from scratch. [Cloud Storage][cloud-storage] buckets are used as a cache. Environment variable `CACHE_TIMEOUT` defines the object timeout in seconds. Zero means the object never expires. The default is 43200.

You can use the following shell script as a template to create a bucket with a lifecycle policy that cleans up expired objects every day.

```
#!/bin/sh
set -e

PROJECT_ID="my-project"
STORAGE_CLASS="STANDARD"
BUCKET_LOCATION="US-CENTRAL1"
BUCKET_NAME="my-cache-bucket"

# https://cloud.google.com/storage/docs/creating-buckets

gsutil mb -p ${PROJECT_ID} -c ${STORAGE_CLASS} -l ${BUCKET_LOCATION} -b on gs://${BUCKET_NAME}

LIFECYCLE_CONFIG_FILE=$(mktemp --suffix=.json)
cat > ${LIFECYCLE_CONFIG_FILE} <<EOF
{
   "rule":[
      {
         "action":{
            "type":"Delete"
         },
         "condition":{
            "daysSinceCustomTime":0
         }
      }
   ]
}
EOF
gsutil lifecycle set ${LIFECYCLE_CONFIG_FILE} gs://${BUCKET_NAME}
rm -- ${LIFECYCLE_CONFIG_FILE}
```

Then set `GCP_BUCKET` environment variable to point to the created bucket in your Cloud Run service.
```
gcloud run deploy my-cloud-run-service \
--image=gcr.io/my-project/my-container-image \
--allow-unauthenticated \
--concurrency=8 \
--cpu=4 \
--memory=8192Mi \
--set-env-vars=GCP_BUCKET=my-cache-bucket \
--platform=managed \
--region=us-central1 \
--project=my-project
```

[cloud-run]: https://cloud.google.com/run
[cloud-storage]: https://cloud.google.com/storage
