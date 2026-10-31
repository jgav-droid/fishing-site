// Pure URL-state rules for the trip finder:  node --test mvp/tests/url_state.test.js
const test = require("node:test");
const assert = require("node:assert");
const S = require("../site/static/finder.js");
const D = { from: "", date: "2026-10-31", max: "25", shore: "1", dock: "any", hide: "0" };

test("default state serialises to nothing (clean URL)", () => {
  assert.strictEqual(S.serialize({ ...D }, D), "");
});
test("only changed criteria are serialised; defaults omitted", () => {
  assert.strictEqual(S.serialize({ ...D, from: "Tacoma" }, D), "from=Tacoma");
  assert.strictEqual(S.serialize({ ...D, from: "Tacoma", max: "40" }, D), "from=Tacoma&max=40");
  assert.strictEqual(S.serialize({ ...D, dock: "require", hide: "1" }, D), "dock=require&hide=1");
  assert.strictEqual(S.serialize({ ...D, from: "Bonney Lake" }, D), "from=Bonney%20Lake");
});
test("returning to defaults clears the state", () => {
  const changed = { ...D, from: "Tacoma", max: "40" };
  assert.notStrictEqual(S.serialize(changed, D), "");
  assert.strictEqual(S.serialize({ ...changed, from: "", max: "25" }, D), "");
});
test("shared fragments parse back, including legacy full-state fragments", () => {
  assert.deepStrictEqual(S.parse("#from=Tacoma&max=40"), { from: "Tacoma", max: "40" });
  assert.deepStrictEqual(S.parse("#from=&date=2026-10-31&max=25&shore=1&dock=any&hide=0"),
                         { date: "2026-10-31", max: "25", shore: "1", dock: "any", hide: "0" });
  const st = { ...D, from: "Bonney Lake", date: "2026-11-02", dock: "prefer" };
  assert.deepStrictEqual({ ...D, ...S.parse("#" + S.serialize(st, D)) }, st);
});
test("invalid values are ignored", () => {
  assert.deepStrictEqual(S.parse("#date=tomorrow&max=far&dock=yes&shore=2&hide=x&evil=<script>"), {});
  assert.deepStrictEqual(S.parse("#from=%E0%A4%A"), {});
});
