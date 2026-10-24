const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const L=require('../app/static/mushaf/layout.js');
const metadata=JSON.parse(fs.readFileSync(path.join(__dirname,'../app/static/mushaf/metadata.json'),'utf8'));
const word=(id,text='word',is_word=true)=>({id,word_index:id,text,is_word});
test('a saved segment crossing many lines retains every Arabic token and Urdu character',()=>{
  const tokens=Array.from({length:22},(_,i)=>word(i+1));tokens.push(word(23,'ornament',false));
  const ur='one  two three\nfour five six seven eight nine ten eleven twelve thirteen fourteen';
  const input=[{key:'2:1:1',ar:tokens,ur,last:true,color:0}];
  const rows=L.pack(input,100,t=>t.length*4,t=>t.length*3,20);
  assert.deepEqual(rows.flat().flatMap(s=>s.ar),tokens);
  assert.equal(rows.flat().map(s=>s.ur).join(''),ur);
  assert.equal(rows.flat().filter(s=>s.last).length,1);
  assert.equal(rows.at(-1).at(-1).ar.at(-1).id,23);
  assert.ok(rows.flat().every(s=>s.color===0));
});
test('wide single Arabic word makes progress without losing text',()=>{
  const rows=L.pack([{key:'x',ar:[word(1,'very-wide-word')],ur:'translation',last:true,color:1}],20,()=>500,()=>100,34);
  assert.equal(rows.length,1);assert.equal(rows[0][0].ar[0].text,'very-wide-word');
});
test('incomplete saved word coverage falls back to the whole ayah',()=>{
  const payload={surah:{id:2},ayahs:[{ayah_number:1,words:[word(1),word(2),word(3,'end',false)],segments:[{segment_index:1,word_start:2,word_end:2,translation_text:'saved'}]}]};
  const r=L.segments(payload);assert.equal(r.warnings,1);assert.deepEqual(r.segments[0].ar,payload.ayahs[0].words);assert.equal(r.segments[0].ur,'saved');
});
test('untranslated ayahs keep their Arabic and expose an explicit missing state',()=>{
  const r=L.segments({surah:{id:1},ayahs:[{ayah_number:1,words:[word(1)],segments:[]}]});
  assert.equal(r.segments[0].missing,true);assert.equal(r.segments[0].ar.length,1);
});
test('segment colours alternate continuously across ayahs',()=>{
  const r=L.segments({surah:{id:2},ayahs:[1,2,3].map(n=>({ayah_number:n,words:[word(n)],segments:[{segment_index:1,word_start:n,word_end:n,translation_text:'text'}]}))});
  assert.deepEqual(r.segments.map(s=>s.color),[0,1,0]);
});
test('Quran structure covers all surahs and resolves para transitions and sample ruku marks',()=>{
  const m=L.structure(metadata);assert.equal(m.bySurah.size,114);
  assert.equal(m.juzAt(2,141),1);assert.equal(m.juzAt(2,142),2);assert.equal(m.juzAt(114,6),30);
  assert.deepEqual(m.ends.get('2:7'),{surah:1,ayahs:7,para:1});
  assert.deepEqual(m.ends.get('2:20'),{surah:2,ayahs:13,para:2});
  assert.equal(m.ends.get('2:286').surah,40);
});
