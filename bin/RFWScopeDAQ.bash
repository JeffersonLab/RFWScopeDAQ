#!/usr/bin/env bash

# Figure out script dir and cd there
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -n "$DIR" ] ; then
  cd "$DIR" || (echo "Error cd'ing to $DIR" && exit 1)
  export APP_ROOT="$DIR"
else
  echo "Error determining script dir"
  exit 1
fi

if [ -f ../venv/bin/activate ]; then
  source ../venv/bin/activate
else
  source ../venv/Scripts/activate
fi

RFWScopeDAQ "$@"
