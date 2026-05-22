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

python3 -c "
c = open('api.py').read()

# --disable-gpu 추가
c = c.replace(
    'browser = await uc.start(user_data_dir=_CHROME_PROFILE)',
    'browser = await uc.start(user_data_dir=_CHROME_PROFILE, browser_args=[\"--disable-gpu\", \"--disable-software-rasterizer\"])'
)

# Strategy 3 스킵 (hang 방지)
c = c.replace(
    'logger.info(\"[3/3] 移除验证码后提交...\")\n        r = await _submit_no_captcha(tab)\n        if r:\n            return r',
    'logger.info(\"[3/3] skip\")'
)

open('api.py', 'w').write(c)
print('패치 완료')
"

python main.py
