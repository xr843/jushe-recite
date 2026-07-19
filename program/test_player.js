// 离线驱动 index.html 真实播放引擎的状态机测试。
// 无浏览器/jsdom：用 mock 媒体元素 + DOM 桩，跑真引擎代码（从 index.html 抽取，非副本）。
// 验证：单颂播放/停止、单曲循环、连播推进、跨品换文件、列表循环、未对齐颂跳过。
const fs = require("fs");
const path = require("path");
const DIR = path.resolve(__dirname);

// ---------- DOM / 媒体 桩 ----------
let intervalCb = null;
const fakeEl = () => {
  const el = {
    _w: "", style: {}, dataset: {}, textContent: "", innerHTML: "",
    classList: { add(){}, remove(){}, toggle(){}, contains(){return false;} },
    addEventListener(){}, scrollIntoView(){}, scrollTo(){},
    getBoundingClientRect: () => ({ top:0, bottom:0, left:0, right:0, width:0, height:0 }),
    querySelector: () => fakeEl(), querySelectorAll: () => [],
  };
  Object.defineProperty(el.style, "width", { get(){return el._w;}, set(v){el._w=v;}, configurable:true });
  return el;
};
const audio = {
  _src:"", currentTime:0, playbackRate:1, _onmeta:null, paused:true,
  set src(v){ this._src=v; }, get src(){ return this._src; },
  addEventListener(ev, cb){ if(ev==="loadedmetadata") this._onmeta=cb; },
  load(){ if(this._onmeta){ const f=this._onmeta; this._onmeta=null; f(); } },  // 模拟元数据就绪
  play(){ this.paused=false; return { catch(){} }; },
  pause(){ this.paused=true; },
};
const ids = {};
// app.js 版引擎比旧内联版多用了 createElement/body（错误横幅、Opus 探测）与 window/location/navigator
global.document = {
  getElementById(id){ if(id==="audio") return audio; return ids[id] || (ids[id]=fakeEl()); },
  querySelector(){ return fakeEl(); },
  querySelectorAll(){ return []; },
  createElement(){ return fakeEl(); },
  addEventListener(){}, removeEventListener(){},
  body: fakeEl(), documentElement: fakeEl(),
};
const store = {};
global.localStorage = { getItem:k=>k in store?store[k]:null, setItem:(k,v)=>{store[k]=String(v);}, removeItem:k=>{delete store[k];} };
global.window = { addEventListener(){}, removeEventListener(){}, matchMedia:()=>({matches:false,addEventListener(){}}) };
global.location = { href:"https://x/program/", hash:"", reload(){}, replace(){} };
global.navigator = { serviceWorker:{ addEventListener(){}, register(){ return { then(){ return { catch(){} }; } }; } } };
global.setInterval = (fn)=>{ intervalCb = fn; return 1; };
global.clearInterval = ()=>{ intervalCb = null; };
global.encodeURIComponent = encodeURIComponent;
global.Math = Math; global.Set = Set; global.JSON = JSON; global.parseInt = parseInt;
global.parseFloat = parseFloat;
// 同步执行 setTimeout 回调：seekThenPlay() 用 setTimeout 推进"确认落点后再 play()"，
// 测试是同步断言，必须让回调当场跑完，否则永远测不到 play()。
global.setTimeout = (fn)=>{ if (typeof fn === "function") fn(); return 0; };
global.clearTimeout = ()=>{};

// ---------- 载入数据 + 引擎 ----------
let code = fs.readFileSync(path.join(DIR,"verses.js"),"utf8") + "\n";
code += fs.readFileSync(path.join(DIR,"timings.js"),"utf8") + "\n";
// 引擎自 3e734ce 起从 index.html 内联 <script> 抽到了 app.js（严格 CSP）。
// app.js = 主引擎 IIFE + 末尾的 SW 注册；这里只取到引擎 IIFE 结尾那行 "})();"。
const appLines = fs.readFileSync(path.join(DIR,"app.js"),"utf8").split("\n");
const engineEnd = appLines.findIndex(function (l) { return /^\}\)\(\);\s*$/.test(l); });
if (engineEnd < 0) throw new Error("app.js 中找不到引擎 IIFE 结尾 })();");
let engineSrc = appLines.slice(0, engineEnd + 1).join("\n");
// 暴露内部函数供测试（仅改测试副本，不动 index.html）
engineSrc = engineSrc.replace(/\}\)\(\);\s*$/,
  '; global.__T={get engine(){return engine;}, onSinglePlay, onSingleLoopToggle, onSeqPlay, onSeqLoopToggle, seqStep, stopEngine, playCurrent, selected, byId}; })();');
code += engineSrc;
eval(code);

const T = global.__T, E = ()=>T.engine;
const tickTo = (sec)=>{ audio.currentTime=sec; if(intervalCb) intervalCb(); };
let pass=0, fail=0;
const ok=(c,m)=>{ if(c){pass++;} else {fail++; console.log("  ✗ "+m);} };

// === 1. 单颂播放：载入界品音频，seek 到该颂起点 ===
T.onSinglePlay("界-3");  // start 35.92 end 41.74, file 1.界品.mp3
ok(E().mode==="single", "单颂模式");
ok(audio.src.includes("1.%E7%95%8C%E5%93%81.mp3"), "界品 mp3 URL 已编码: "+audio.src);
ok(Math.abs(audio.currentTime-35.92)<0.01, "seek 到 35.92, got "+audio.currentTime);
ok(!audio.paused, "已播放");

// === 2. 到达本颂 end → 非循环则停止 ===
tickTo(41.74);
ok(E().mode===null, "到 end 后停止");
ok(audio.paused, "音频已暂停");

// === 3. 单曲循环：到 end 回到起点继续 ===
T.onSingleLoopToggle("界-5"); // 47.54-53.32
ok(E().looping===true, "循环开启");
tickTo(53.32);
ok(E().mode==="single", "循环态仍在播");
ok(Math.abs(audio.currentTime-47.54)<0.01, "回到起点 47.54, got "+audio.currentTime);

// === 4. 连播：勾选跨序分→界品，验证推进 + 同文件不重载 ===
T.stopEngine();
["序-1","界-1","界-2"].forEach(id=>T.selected.add(id));
audio._src=""; T.engine.curFile=null;
T.onSeqPlay();
ok(E().mode==="sequence" && E().queue[0]==="序-1", "连播从序-1 开始");
ok(Math.abs(audio.currentTime-0.5)<0.01, "序-1 起点 0.5, got "+audio.currentTime);
const fileAfterFirst = audio.src;
tickTo(8.46); // 序-1 end → 应推进到 界... 不，queue 是 selectedOrdered 按 globalNo: 序-1,界-1,界-2
ok(E().queue[E().index]==="界-1", "推进到 界-1, got "+E().queue[E().index]);
ok(audio.src===fileAfterFirst, "同属界品音频，未换文件");
ok(Math.abs(audio.currentTime-24.28)<0.01, "界-1 起点 24.28, got "+audio.currentTime);

// === 5. 列表末尾非循环 → 停止 ===
tickTo(30.14); // 界-1 end → 界-2
ok(E().queue[E().index]==="界-2", "推进到 界-2");
tickTo(35.92); // 界-2 end → 末尾，非循环
ok(E().mode===null, "列表末尾停止");

// === 6. 列表循环：末尾回到首颂 ===
T.onSeqLoopToggle(); // savedSeqLoop=true
T.onSeqPlay();
ok(E().looping===true, "连播循环开启");
E().index = E().queue.length-1; // 跳到末尾
tickTo(window.TIMINGS[E().queue[E().index]].end);
ok(E().index===0, "循环回到首颂, got index "+E().index);

// === 7. 未对齐颂跳过：连播队列中间夹一个无时间戳 id，playCurrent 应自动跳过 ===
T.stopEngine();
T.engine.mode="sequence"; T.engine.queue=["界-1","__未对齐__","界-2"]; T.engine.index=1; T.engine.looping=false;
T.engine.curFile=null;
T.playCurrent(); // index 1 无时间戳 → 内部 advanceSeq 跳到 界-2 并播放
ok(E().mode==="sequence" && E().queue[E().index]==="界-2", "跳过未对齐颂到界-2, got "+(E().mode?E().queue[E().index]:"已停止"));
ok(Math.abs(audio.currentTime-window.TIMINGS["界-2"].start)<0.01, "界-2 起点已 seek, got "+audio.currentTime);

console.log(`\n  通过 ${pass} / ${pass+fail}`);
process.exit(fail?1:0);
