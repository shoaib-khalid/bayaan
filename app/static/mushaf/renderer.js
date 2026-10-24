/* Bayaan /mushaf: live saved segments, flowing pages, SVG ink bands. */
'use strict';
const $=id=>document.getElementById(id), L=window.MushafLayout;
const W=697.7008, CONTENT_H=1019.5197, COLORS=['#dceaf6','#f8e9bd'];
const query=new URLSearchParams(location.search);
const int=(value,fallback,min,max)=>Math.max(min,Math.min(max,Number.parseInt(value,10)||fallback));
const state={payloads:[],surahs:[],translations:[],structure:null,border:'',header:'',busy:false,current:0,observer:null,renderId:0,translation:int(query.get('translation_id'),2,1,9999),folio:int(query.get('folio'),1,1,99999)};
const toUr=n=>String(n).replace(/[0-9]/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function request(url,text=false){const r=await fetch(url,{cache:'no-cache'});if(!r.ok)throw Error(`${url}: ${r.status}`);return text?r.text():r.json();}
function status(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
function busy(value){state.busy=value;['read','continue','print','surahSel','endSel','trSel'].forEach(id=>$(id).disabled=value);if(!value)$('continue').disabled=!state.payloads.length||state.payloads.at(-1).surah.id===114;}
function fit(){document.documentElement.style.setProperty('--page-scale',Math.min(1,Math.max(.2,(innerWidth-16)/793.7008)));document.documentElement.style.setProperty('--toolbar-height',document.querySelector('.toolbar').getBoundingClientRect().height+'px');}
function updateURL(){if(!state.payloads.length)return;const q=new URLSearchParams({surah:state.payloads[0].surah.id,through:state.payloads.at(-1).surah.id,translation_id:state.translation,page:state.current+1,ar:$('arSize').value,ur:$('urSize').value});if(state.folio!==1)q.set('folio',state.folio);history.replaceState(null,'',`/mushaf?${q}`);}
function setPage(index,scroll=false){const pages=[...$('pages').children];if(!pages.length)return;state.current=Math.max(0,Math.min(pages.length-1,index));$('pageInfo').textContent=`${state.current+1} / ${pages.length}`;$('prev').disabled=state.current===0;$('next').disabled=state.current===pages.length-1&&state.payloads.at(-1).surah.id===114;if(scroll)pages[state.current].scrollIntoView({block:'start',behavior:'instant'});updateURL();}
function observePages(){state.observer?.disconnect();state.observer=new IntersectionObserver(entries=>{const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio);if(visible.length)setPage(+visible[0].target.dataset.page-1);},{threshold:[.1,.3,.6],rootMargin:'-100px 0px 0px 0px'});[...$('pages').children].forEach(p=>state.observer.observe(p));}
function band(units,height){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('bands');svg.setAttribute('viewBox',`0 0 ${W} ${height}`);svg.setAttribute('preserveAspectRatio','none');for(const u of units){const r=document.createElementNS(svg.namespaceURI,'rect');for(const [k,v] of Object.entries({x:W-u.x-u.w,y:0,width:u.w+.08,height,fill:COLORS[u.color]}))r.setAttribute(k,v);svg.append(r);}return svg;}
function surahHeader(payload){
 const meta=state.structure.bySurah.get(payload.surah.id),compact=[1,9].includes(payload.surah.id);
 const h=el('div','surah-header'+(compact?' compact':''));h.dataset.surah=payload.surah.id;h.innerHTML=state.header;
 if(compact)h.querySelector('svg').setAttribute('viewBox','0 0 1200 400');
 h.append(el('div','surah-title',`${toUr(payload.surah.id)} سُوْرَةُ ${meta.name} ${meta.type==='Medinan'?'مَدَنِيَّةٌ':'مَكِّيَّةٌ'}`));
 h.append(el('div','count left-count',`رکوعات ${toUr(meta.rukus)}`),el('div','count right-count',`آیات ${toUr(payload.ayah_count)}`));
 if(!compact)h.append(el('div','basmala','بِسْمِ اللّٰهِ الرَّحْمٰنِ الرَّحِيْمِ'));
 return h;
}
const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d'),widthCache=new Map();
function width(text,family,size){const key=`${family}|${size}|${text}`;if(!widthCache.has(key)){ctx.font=`${size}px ${family}`;widthCache.set(key,ctx.measureText(text).width);}return widthCache.get(key);}
function makeRow(units,ar,ur){
 const need=units.reduce((n,u)=>n+u.need,0),extra=Math.max(0,W-need),weight=units.reduce((n,u)=>n+Math.max(1,u.ar.length-1),0);let x=0;
 units.forEach(u=>{u.w=u.need+extra*Math.max(1,u.ar.length-1)/weight;u.x=x;x+=u.w;});
 const block=el('div','row'),at=el('div','artrack'),ut=el('div','urtrack'),arH=ar*2.22,line=ur*1.85;
 at.style.height=arH+'px';at.append(band(units,arH));block.append(at,ut);$('measure').style.width=W+'px';$('measure').append(block);let maxH=0;
 for(const u of units){
   const a=el('div','arunit');a.dataset.segment=u.key;a.style.cssText=`right:${u.x}px;width:${u.w}px;font-size:${ar}px`;
   for(const t of u.ar){const w=el('span','aw',t.text);w.dataset.word=t.id;if(t===u.ar.at(-1)&&u.last)w.dataset.ayahEnd=`${u.surah}:${u.ayah}`;a.append(w);if(width(t.text,'Quran',ar)>u.w-8){w.classList.add('long-word');w.style.transform=`scaleX(${(u.w-8)/width(t.text,'Quran',ar)})`;w.style.width=(u.w-8)+'px';}}at.append(a);
   const p=el('div','urunit');p.dataset.segment=u.key;p.style.cssText=`right:${u.x}px;width:${u.w}px;font-size:${ur}px;line-height:${line}px`;
   if(u.missing){p.append(el('span','missing-translation','Translation not available'));}
   else {const text=el('span','translation-text',u.ur);text.dataset.segment=u.key;p.append(text);if(u.last)p.append(el('span','umark',` (${toUr(u.ayah)})`));}
   ut.append(p);maxH=Math.max(maxH,p.getBoundingClientRect().height);
 }
 const urH=maxH+7;ut.style.height=urH+'px';ut.prepend(band(units,urH));
 return {block,height:arH+urH+7.3,first:units[0]};
}
function rukuMarks(){
 for(const anchor of $('pages').querySelectorAll('.aw[data-ayah-end]')){
   const info=state.structure.ends.get(anchor.dataset.ayahEnd);if(!info)continue;
   const sheet=anchor.closest('.sheet'),r=anchor.closest('.artrack').getBoundingClientRect(),p=sheet.getBoundingClientRect();
   const mark=el('div','ruku-mark '+(+sheet.dataset.folio%2?'left':'right'));mark.dataset.ayah=anchor.dataset.ayahEnd;mark.style.top=(r.top-p.top+r.height/2-36)+'px';
   mark.setAttribute('aria-label',`Ruku ${info.surah}, ${info.ayahs} ayahs, para ruku ${info.para}`);
   mark.innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 27 72"><g fill="#111" text-anchor="middle"><text x="13.5" y="14" font-family="Georgia,serif" font-size="16">${toUr(info.surah)}</text><text x="13.5" y="48" font-family="Urdu" font-size="38">ع</text><text x="14" y="41" font-family="Georgia,serif" font-size="12">${toUr(info.ayahs)}</text><text x="13.5" y="68" font-family="Georgia,serif" font-size="16">${toUr(info.para)}</text></g></svg>`;
   sheet.append(mark);
 }
}
async function render(targetPage=state.current){
 const id=++state.renderId;window.mushafReady=false;state.observer?.disconnect();busy(true);status('Laying out pages…');
 document.documentElement.style.setProperty('--page-scale',1);$('pages').replaceChildren();
 const ar=+$('arSize').value,ur=+$('urSize').value;$('arValue').value=ar;$('urValue').value=ur;
 let sheet,content,y=0,pageNo=0,color=0,warnings=0,rowCount=0;
 function newPage(surah,ayah){sheet=el('section','sheet');sheet.dataset.page=++pageNo;sheet.dataset.folio=state.folio+pageNo-1;sheet.dataset.surah=surah;const frame=el('div','frame');frame.innerHTML=state.border;sheet.append(frame);const head=el('div','running');head.append(el('span','surah',`سورۃ ${state.structure.bySurah.get(surah).name}`),el('span','page-number',toUr(sheet.dataset.folio)),el('span','para',`پارہ ${toUr(state.structure.juzAt(surah,ayah))}`));sheet.append(head);content=el('div','content');sheet.append(content);$('pages').append(sheet);y=0;}
 for(const payload of state.payloads){
   if(!sheet)newPage(payload.surah.id,1);
   const built=L.segments(payload,color);color=built.nextColor;warnings+=built.warnings;
   const rows=L.pack(built.segments,W,t=>width(t,'Quran',ar),t=>width(t,'Urdu',ur),ar);
   const header=surahHeader(payload);content.append(header);let headerH=header.getBoundingClientRect().height+10;
   if(y+headerH+125>CONTENT_H){header.remove();newPage(payload.surah.id,1);content.append(header);}const beforeHeader=y;y+=headerH;
   for(let i=0;i<rows.length;i++){
     if(id!==state.renderId)return;
     const r=makeRow(rows[i],ar,ur);
     if(y+r.height>CONTENT_H&&y>0){
       if(i===0){header.remove();y=beforeHeader;newPage(payload.surah.id,r.first.ayah);content.append(header);y=headerH;}
       else newPage(payload.surah.id,r.first.ayah);
     }
     content.append(r.block);y+=r.height;
     if(++rowCount%18===0){status(`Laying out ${pageNo} pages…`);await tick();}
   }
 }
 rukuMarks();fit();observePages();setPage(targetPage);busy(false);
 status(`${pageNo} A4 pages · ${state.payloads.length} surah${state.payloads.length===1?'':'s'} loaded${warnings?` · ${warnings} ayahs shown whole because their saved alignment/translation is unavailable`:''}`);
 window.mushafReady=true;window.mushafDiagnostics={pages:pageNo,rows:rowCount,warnings,loaded:state.payloads.map(p=>p.surah.id)};
}
async function load(append=false){
 if(state.busy||(append&&state.payloads.at(-1)?.surah.id===114))return;busy(true);window.mushafReady=false;
 const start=append?state.payloads.at(-1).surah.id+1:+$('surahSel').value;
 const end=append?start:Math.max(start,+$('endSel').value),translation=append?state.translation:+$('trSel').value;
 if(append)$('trSel').value=state.translation;
 if(start>114){busy(false);return;}
 try{
   let payloads=[];
   for(let s=start;s<=end;s+=3){status(`Loading surahs ${start}–${end}: ${s}…`);const ids=Array.from({length:Math.min(3,end-s+1)},(_,i)=>s+i);payloads.push(...await Promise.all(ids.map(n=>request(`/surah/${n}?translation_id=${translation}`))));}
   state.translation=translation;state.payloads=append?[...state.payloads,...payloads]:payloads;
   $('surahSel').value=state.payloads[0].surah.id;$('endSel').value=state.payloads.at(-1).surah.id;
   const target=append?state.current:0;await render(target);if(!append)setPage(0,true);
 }catch(e){busy(false);status(`Unable to load the reader: ${e.message}. Choose Read to retry.`,true);window.mushafError=e.message;}
}
async function turnNext(){const total=$('pages').children.length;if(state.current<total-1){setPage(state.current+1,true);return;}if(state.payloads.at(-1)?.surah.id<114){const old=total;await load(true);setPage(Math.min(old,$('pages').children.length-1),true);}}
function onError(e){busy(false);fit();status(`Unable to render: ${e.message}`,true);window.mushafError=e.message;}
let fontTimer;
['arSize','urSize'].forEach(id=>$(id).addEventListener('input',()=>{clearTimeout(fontTimer);fontTimer=setTimeout(()=>{if(!state.busy)render().catch(onError);},180);}));
$('read').onclick=()=>load();$('continue').onclick=()=>load(true);$('prev').onclick=()=>setPage(state.current-1,true);$('next').onclick=turnNext;
$('surahSel').onchange=()=>{if(+$('endSel').value<+$('surahSel').value)$('endSel').value=$('surahSel').value;};
$('print').onclick=()=>{if(window.mushafReady)window.print();};
addEventListener('resize',()=>{if(!state.busy)fit();});
addEventListener('keydown',e=>{if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)||state.busy)return;if(e.key==='ArrowLeft'||e.key==='PageDown'){e.preventDefault();turnNext();}else if(e.key==='ArrowRight'||e.key==='PageUp'){e.preventDefault();setPage(state.current-1,true);}});
(async()=>{
 busy(true);
 try{
   const [surahs,translations,meta,border,header]=await Promise.all([request('/surahs'),request('/translations'),request('/static/mushaf/metadata.json'),request('/static/mushaf/page-border.svg',true),request('/static/mushaf/surah-header.svg',true)]);
   state.surahs=surahs;state.translations=translations;state.structure=L.structure(meta);
   state.border=border.replace(/<svg[^>]*>/,'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="92 72 924 1324" preserveAspectRatio="none">');
   state.header=header.replace(/<svg[^>]*>/,'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1200 490">');
   for(const s of surahs)for(const id of ['surahSel','endSel']){const o=el('option','',`${s.id}. ${s.name_english} — ${s.name_arabic}`);o.value=s.id;$(id).append(o);}
   for(const t of translations){const o=el('option','',t.name);o.value=t.id;$('trSel').append(o);}
   $('surahSel').value=int(query.get('surah'),1,1,114);$('endSel').value=int(query.get('through'),+$('surahSel').value,+$('surahSel').value,114);
   $('trSel').value=translations.some(t=>t.id===state.translation)?state.translation:translations[0].id;
   $('arSize').value=int(query.get('ar'),34,26,42);$('urSize').value=int(query.get('ur'),24,18,32);
   await Promise.all([document.fonts.load('34px Quran'),document.fonts.load('24px Urdu')]);await document.fonts.ready;
   busy(false);await load();setPage(int(query.get('page'),1,1,99999)-1,true);
 }catch(e){onError(e);}
})();
