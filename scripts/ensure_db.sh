#!/bin/bash
# Postgres doesn't stay running between separate tool invocations in this
# sandbox (no persistent init system), so every script/test run starts it
# first if it's not already up.
if ! pg_isready -q 2>/dev/null; then
  service postgresql start >/dev/null 2>&1
  sleep 2
fi
