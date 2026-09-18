"""Run the actual browser JS against a small DOM double, without site requests."""
import json
import os
import shutil
import subprocess
import unittest

import api


NODE = os.environ.get("NODE_BINARY") or shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is optional for selector regression tests")
class SelectorTests(unittest.TestCase):
    def test_vue_action_and_confirmation_scope(self):
        script = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
function button(text, visible=true, disabled=false) {
    return {textContent:text, disabled, className:'n-button', attrs:{},
        getClientRects:()=>visible?[{}]:[],
        getAttribute(k){return this.attrs[k] || null},
        setAttribute(k,v){this.attrs[k]=v}, removeAttribute(k){delete this.attrs[k]}};
}
const sidebar = button('签到');
const action = button(' 签到 ');
const hidden = button('签到',false);
let panel = {querySelectorAll:selector=>[hidden, action]};
let modal = null;
let doc = {
    querySelector:s=>s.includes('NexusCheckin')?panel:s==='.captcha-modal-body'?modal:null,
    getElementById:()=>null,
    querySelectorAll:s=>s==='button'?[sidebar, hidden, action]:[]
};
const run = code => {
    const raw = vm.runInNewContext(code, {document:doc});
    return raw === null ? null : JSON.parse(raw);
};
assert.equal(run(input.action).text,'签到');
assert.equal(sidebar.attrs['data-checkin-automation'],undefined);
assert.equal(hidden.attrs['data-checkin-automation'],undefined);
assert.equal(action.attrs['data-checkin-automation'],'action');
action.disabled=true;
assert.equal(run(input.action).disabled,true);
action.textContent='今日已签到';
assert.equal(run(input.action).text,'今日已签到');
panel=null;
assert.equal(run(input.action),null); // never click sidebar navigation while Vue loads
assert.equal(run(input.confirm),null); // no unrelated global confirmation
const confirm = button('确认',true,true);
modal = {closest:()=>({querySelectorAll:()=>[confirm]})};
assert.equal(run(input.confirm).disabled,true);
confirm.disabled=false;
assert.equal(run(input.confirm).disabled,false);
console.log('selector scenarios passed');
'''
        result = subprocess.run([NODE, "-e", script], input=json.dumps({
            "action": api._BTN_STATE_JS, "confirm": api._CONFIRM_STATE_JS,
        }), text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
