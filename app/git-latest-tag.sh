#!/bin/sh
set -e
LATEST_TAG=$(git ls-remote --tags --exit-code --refs "$1" | grep -oP '^[[:xdigit:]]+[[:space:]]+refs\/tags\/\Kv?[0-9\._-]*$' | sort -V | tail -n1)
if [ "$2" != "${LATEST_TAG}" ]
then
  printf 'Git: %s\nCurrent tag: %s\nThe latest tag: %s\n' "$1" "$2" "${LATEST_TAG}"
  if [ "${CI}" ]
  then
    exit 1
  fi
fi
