// Inspección visual de las DOS descargas reales con datos exclusivamente ficticios.
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
const require=createRequire(import.meta.url), deps=process.env.ARNOLD_ARTIFACT_NODE_MODULES;
if(!deps) throw new Error('Falta el runtime configurado.');
const {FileBlob,SpreadsheetFile,Workbook}=await import(pathToFileURL(require.resolve('@oai/artifact-tool',{paths:[deps]})).href);
const project=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const root=path.join(project,'outputs','order-presentation');
const manifest=JSON.parse(await fs.readFile(path.join(project,'backend','apps','workflow','order_manifest.json'),'utf8'));
for(const [file,issue] of [['principal-por-orden-sintetico.xlsx',false],['inconsistencias-sinteticas.xlsx',true]]){
  const book=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root,file)));
  console.log((await book.inspect({kind:'sheet',include:'id,name',maxChars:2300})).ndjson);
  for(const template of manifest.sheets.filter(s=>(s.id==='issues')===issue)){
    // Rango breve del bloque de identificación y otro del bloque financiero.
    // Tipos/ceros se comprueban en XML/openpyxl, no mediante inferencia del visor.
    for(const [label,range] of [['identidad','C1:E4'],['importes',Number(template.id)>=36&&template.id!=='issues'?'W1:AE4':'V1:AD4']]){
      const preview=await book.render({sheetName:template.name,range,scale:1.5,format:'png'});
      await fs.writeFile(path.join(root,template.id+'-'+label+'.png'),new Uint8Array(await preview.arrayBuffer()));
    }
  }
}
// Vista de referencia sin personas ni fórmulas: sólo la estructura leída del XML.
const reference=Workbook.create(), sheet=reference.worksheets.add('Referencia 030');
const template=manifest.sheets[0], visible=template.columns.filter(c=>!c.hidden&&c.label);
sheet.getRangeByIndexes(0,0,1,visible.length).values=[visible.map(c=>c.label)];
for(let i=0;i<visible.length;i++) sheet.getRangeByIndexes(0,i,2,1).format.columnWidthPx=Math.max(8,Math.round(visible[i].width*7+5));
sheet.getRangeByIndexes(0,0,1,visible.length).format={fill:template.header_fill,font:{name:'Arial',bold:true,color:'#243E54'},rowHeight:36};
const ref=await reference.render({sheetName:'Referencia 030',range:'A1:C2',scale:1.5,format:'png'});
await fs.writeFile(path.join(root,'referencia-030-sin-datos.png'),new Uint8Array(await ref.arrayBuffer()));
