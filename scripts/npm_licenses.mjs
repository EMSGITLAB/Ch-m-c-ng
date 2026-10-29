import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const lock=JSON.parse(await fs.readFile(path.join(root,'frontend/package-lock.json'),'utf8'));
const records=[];
for(const [location,entry] of Object.entries(lock.packages)){
 if(!location)continue;
 let metadata={};
 try{metadata=JSON.parse(await fs.readFile(path.join(root,'frontend',location,'package.json'),'utf8'));}catch{}
 records.push({name:metadata.name||location,version:entry.version,license:metadata.license||entry.license||'Check bundled LICENSE',source:entry.resolved||''});
}
await fs.writeFile(path.join(root,'evidence/m0/frontend-licenses.json'),JSON.stringify(records,null,2));
console.log(`Collected license metadata for ${records.length} frontend packages`);
