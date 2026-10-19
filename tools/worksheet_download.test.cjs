const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const D = require('../backend/static/js/worksheet-download.js');
const batch = '00000000-0000-0000-0000-000000000001';
const excel = () => new Uint8Array([80,75,3,4,...Array(200).fill(0)]);
const headers = (revision=2) => ({'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'Content-Disposition':'attachment; filename="ARNOLD_clean_2026-10-01_r2.xlsx"',
  'X-ARNOLD-Export-Rows':'3','X-ARNOLD-Export-Revision':String(revision),'X-ARNOLD-Export-Batch':batch});
test('El nombre dinámico viene del servidor, no de la página o del nombre histórico',()=>{
  assert.equal(D.filename(headers()['Content-Disposition']),'ARNOLD_clean_2026-10-01_r2.xlsx');
  assert.equal(D.filename("attachment; filename*=UTF-8''ARNOLD%20prueba.xlsx"),'ARNOLD prueba.xlsx');
  for(const name of ['../../secret.xlsx','bad.exe','x\\y.xlsx','']) assert.throws(()=>D.filename(`attachment; filename="${name}"`));
});
test('Valida revisión, lote, tipo y firma antes de crear descarga',async()=>{
  const options={batch,revision:2,expected:3};
  assert.equal((await D.receive(new Response(excel(),{headers:headers()}),options)).count,3);
  await assert.rejects(D.receive(new Response(excel(),{headers:headers(1)}),options),/revisión/);
  await assert.rejects(D.receive(new Response(excel(),{headers:headers()}),{...options,batch:'other'}),/lote/);
  await assert.rejects(D.receive(new Response('not a zip',{headers:headers()}),options),/Excel válido/);
  await assert.rejects(D.receive(new Response(excel(),{headers:headers()}),{...options,expected:100}),/cantidad/);
});
test('El error empresarial del servidor se conserva',async()=>{
  await assert.rejects(D.receive(new Response(JSON.stringify({error:{message:'La revisión cambió; actualiza.'}}),
    {status:409,headers:{'Content-Type':'application/json'}}),{}),/La revisión cambió/);
});

function app({downloadFails=false, refreshFails=false, saveFails=false}={}) {
  const events=[], nodes=new Map();
  const element=()=>({value:'',textContent:'',style:{},dataset:{},rows:[],cells:[],hidden:false,open:true,disabled:false,
    scrollLeft:0,scrollTop:0,classList:{add(){},remove(){},toggle(){}},replaceChildren(){},append(){},remove(){},
    focus(){},close(){this.open=false;},querySelector(){return null;},querySelectorAll(){return []},
    click(){events.push({kind:'file',name:this.download});}});
  const get=id=>{if(!nodes.has(id))nodes.set(id,element()); return nodes.get(id);};
  get('changeReason').value='Verificación sintética';
  const data={name:'Cartera sintética',summary:{revision:2,clean:3,problem:0,total:3,duplicates:0,pending_approvals:0},
    page:1,filtered_total:0,rows:[],fields:[],columns:[],tabs:[],order:'030',presentation:{version:0},capabilities:{edit:true,export:true},skipped_rules:{}};
  const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
  const context={window:{ArnoldSheetModel:require('../backend/static/js/worksheet-grid-model.js'),ArnoldDownload:D},
    document:{getElementById:get,activeElement:null,createElement:element,createDocumentFragment:element,body:element(),
      querySelector(){return null;},querySelectorAll(){return []}},
    URL:{createObjectURL(){return 'blob:synthetic';},revokeObjectURL(){}},
    AbortSignal,Intl,Uint8Array,Map,Set,setTimeout(){},fetch:async(url,init)=>{
      const payload=JSON.parse(init.body); events.push({kind:url.split('/').filter(Boolean).at(-1),payload});
      if(url.endsWith('save/'))return json(saveFails?{error:{message:'Error de guardado'}}:{applied:['r1'],pending:[]},saveFails?409:200);
      if(url.endsWith('query/'))return json(refreshFails?{error:{message:'Error de actualización'}}:data,refreshFails?503:200);
      if(url.endsWith('download/'))return downloadFails?json({error:{message:'Fallo de descarga sintético'}},503):new Response(excel(),{headers:headers()});
      throw new Error('unexpected URL');
    }};
  vm.createContext(context);
  const source=fs.readFileSync(require.resolve('../backend/static/js/worksheet-app.js'),'utf8')
    .replace('  start();','  window.__test = {state, save, download};');
  vm.runInContext(source,context);
  const api=context.window.__test;
  api.state.batch={id:batch}; api.state.data={...data,summary:{...data.summary,revision:1}};
  api.state.dirty.set('r1',{id:'r1',version:1,values:{NOMBRES:'Persona sintética'}});
  return {api,events,get};
}
test('Guardar y descargar principal espera confirmación y revisión nueva',async()=>{
  const {api,events}=app(); await api.save(true);
  assert.deepEqual(events.map(e=>e.kind),['save','query','download','file']);
  assert.equal(events[2].payload.revision,2); assert.equal(events[2].payload.scope,'clean');
  assert.equal(events[3].name,'ARNOLD_clean_2026-10-01_r2.xlsx');
  assert.equal(api.state.dirty.size,0);
});
test('Si sólo falla la descarga, el reintento NO vuelve a guardar',async()=>{
  const {api,events,get}=app({downloadFails:true}); await api.save(true);
  assert.match(get('globalStatus').textContent,/1 filas guardadas.*Fallo de descarga sintético/);
  assert.equal(api.state.dirty.size,0); await api.download('clean');
  assert.equal(events.filter(e=>e.kind==='save').length,1);
  assert.equal(events.filter(e=>e.kind==='download').length,2);
});
test('Fallo al guardar conserva borrador y no descarga; actualización fallida tampoco descarga',async()=>{
  const failed=app({saveFails:true}); await failed.api.save(true);
  assert.equal(failed.api.state.dirty.size,1); assert.deepEqual(failed.events.map(e=>e.kind),['save']);
  const refresh=app({refreshFails:true}); await refresh.api.save(true);
  assert.equal(refresh.api.state.dirty.size,0); assert.deepEqual(refresh.events.map(e=>e.kind),['save','query']);
});
