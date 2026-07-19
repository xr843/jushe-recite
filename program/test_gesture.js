// 回归测试：点 ▶ 时 audio.play() 必须【同步发生在用户手势任务内】。
//
// 背景（这个 bug 真实发生过）：为修「冷缓存 seek 失败会放错颂」，playCurrent 改成
// 等 loadedmetadata + setTimeout 确认落点后才 play()。于是所有 play() 都脱离了手势任务，
// 而 iOS/Safari 只放行手势任务内同步调用的 play()，其余一律 NotAllowedError 拒绝——
// 偏偏这些拒绝被 .catch(function(){}) 吞掉 → 用户「点播放，没有声音」，且没有任何报错。
//
// 与 test_player.js 的关键区别：那边把 setTimeout 打桩成同步执行（为了能同步断言），
// 恰好掩盖了本 bug。这里必须用【真实异步】的 setTimeout，并让 loadedmetadata 异步触发。
const fs = require("fs");
const path = require("path");
const DIR = path.resolve(__dirname);

let inGesture = false;          // 仅在「点击处理函数同步执行期间」为 true
const playCalls = [];

let intervalCb = null;
const fakeEl = () => {
  const el = {
    _w: "", style: {}, dataset: {}, textContent: "", innerHTML: "", checked: false,
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    addEventListener(){}, removeEventListener(){}, scrollIntoView(){}, scrollTo(){},
    appendChild(){}, removeChild(){}, setAttribute(){}, removeAttribute(){},
    getBoundingClientRect: () => ({ top:0, bottom:0, left:0, right:0, width:0, height:0 }),
    querySelector: () => fakeEl(), querySelectorAll: () => [],
    focus(){}, blur(){}, click(){},
  };
  Object.defineProperty(el.style, "width", { get(){ return el._w; }, set(v){ el._w = v; }, configurable:true });
  return el;
};

const audio = {
  _src:"", currentTime:0, playbackRate:1, volume:1, muted:false,
  paused:true, seeking:false, readyState:0, ended:false, error:null,
  _listeners:{},
  set src(v){ this._src = v; this.readyState = 0; }, get src(){ return this._src; },
  addEventListener(ev, cb){ (this._listeners[ev] = this._listeners[ev] || []).push(cb); },
  removeEventListener(){},
  // 真实浏览器里 loadedmetadata 一定是异步的（要等网络返回元数据）
  load(){
    setTimeout(() => {
      this.readyState = 1; this.duration = 600;
      const ls = (this._listeners["loadedmetadata"] || []).slice();
      this._listeners["loadedmetadata"] = [];
      ls.forEach(f => f());
    }, 5);
  },
  play(){ playCalls.push({ inGesture, muted: this.muted }); this.paused = false; return Promise.resolve(); },
  pause(){ this.paused = true; },
};

const ids = {};
global.document = {
  getElementById(id){ if (id === "audio") return audio; return ids[id] || (ids[id] = fakeEl()); },
  querySelector(){ return fakeEl(); }, querySelectorAll(){ return []; },
  createElement(){ return fakeEl(); }, addEventListener(){}, removeEventListener(){},
  body: fakeEl(), documentElement: fakeEl(),
};
const store = {};
global.localStorage = { getItem:k=>k in store?store[k]:null, setItem:(k,v)=>{store[k]=String(v);}, removeItem:k=>{delete store[k];} };
global.window = { addEventListener(){}, removeEventListener(){}, matchMedia:()=>({matches:false,addEventListener(){}}) };
global.location = { href:"https://x/program/", hash:"", reload(){}, replace(){} };
global.navigator = { serviceWorker:{ addEventListener(){}, register(){ return { then(){ return { catch(){} }; } }; } } };
global.setInterval = (fn)=>{ intervalCb = fn; return 1; };
global.clearInterval = ()=>{ intervalCb = null; };
// setTimeout / clearTimeout 刻意保持 Node 原生（真实异步）—— 这正是本测试的意义所在

let code = fs.readFileSync(path.join(DIR, "verses.js"), "utf8") + "\n";
code += fs.readFileSync(path.join(DIR, "timings.js"), "utf8") + "\n";
const appLines = fs.readFileSync(path.join(DIR, "app.js"), "utf8").split("\n");
const engineEnd = appLines.findIndex(l => /^\}\)\(\);\s*$/.test(l));
if (engineEnd < 0) throw new Error("app.js 中找不到引擎 IIFE 结尾 })();");
code += appLines.slice(0, engineEnd + 1).join("\n")
  .replace(/\}\)\(\);\s*$/, '; global.__T={get engine(){return engine;}, onSinglePlay, stopEngine}; })();');
eval(code);

const T = global.__T;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  ✗ " + m); } };

// 模拟一次真实点击：处理函数同步执行期间 inGesture=true，返回后立即置 false。
// 之后任何 setTimeout / 事件回调里的 play() 都算「脱离手势任务」。
async function clickPlay(id) {
  playCalls.length = 0;
  inGesture = true;
  T.onSinglePlay(id);
  inGesture = false;
  await sleep(300);
}

(async () => {
  // 场景 A：首次点播放，需要换 src 并等 loadedmetadata
  await clickPlay("界-3");
  const gA = playCalls.filter(c => c.inGesture);
  ok(gA.length >= 1, "A 首次播放：手势任务内至少有一次 play()（iOS 解锁），实际 " + gA.length);
  ok(gA.every(c => c.muted), "A 手势内那次 play() 必须是静音的（避免放出片头/错颂）");
  ok(audio.muted === false, "A 落点确认后必须解除静音，实际 muted=" + audio.muted);
  ok(!audio.paused, "A 最终处于播放态");

  // 场景 B：同一品内换一颂（src 已载入，不重新 load）
  await clickPlay("界-5");
  const gB = playCalls.filter(c => c.inGesture);
  ok(gB.length >= 1, "B 同文件换颂：手势任务内至少有一次 play()，实际 " + gB.length);
  ok(gB.every(c => c.muted), "B 手势内那次 play() 必须是静音的");
  ok(audio.muted === false, "B 落点确认后必须解除静音，实际 muted=" + audio.muted);
  ok(Math.abs(audio.currentTime - window.TIMINGS["界-5"].start) < 0.4,
     "B 仍落在本颂起点（没有退回「放错颂」），实际 " + audio.currentTime);

  // 场景 C：停止后不能把静音态留给下次播放
  T.stopEngine();
  ok(audio.muted === false, "C stopEngine 后 muted 必须为 false，否则续播永远无声");

  console.log("\n  通过 " + pass + " / " + (pass + fail));
  process.exit(fail ? 1 : 0);
})();
