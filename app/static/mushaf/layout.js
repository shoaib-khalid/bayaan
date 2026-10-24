/* Shared, DOM-free layout data logic. Arabic and translation stay lossless. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MushafLayout = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const isWord = w => typeof w.is_word === 'boolean' ? w.is_word : /[\u0621-\u064a\u0671-\u06d3\uf658\uf666]/.test(w.text);
  function segments(payload, colorStart = 0) {
    let color = colorStart, warnings = 0;
    const result = [];
    for (const ayah of payload.ayahs) {
      const words = ayah.words, real = words.filter(isWord);
      const saved = [...ayah.segments].sort((a,b) => a.segment_index-b.segment_index);
      const groups = saved.map(s => ({s, words:real.filter(w => w.id>=s.word_start && w.id<=s.word_end)}));
      const covered = groups.flatMap(g=>g.words.map(w=>w.id));
      const valid = covered.length===real.length && covered.every((id,i)=>id===real[i].id) && groups.every(g=>g.words.length);
      const add = (key, ar, ur, last, missing=false) => result.push({key,surah:payload.surah.id,ayah:ayah.ayah_number,ar,ur,last,missing,color:color++%2});
      if (!valid) {
        // Preserve the full ayah when a translation is missing or its saved
        // ranges are incomplete. Never silently drop an Arabic word.
        warnings++;
        add(`${payload.surah.id}:${ayah.ayah_number}:fallback`,words,saved.map(s=>s.translation_text).join(' '),true,!saved.length);
        continue;
      }
      groups.forEach((g,i)=>{
        const first=g.words[0].word_index;
        const next=i+1<groups.length?groups[i+1].words[0].word_index:Infinity;
        const start=i===0?-Infinity:first;
        add(`${payload.surah.id}:${ayah.ayah_number}:${g.s.segment_index}`,words.filter(w=>w.word_index>=start&&w.word_index<next),g.s.translation_text,i===groups.length-1);
      });
    }
    return {segments:result,nextColor:color,warnings};
  }
  function splitText(text, fraction) {
    const ends=[...text.matchAll(/\S+\s*/gu)].map(m=>m.index+m[0].length);
    if (ends.length<2) return [fraction<.5?'':text,fraction<.5?text:''];
    const count=Math.max(1,Math.min(ends.length-1,Math.round(ends.length*fraction)));
    return [text.slice(0,ends[count-1]),text.slice(ends[count-1])];
  }
  function pack(input, width, measureA, measureU, font) {
    const gap=font*.21;
    const natural=ar=>ar.reduce((n,w)=>n+measureA(w.text),0)+Math.max(0,ar.length-1)*gap+10;
    const longest=ur=>Math.max(0,...ur.trim().split(/\s+/u).map(measureU))+12;
    const need=s=>Math.max(natural(s.ar),longest(s.ur));
    const queue=input.map(s=>({...s,ar:[...s.ar]})), rows=[];
    let row=[],used=0;
    const flush=()=>{if(row.length)rows.push(row);row=[];used=0;};
    while(queue.length) {
      let s=queue.shift(), room=width-used, n=need(s);
      if(n<=room+.01){row.push({...s,need:n});used+=n;continue;}
      // Continue the same saved segment on the next line when it can fill the
      // current line. Urdu wraps at word boundaries; its saved text is intact.
      let count=0;
      while(count<s.ar.length && natural(s.ar.slice(0,count+1))<=room)count++;
      if(count && count<s.ar.length && s.ar.slice(count).every(w=>!isWord(w)))count--;
      if(count>0 && count<s.ar.length && (room>width*.22 || !row.length)) {
        let [head,tail]=splitText(s.ur,count/s.ar.length);
        while(count>1 && longest(head)>room){count--;[head,tail]=splitText(s.ur,count/s.ar.length);}
        if(longest(head)<=room){
          const first={...s,ar:s.ar.slice(0,count),ur:head,last:false};
          row.push({...first,need:need(first)});
          queue.unshift({...s,ar:s.ar.slice(count),ur:tail});flush();continue;
        }
      }
      if(row.length){queue.unshift(s);flush();continue;}
      if(natural(s.ar)<=width){row.push({...s,need:width});flush();continue;}
      // A single unusually wide word still renders in full. The renderer
      // fits only that word horizontally; it never truncates its text.
      if(s.ar.length===1){row.push({...s,need:width});flush();continue;}
      count=Math.max(1,count);
      const [head,tail]=splitText(s.ur,count/s.ar.length);
      row.push({...s,ar:s.ar.slice(0,count),ur:head,last:false,need:width});
      queue.unshift({...s,ar:s.ar.slice(count),ur:tail});flush();
    }
    flush();
    return rows;
  }
  function structure(meta) {
    const bySurah=new Map(meta.suras.map(s=>[s.index,s]));
    const ordinal=(s,a)=>bySurah.get(s).start+a;
    const starts=meta.juzs.map(j=>({...j,ordinal:ordinal(j.sura,j.aya)}));
    const juzAt=(s,a)=>starts.filter(j=>j.ordinal<=ordinal(s,a)).at(-1).index;
    const ends=new Map(),surahCounts={},paraCounts={};
    meta.rukus.forEach((r,i)=>{
      const next=meta.rukus[i+1];
      const endS=r.sura;
      const endA=next&&next.sura===r.sura?next.aya-1:bySurah.get(r.sura).ayas;
      const para=juzAt(endS,endA);
      surahCounts[r.sura]=(surahCounts[r.sura]||0)+1;
      if(r.sura!==1)paraCounts[para]=(paraCounts[para]||0)+1;
      ends.set(`${endS}:${endA}`,{surah:surahCounts[r.sura],ayahs:endA-r.aya+1,para:r.sura===1?1:paraCounts[para]});
    });
    return {bySurah,juzAt,ends};
  }
  return {isWord,segments,splitText,pack,structure};
});
