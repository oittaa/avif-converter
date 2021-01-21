# avif-converter docker image

To build and use avif-converter locally in a Debian Docker container with all dependencies,
change into `app` directory and run:

    docker-compose up --build avif-converter

This should install all necessary dependencies, including manually building and installing all
supported codecs as shared libraries. It will then start a web server attached to port 8080.

*Note: This build process will take a while.*
