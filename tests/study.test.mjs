import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtemp,rm} from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {fixture} from './fixtures.mjs'
import {validateManifest} from '../scripts/release.mjs'

async function study(t) {
  const dir=await mkdtemp(path.join(os.tmpdir(),'terra-study-'));t.after(()=>rm(dir,{recursive:true,force:true}))
  const m=await fixture(dir)
  m.schemaVersion=2;m.studyIdentity='same';m.attempts=[];m.incidents=[]
  m.protocol={...m.protocol,selectionPolicy:'first-valid-primary-v1',toolCallLimit:null,toolCallLimitPolicy:'none'}
  for(const r of m.results) {
    r.measurementValid=!['invalid','setup-blocked'].includes(r.outcome)
    r.selectedAttemptId=r.measurementValid?r.taskId:null
    if(r.measurementValid)m.attempts.push({attemptId:r.taskId,taskId:r.taskId,role:'primary',startedAt:'2026-01-01T00:00:00Z',infrastructureInvalid:false,remoteTerminal:true,studyIdentity:'same'})
  }
  m.summary={selected:m.results.length,valid:m.results.filter(r=>r.measurementValid).length}
  for(const cohort of ['computational','limitation-control']) {
    const rows=m.results.filter(r=>r.cohort===cohort),valid=rows.filter(r=>r.measurementValid),passed=valid.filter(r=>r.outcome==='pass').length
    m.summary[cohort]={selected:rows.length,valid:valid.length,passed,percent:valid.length?100*passed/valid.length:null}
  }
  return m
}
test('valid measurements and absent tool cap are explicit',async t=>{
  const m=await study(t);assert.equal(validateManifest(m).results.length,7)
  m.results[4].measurementValid=true;assert.throws(()=>validateManifest(m),/denominator/)
})
test('a later passing attempt cannot replace an earlier valid failure',async t=>{
  const m=await study(t);const r=m.results[2]
  m.attempts.push({...m.attempts[2],attemptId:'later',startedAt:'2026-01-02T00:00:00Z'})
  r.selectedAttemptId='later';assert.throws(()=>validateManifest(m),/first valid/)
})
test('a fabricated summary cannot change the denominator',async t=>{
  const m=await study(t);m.summary.computational.passed+=1
  assert.throws(()=>validateManifest(m),/denominator/)
})
test('infrastructure replacement requires evidence and identical freeze',async t=>{
  const m=await study(t);const r=m.results[0];const a=m.attempts[0]
  a.infrastructureInvalid=true
  m.attempts.push({...a,attemptId:'replacement',role:'infrastructure',infrastructureInvalid:false,startedAt:'2026-01-02T00:00:00Z'})
  r.selectedAttemptId='replacement'
  assert.throws(()=>validateManifest(m),/incident/)
  m.incidents=[{affectedAttemptIds:[a.attemptId],explanation:'Verified host interruption.',recoveryProof:'Recorded healthy restart.'}]
  validateManifest(m)
  m.attempts.at(-1).studyIdentity='changed';assert.throws(()=>validateManifest(m),/freeze/)
})
