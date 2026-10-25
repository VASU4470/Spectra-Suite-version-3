const ribbonMap={
home:[["File",["Open","Save","Undo","Redo"]],["Common",["Import","New Plot","Properties"]]],
data:[["Import",["Open Data","Add Dataset","Paste"]],["Table",["Add Column","Delete","Set X/Y ▼","Formula"]]],
plot:[["Graph",["Axes ▼","Legend ▼","Series ▼","Layout ▼"]],["View",["Fit View","Zoom","Pan","Cursor"]]],
process:[["Processing",["Baseline ▼","Smooth ▼","Normalize ▼","Derivative ▼","Subtract"]]],
analyze:[["FT-IR Analysis",["Find Peaks ▼","Area","Deconvolution ▼","Functional Groups"]],["General",["Fit ▼","Statistics ▼"]]],
annotate:[["Insert",["Text","Arrow","Peak Label","Shape ▼"]]],
view:[["Workspace",["Project Explorer","Tile","Maximize Active","Status Bar"]]],
export:[["Export",["Figure ▼","Data ▼","Results ▼","Report"]]]
};

const ribbon=document.getElementById("ribbon");
const tabs=[...document.querySelectorAll(".ribbon-tabs .tab")];
const status=document.getElementById("statusText");
const context=document.getElementById("contextLabel");
let activeTab="home";
let maximized=null;

function drawRibbon(tab){
  ribbon.innerHTML="";
  (ribbonMap[tab]||[]).forEach(([title,items])=>{
    const g=document.createElement("div"); g.className="ribbon-group";
    items.forEach(label=>{
      const b=document.createElement("button"); b.className="ribbon-btn";
      b.innerHTML='<span class="ico">'+iconFor(label)+'</span><span>'+label+'</span>';
      b.onclick=()=>handleCommand(label);
      g.appendChild(b);
    });
    const t=document.createElement("div"); t.className="group-title"; t.textContent=title; g.appendChild(t);
    ribbon.appendChild(g);
  });
}
function iconFor(label){
  if(/Open|Import/.test(label)) return "⇧";
  if(/Save|Export/.test(label)) return "⇩";
  if(/Baseline/.test(label)) return "⌁";
  if(/Smooth/.test(label)) return "≈";
  if(/Peak/.test(label)) return "⌃";
  if(/Axis|Axes/.test(label)) return "↔";
  if(/Legend/.test(label)) return "▤";
  if(/Plot|Graph/.test(label)) return "⌁";
  if(/Data|Table|Column/.test(label)) return "▦";
  if(/Properties/.test(label)) return "⚙";
  return "◇";
}
tabs.forEach(t=>t.onclick=()=>{
  tabs.forEach(x=>x.classList.remove("active"));
  t.classList.add("active"); activeTab=t.dataset.tab; drawRibbon(activeTab);
});
function handleCommand(label){
  status.textContent=label;
  if(/Axes|Properties/.test(label)) document.getElementById("axisDialog").showModal();
  if(label==="Tile") tileDocs();
  if(label==="Project Explorer") document.getElementById("projectPanel").classList.toggle("collapsed");
}

function setActive(doc){
  document.querySelectorAll(".tree-item").forEach(x=>x.classList.remove("active"));
  const item=document.querySelector('.tree-item[data-doc="'+doc+'"]'); if(item)item.classList.add("active");
  context.textContent="Active: "+({table:"Raw Data",plot:"FT-IR Plot",peaks:"Peak Results",overlay:"Overlay Plot"}[doc]||doc);
  if(doc==="plot"){tabs.find(x=>x.dataset.tab==="plot").click();}
  if(doc==="table"){tabs.find(x=>x.dataset.tab==="data").click();}
}
document.querySelectorAll(".tree-item").forEach(b=>b.onclick=()=>setActive(b.dataset.doc));
document.getElementById("tableDoc").onclick=()=>setActive("table");
document.getElementById("plotDoc").onclick=()=>setActive("plot");

function maximize(id){
  const canvas=document.getElementById("docCanvas");
  const docs=[...document.querySelectorAll(".doc-window")];
  if(maximized===id){tileDocs();return;}
  maximized=id; canvas.className="doc-canvas maximized";
  docs.forEach(d=>d.classList.toggle("hidden",d.id!==id));
  status.textContent="Maximized "+id.replace("Doc","");
}
function tileDocs(){
  maximized=null;
  const canvas=document.getElementById("docCanvas"); canvas.className="doc-canvas tiled";
  document.querySelectorAll(".doc-window").forEach(d=>d.classList.remove("hidden"));
  status.textContent="Tiled documents";
}
document.querySelectorAll(".doc-max").forEach(b=>b.onclick=e=>{e.stopPropagation();maximize(b.dataset.target)});
document.querySelectorAll(".doc-close").forEach(b=>b.onclick=e=>{e.stopPropagation();document.getElementById(b.dataset.target).classList.add("hidden");});
document.getElementById("tileDocs").onclick=tileDocs;
document.getElementById("showTable").onclick=()=>{document.getElementById("tableDoc").classList.remove("hidden");setActive("table")};
document.getElementById("showPlot").onclick=()=>{document.getElementById("plotDoc").classList.remove("hidden");setActive("plot")};
document.getElementById("collapseProject").onclick=()=>document.getElementById("projectPanel").classList.toggle("collapsed");
document.getElementById("axisProps").onclick=e=>{e.stopPropagation();document.getElementById("axisDialog").showModal()};
document.getElementById("applyAxis").onclick=()=>status.textContent="Axis settings applied in prototype";
document.querySelectorAll(".axis-pill").forEach(b=>b.onclick=()=>{document.querySelectorAll(".axis-pill").forEach(x=>x.classList.remove("active"));b.classList.add("active")});
document.querySelectorAll(".dialog-tab").forEach(b=>b.onclick=()=>{document.querySelectorAll(".dialog-tab").forEach(x=>x.classList.remove("active"));b.classList.add("active")});
document.getElementById("commandSearch").addEventListener("keydown",e=>{if(e.key==="Enter"){status.textContent="Command search: "+e.target.value}});
drawRibbon("home");
