import { mkdir, writeFile, readFile } from 'node:fs/promises'
import path from 'node:path'
import { createHash } from 'node:crypto'

export async function fixture(root) {
  const m=JSON.parse(await readFile(new URL('./template.json',import.meta.url),'utf8'))
  m.status='published'; m.title='TEST FIXTURE — not benchmark results'; m.publishedAt=m.evaluatedAt='2026-01-01T00:00:00Z'
  for(const key of Object.keys(m.system)) if(m.system[key]===null) m.system[key]='fixture'
  m.benchmark.revision='fixture';m.benchmark.originalTaskCount=8
  m.protocol={...m.protocol,graderCommit:'fixture',attemptPolicy:'One measured attempt per task',humanAssistance:'None',timeLimitSeconds:1200,toolCallLimit:80,concurrency:4}
  m.sources=[{name:'Synthetic test data',version:'1',url:'https://example.org/data',license:'CC0',attribution:'Local test fixture',sha256:'a'.repeat(64)}]
  m.benchmark.exclusions=[{taskId:'999',reason:'Explicitly excluded synthetic case'}]
  await mkdir(path.join(root,'evidence'),{recursive:true})
  for(const [i,outcome] of ['pass','partial','fail','timeout','setup-blocked','invalid','pass'].entries()) {
    const id=String(100+i)
    const e={releaseId:m.releaseId,taskId:id,question:`TEST FIXTURE: select synthetic features ${id}.`,finalAnswer:outcome==='timeout'?null:'TEST FIXTURE: recorded answer.',activityDisclosure:'Synthetic activity used only in isolated UI tests.',activity:[{at:null,title:'Inspect inputs',detail:'Synthetic fixture record.'}],workflow:[{title:'Select features',description:'Synthetic operation.'}],previews:[]}
    const buf=Buffer.from(JSON.stringify(e,null,2)+'\n')
    await writeFile(path.join(root,`evidence/${id}.json`),buf)
    m.benchmark.selectedTaskIds.push(id)
    m.results.push({taskId:id,title:`TEST FIXTURE ${outcome}`,family:'synthetic',cohort:i===6?'limitation-control':'computational',outcome,durationSeconds:i===0?0:i===1?null:80+i,toolCalls:i===1?null:i,totalTokens:null,costUsd:null,applicationCommit:'fixture',explanation:'Synthetic test result. Not a Terra measurement.',evidencePath:`evidence/${id}.json`,evidenceSha256:createHash('sha256').update(buf).digest('hex')})
  }
  await writeFile(path.join(root,'release.json'),JSON.stringify(m,null,2)+'\n')
  return m
}
