const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const html = fs.readFileSync("index.html", "utf8");
const data = JSON.parse(fs.readFileSync("data.json", "utf8"));
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new Function(script);

const prefix = script.split("/* ---------- 本机存储")[0];
const sandbox = { data };
vm.runInNewContext(`let A;\n${prefix}
  A=anchors(data);
  const match=rule=>{const r=ruleDates(rule,A);return periodsForItem({_start:r.start,_end:r.end});};
  globalThis.result={
    ranges:PERIODS.map(p=>{const r=periodRange(p);return{id:p.id,start:r.start?iso(r.start):null,end:r.end?iso(r.end):null};}),
    due:iso(A.due),allPregnancy:match("lmp+0W..due+0W"),duePoint:match("due+0W"),
    post:match("due+100D"),items:data.items.map(it=>({id:it.id,periods:match(it.rule)})),
    knowledgeOk:TOPICS.every(t=>Array.isArray(data.knowledge.w1_3[t.key])&&data.knowledge.w1_3[t.key].length>0)
  };
})();`, sandbox);

const r = JSON.parse(JSON.stringify(sandbox.result));
assert.equal(r.ranges.length, 15);
assert.equal(r.due, "2028-03-22");
assert.deepEqual(r.ranges.find(x => x.id === "w1_3"), { id:"w1_3", start:"2027-06-16", end:"2027-07-06" });
assert.deepEqual(r.ranges.find(x => x.id === "w4_6"), { id:"w4_6", start:"2027-07-07", end:"2027-07-27" });
assert.deepEqual(r.ranges.find(x => x.id === "w40"), { id:"w40", start:"2028-03-15", end:"2028-03-21" });
assert.deepEqual(r.ranges.find(x => x.id === "birth"), { id:"birth", start:"2028-03-22", end:"2028-03-22" });
assert.deepEqual(r.ranges.find(x => x.id === "post100"), { id:"post100", start:"2028-03-23", end:"2028-06-30" });
assert.equal(r.allPregnancy.length, 13);
assert.ok(r.allPregnancy.includes("birth"));
assert.deepEqual(Array.from(r.duePoint), ["birth"]);
assert.deepEqual(Array.from(r.post), ["post100"]);
assert.ok(r.items.every(x => x.periods.length > 0));
assert.ok(r.knowledgeOk);
assert.ok(html.includes("```daopai-sync"));
assert.ok(html.includes('const LS_ITEMS="daopai.phoneItems.v1"'));
console.log(`通过：脚本语法、15 个阶段边界、${data.items.length} 条事项归段、跨周匹配、知识示例与原同步格式。`);
