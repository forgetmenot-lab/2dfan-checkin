#!/bin/bash
set -e

Xvfb :99 -screen 0 1280x720x24 &
sleep 2
export DISPLAY=:99

python3 -c "
import nodriver.core.browser as b, inspect
f = inspect.getfile(b.Browser)
src = open(f).read()
p = src.replace('range(5)', 'range(20)').replace('range(10)', 'range(30)')
if p != src:
    open(f, 'w').write(p)
"

if [ "$#" -gt 0 ]; then
    exec "$@"
fi
exec python main.py
