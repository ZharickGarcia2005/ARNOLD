const {test} = require('node:test');
const assert = require('node:assert/strict');
const M = require('../backend/static/js/worksheet-grid-model.js');
const rows = Array.from({length:100}, (_,i)=>({id:`stable-${i}`,source_row:i+2}));
const columns = ['#','QUALITY','CIU','CEDULA_RUC','NOMBRES','CLAVE'].map(field=>({field}));
test('Shift y Ctrl mantienen rangos continuos y separados',()=>{
  const s=new M.Selection(rows,columns); s.choose(0,2); s.choose(3,4,{shift:true});
  assert.equal(s.has(2,3),true); assert.equal(s.has(4,3),false);
  s.choose(8,5,{add:true}); assert.equal(s.ranges.length,2); assert.equal(s.has(2,3),true);
  assert.equal(s.operations({bold:true})[0].rows[3],'stable-3');
});
test('Fila y columna conservan identificadores; columna es global sin 38 mil filas',()=>{
  const s=new M.Selection(rows,columns); s.selectRows(2); assert.equal(s.operations({underline:true})[0].columns.length,6);
  s.selectColumns(4); const op=s.operations({background:'#FFF2CC'})[0];
  assert.equal(op.kind,'columns'); assert.equal(op.rows,undefined); assert.deepEqual(op.columns,['NOMBRES']);
});
test('Repintar la misma página no pierde la selección múltiple',()=>{
  const s=new M.Selection(rows,columns); s.choose(2,2); s.choose(4,4,{shift:true}); s.choose(7,5,{add:true});
  s.setRows(structuredClone(rows),structuredClone(columns)); assert.equal(s.ranges.length,2);
  s.setRows([{id:'another-page',source_row:200}],columns); assert.equal(s.ranges.length,0);
});
test('TSV conserva saltos, comillas y columnas vacías para Excel',()=>{
  const data=[['001','Texto\ncon salto','a"b',''],['=1+1','x\ty','0','']];
  assert.deepEqual(M.parseTSV(M.encodeTSV(data)),data);
  assert.deepEqual(M.parseTSV('a\tb\r\nc\td\r\n'),[['a','b'],['c','d']]);
  assert.throws(()=>M.parseTSV('"sin cierre')); assert.throws(()=>M.parseTSV('a\n'.repeat(101)));
});
test('La presentación no cambia valores y las columnas tienen efecto entre páginas',()=>{
  const doc=M.blank(); M.apply(doc,[{kind:'columns',columns:['NOMBRES'],style:{bold:true,background:'#FFF2CC'}}]);
  assert.equal(M.style(doc,'stable-99','NOMBRES').bold,true);
  M.apply(doc,[{kind:'cells',rows:['stable-99'],columns:['NOMBRES'],reset:true}]);
  assert.deepEqual(M.style(doc,'stable-99','NOMBRES'),{});
  M.apply(doc,[{kind:'cells',rows:['stable-99'],columns:['NOMBRES'],style:{underline:true}}]);
  assert.deepEqual(M.style(doc,'stable-99','NOMBRES'),{underline:true});
});
test('Restaurar tamaños conserva colores y elimina alturas y zoom',()=>{
  const doc=M.blank(); M.apply(doc,[{kind:'width',columns:['CIU'],value:350},{kind:'height',rows:['stable-2'],value:70},{kind:'zoom',value:130},{kind:'columns',columns:['CIU'],style:{color:'#123456'}}]);
  M.apply(doc,[{kind:'reset_sizes'}]); assert.deepEqual(doc.heights,{}); assert.equal(doc.zoom,100); assert.equal(doc.columns.CIU.width,undefined); assert.equal(doc.columns.CIU.style.color,'#123456');
});
test('Formato global de 38.042 filas produce una operación sin enumerarlas',()=>{
  const large=Array.from({length:38042},(_,i)=>({id:`row-${i}`}));
  const s=new M.Selection(large,columns); s.selectColumns(4);
  const ops=s.operations({underline:true}); assert.equal(ops.length,1);
  assert.equal(ops[0].rows,undefined); assert.ok(JSON.stringify(ops).length<150);
});
test('Deshacer agrupa la escritura y conserva el valor inicial, incluidos ceros',()=>{
  const u=new M.DraftUndo();
  u.record([{id:'r1',field:'CIU',before:'001',after:'0012'}],'r1:CIU',1000);
  u.record([{id:'r1',field:'CIU',before:'0012',after:'00123'}],'r1:CIU',1100);
  assert.equal(u.actions.length,1);
  assert.deepEqual(u.take(),[{id:'r1',field:'CIU',before:'001',after:'00123'}]);
  assert.equal(u.available,false);
});
test('Un pegado múltiple se deshace como bloque; limpiar impide revertir guardados',()=>{
  const u=new M.DraftUndo(); const changes=[{id:'r1',field:'NOMBRES',before:'A',after:'B'},{id:'r2',field:'NOMBRES',before:'C',after:'D'}];
  u.record(changes); changes[0].before='mutated';
  assert.equal(u.take()[0].before,'A');
  u.record(changes); u.clear(); assert.deepEqual(u.take(),[]);
});
test('Deshacer acota memoria y descarta escrituras sin cambio neto',()=>{
  const u=new M.DraftUndo(2);
  u.record([{id:'r',field:'x',before:'a',after:'b'}],'r:x',100);
  u.record([{id:'r',field:'x',before:'b',after:'a'}],'r:x',200); assert.equal(u.available,false);
  for(let i=0;i<3;i++) u.record([{id:'r',field:'x',before:String(i),after:String(i+1)}]);
  assert.equal(u.actions.length,2); assert.equal(u.take()[0].before,'2');
  const small=new M.DraftUndo(50,100); small.record([{id:'r',field:'x',before:'a',after:'x'.repeat(1000)}]);
  assert.equal(small.available,false);
});
