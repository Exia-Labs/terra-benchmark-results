import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, readFile, rm, symlink } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { validateManifest, validateRelease, resultsCsv } from '../scripts/release.mjs'

import { fixture } from './fixtures.mjs'
async function temporary(t) {const dir=await mkdtemp(path.join(os.tmpdir(),'terra-publication-'));t.after(()=>rm(dir,{recursive:true,force:true}));return dir}
test('draft has no scores or measured tasks',async()=>{
  const manifest=validateManifest(JSON.parse(await readFile(new URL('./template.json',import.meta.url),'utf8')))
  assert.equal(manifest.status,'draft');assert.deepEqual(manifest.results,[])
})
test('all outcome classes, missing metrics, zero and explicit exclusions are valid',async t=>{
  const root=await temporary(t);const m=await fixture(root)
  assert.equal(validateManifest(m).results.length,7)
  assert.equal((await validateRelease(root)).files.size,7)
})
test('mixed revisions, missing tasks, duplicate identities and bad denominators are rejected',async t=>{
  const root=await temporary(t);const original=await fixture(root)
  for(const edit of [m=>m.results[0].applicationCommit='different',m=>m.results.pop(),m=>m.results[1].taskId=m.results[0].taskId,m=>m.benchmark.originalTaskCount=9]) {
    const m=structuredClone(original);edit(m);assert.throws(()=>validateManifest(m))
  }
})
test('unknown outcomes and accidental internal links fail validation',async t=>{
  const root=await temporary(t);const original=await fixture(root)
  for(const edit of [m=>m.results[0].outcome='success',m=>m.links.repository='http://localhost:5173',m=>m.links.artifacts='https://10.0.0.2/file',m=>m.results[0].explanation='Stored at /Users/person/private/file']) {
    const m=structuredClone(original);edit(m);assert.throws(()=>validateManifest(m))
  }
})
test('missing, changed and wrong-identity evidence fails validation',async t=>{
  const root=await temporary(t);const m=await fixture(root)
  await writeFile(path.join(root,'evidence/100.json'),'{}')
  await assert.rejects(validateRelease(root),/checksum/)
  await rm(path.join(root,'evidence/100.json'))
  await assert.rejects(validateRelease(root),/ENOENT/)
  const e=JSON.parse(await readFile(path.join(root,'evidence/101.json'),'utf8'));e.taskId='999'
  const buf=Buffer.from(JSON.stringify(e));m.results[0].evidenceSha256=createHash('sha256').update(buf).digest('hex')
  await writeFile(path.join(root,'evidence/100.json'),buf);await writeFile(path.join(root,'release.json'),JSON.stringify(m))
  await assert.rejects(validateRelease(root),/identity/)
})

test('CSV escapes quotes and spreadsheet formulas',()=>{
  const csv=resultsCsv({results:[{taskId:'1',title:'=FORMULA()',explanation:'Line "quoted"\nnext'}]})
  assert.ok(csv.includes('"\'=FORMULA()"'));assert.ok(csv.includes('"Line ""quoted""\nnext"'))
})

test('previews require rights, checksum and in-package paths',async t=>{
  const root=await temporary(t);const m=await fixture(root)
  const e=JSON.parse(await readFile(path.join(root,'evidence/100.json'),'utf8'))
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jT0YAAAAASUVORK5CYII=','base64')
  await mkdir(path.join(root,'assets'));await writeFile(path.join(root,'assets/test.png'),png)
  e.previews=[{path:'assets/test.png',alt:'Synthetic test pixel',caption:'Test only',attribution:'Synthetic fixture',license:'CC0',sha256:createHash('sha256').update(png).digest('hex')}]
  const save=async()=>{const buf=Buffer.from(JSON.stringify(e));m.results[0].evidenceSha256=createHash('sha256').update(buf).digest('hex');await writeFile(path.join(root,'evidence/100.json'),buf);await writeFile(path.join(root,'release.json'),JSON.stringify(m))}
  await save();assert.equal((await validateRelease(root)).files.size,8)
  e.previews[0].license='';await save();await assert.rejects(validateRelease(root),/rights/)
  e.previews[0].license='CC0';e.previews[0].path='assets/../../outside.png';await save();await assert.rejects(validateRelease(root),/escapes/)
  const outside=await temporary(t);await writeFile(path.join(outside,'other.png'),png)
  await symlink(path.join(outside,'other.png'),path.join(root,'assets/link.png'))
  e.previews[0].path='assets/link.png';await save();await assert.rejects(validateRelease(root),/symlink/)
})
