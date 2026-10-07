import { readFile, realpath } from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { createHash } from 'node:crypto'

const outcomes = new Set(['pass', 'partial', 'fail', 'timeout', 'setup-blocked', 'invalid'])
const cohorts = new Set(['computational', 'limitation-control'])
const unsafe = /(?:localhost|\b127\.\d+\.\d+\.\d+|\b0\.0\.0\.0\b|\[::1\]|file:\/\/|s3:\/\/|\/Users\/|\/home\/|Bearer\s+|X-Amz-(?:Credential|Signature)|[?&](?:token|access_token|api_key|sig)=)/i
const requireValue = (condition, message) => { if (!condition) throw new Error(message) }
const text = value => typeof value === 'string' && value.trim().length > 0
const nullableNumber = value => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0)
const digest = buffer => createHash('sha256').update(buffer).digest('hex')

function publicUrl(value) {
  if (value === null) return
  requireValue(text(value), 'URL must be an HTTPS URL or null')
  const url = new URL(value)
  requireValue(url.protocol === 'https:' && !url.username && !url.password, 'Only public HTTPS URLs are allowed')
  requireValue(!/^(?:10\.|127\.|0\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(url.hostname) && url.hostname.includes('.') && !/\.(?:local|internal|localhost)$/.test(url.hostname) && !url.hostname.includes(':'), 'Private network URLs are not public evidence')
  requireValue(!unsafe.test(value), 'Internal or signed URL found')
}

function safeRecord(value) {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value), 'Expected an object')
  requireValue(!unsafe.test(JSON.stringify(value)), 'Internal link, local path, or credential-like text found')
  for (const url of JSON.stringify(value).match(/https?:\/\/[^\s"<>\\]+/g) || []) publicUrl(url)
}

export function validateManifest(m) {
  safeRecord(m)
  requireValue([1,2].includes(m.schemaVersion) && ['draft','published'].includes(m.status), 'Unknown schema or publication status')
  requireValue(/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(m.releaseId), 'Invalid release ID')
  requireValue(text(m.title), 'Study title is required')
  for (const key of ['system','benchmark','protocol','links']) safeRecord(m[key])
  requireValue(Number.isInteger(m.benchmark.originalTaskCount) && m.benchmark.originalTaskCount > 0, 'Original benchmark count required')
  for (const value of [m.benchmark.url, ...Object.values(m.links), m.protocol.url]) publicUrl(value)
  requireValue(Array.isArray(m.results) && Array.isArray(m.benchmark.selectedTaskIds) && Array.isArray(m.benchmark.exclusions), 'Results, selected tasks and exclusions must be arrays')
  requireValue(Array.isArray(m.limitations) && Array.isArray(m.protocol.adaptations) && Array.isArray(m.sources), 'Limitations, adaptations and sources must be arrays')
  requireValue(m.protocol.attemptsPerTask === 1, 'This publication schema reports one measured attempt per task; do not merge repaired or repeated attempts')
  const selected = m.benchmark.selectedTaskIds
  requireValue(selected.every(id => typeof id === 'string' && /^\d+$/.test(id)) && new Set(selected).size === selected.length, 'Selected task IDs must be unique numeric strings')
  const excluded = m.benchmark.exclusions.map(row => {
    requireValue(typeof row.taskId === 'string' && /^\d+$/.test(row.taskId) && text(row.reason), 'Exclusions require an ID and explanation')
    return row.taskId
  })
  requireValue(new Set(excluded).size === excluded.length && excluded.every(id=>!selected.includes(id)), 'Selected and excluded IDs must be disjoint and unique')
  requireValue(selected.length + excluded.length <= m.benchmark.originalTaskCount, 'Task counts exceed the original benchmark')
  const ids = new Set()
  if (m.schemaVersion === 2) {
    requireValue(m.protocol.selectionPolicy === 'first-valid-primary-v1', 'Explicit first-valid policy required')
    requireValue(['none','bounded','unknown'].includes(m.protocol.toolCallLimitPolicy), 'Tool limit policy required')
    requireValue(Array.isArray(m.attempts) && Array.isArray(m.incidents), 'All-attempt and incident ledgers required')
    requireValue(new Set(m.attempts.map(a=>a.attemptId)).size === m.attempts.length, 'Duplicate attempt identity')
    for (const a of m.attempts) {
      requireValue(text(a.attemptId) && selected.includes(a.taskId) && ['repair','primary','infrastructure','supplemental'].includes(a.role), 'Invalid attempt record')
      requireValue(Number.isFinite(Date.parse(a.startedAt)) && typeof a.infrastructureInvalid === 'boolean', 'Attempt timing/classification required')
      requireValue(a.role === 'repair' || a.studyIdentity === m.studyIdentity, 'Mixed study freeze')
      if (a.infrastructureInvalid) requireValue(m.incidents.some(i=>i.affectedAttemptIds.includes(a.attemptId) && text(i.explanation) && text(i.recoveryProof)), 'Invalidation lacks incident evidence')
    }
  }
  for (const r of m.results) {
    safeRecord(r)
    requireValue(selected.includes(r.taskId) && !ids.has(r.taskId), 'Unexpected or duplicate result task ID')
    ids.add(r.taskId)
    requireValue(text(r.title) && text(r.family) && text(r.explanation), 'Result needs title, family and grading explanation')
    requireValue(outcomes.has(r.outcome) && cohorts.has(r.cohort), 'Unknown outcome or task cohort')
    if (m.schemaVersion === 2) {
      requireValue(typeof r.measurementValid === 'boolean', 'Explicit valid-measurement flag required')
      requireValue(r.measurementValid === !['invalid','setup-blocked'].includes(r.outcome), 'Outcome and measurement denominator disagree')
      const candidates=m.attempts.filter(a=>a.taskId===r.taskId && ['primary','infrastructure'].includes(a.role) && !a.infrastructureInvalid).sort((a,b)=>Date.parse(a.startedAt)-Date.parse(b.startedAt)||a.attemptId.localeCompare(b.attemptId))
      requireValue(r.selectedAttemptId === (candidates[0]?.attemptId ?? null), 'Selected attempt is not the first valid primary candidate')
      if(r.measurementValid) requireValue(text(r.selectedAttemptId) && candidates[0].remoteTerminal === true, 'Valid measurement requires terminal primary evidence')
    }
    requireValue(r.applicationCommit === m.system.applicationCommit && text(r.applicationCommit), 'Mixed or missing application revisions')
    requireValue(nullableNumber(r.durationSeconds) && nullableNumber(r.toolCalls) && nullableNumber(r.totalTokens) && nullableNumber(r.costUsd), 'Missing metrics must be null; measured metrics must be finite and nonnegative')
    for (const key of ['toolCalls','totalTokens']) requireValue(r[key] === null || Number.isInteger(r[key]), 'Measured counts must be integers')
    requireValue(r.evidencePath === `evidence/${r.taskId}.json`, 'Evidence must use the task identity path')
    requireValue(typeof r.evidenceSha256 === 'string' && /^[a-f0-9]{64}$/.test(r.evidenceSha256), 'Evidence SHA-256 is required')
  }
  requireValue(m.representativeTaskId === null || m.results.some(r=>r.taskId===m.representativeTaskId && r.cohort==='computational' && r.outcome==='pass'), 'Representative task must be a recorded computational pass')
  if(m.schemaVersion === 2) {
    requireValue(m.summary?.selected === m.results.length && m.summary?.valid === m.results.filter(r=>r.measurementValid).length, 'Summary coverage disagrees with recorded rows')
    for(const cohort of cohorts) {
      const rows=m.results.filter(r=>r.cohort===cohort), valid=rows.filter(r=>r.measurementValid), passed=valid.filter(r=>r.outcome==='pass').length
      const summary=m.summary[cohort]
      requireValue(summary?.selected===rows.length && summary?.valid===valid.length && summary?.passed===passed && summary?.percent===(valid.length?100*passed/valid.length:null), 'Summary cohort denominator or percentage disagrees')
    }
  }
  for (const s of m.sources) {
    requireValue(text(s.name) && text(s.version) && text(s.attribution) && text(s.license), 'Sources require name, edition, attribution and license')
    requireValue(text(s.url), 'Source download URL is required'); publicUrl(s.url)
    requireValue(typeof s.sha256 === 'string' && /^[a-f0-9]{64}$/.test(s.sha256), 'Source checksum required')
  }
  if (m.status === 'published') {
    requireValue(selected.length > 0 && ids.size === selected.length, 'Every selected task needs a recorded outcome')
    requireValue(selected.length + excluded.length === m.benchmark.originalTaskCount, 'Account for every original task with a result or an explicit exclusion')
    for (const key of ['publishedAt','evaluatedAt']) requireValue(text(m[key]) && Number.isFinite(Date.parse(m[key])), `${key} is required`)
    for (const key of ['name','model','reasoningEffort','runtimeName','runtimeVersion','applicationCommit','instructionHash','toolSchemaHash']) requireValue(text(m.system[key]), `System ${key} is required`)
    requireValue(text(m.benchmark.revision), 'Pinned benchmark revision is required')
    for (const key of ['graderCommit','attemptPolicy','measurement','humanAssistance']) requireValue(text(m.protocol[key]), `Protocol ${key} is required`)
    for (const key of ['timeLimitSeconds','concurrency', ...(m.schemaVersion === 1 || m.protocol.toolCallLimitPolicy === 'bounded' ? ['toolCallLimit'] : [])]) requireValue(Number.isInteger(m.protocol[key]) && m.protocol[key] > 0, `Positive protocol ${key} is required`)
    requireValue(m.sources.length > 0, 'Record source editions and attribution before publication')
  }
  return m
}

async function readOwned(root, relative) {
  requireValue(text(relative) && !path.isAbsolute(relative) && !relative.split(/[\\/]/).includes('..'), 'Evidence path escapes release directory')
  const base = await realpath(root)
  const target = await realpath(path.resolve(root, relative))
  requireValue(target.startsWith(base + path.sep), 'Evidence symlink escapes release directory')
  return readFile(target)
}

export async function validateRelease(root) {
  const manifest = validateManifest(JSON.parse(await readFile(path.join(root,'release.json'), 'utf8')))
  const files = new Map()
  for (const row of manifest.results) {
    const buffer = await readOwned(root,row.evidencePath)
    requireValue(digest(buffer) === row.evidenceSha256, `Evidence checksum mismatch: ${row.taskId}`)
    requireValue(buffer.length <= 1024 * 1024, 'Readable task evidence must remain below 1 MiB')
    const evidence = JSON.parse(buffer)
    safeRecord(evidence)
    requireValue(evidence.taskId === row.taskId && evidence.releaseId === manifest.releaseId, 'Evidence identity does not match result')
    requireValue(text(evidence.question) && text(evidence.activityDisclosure), 'Question and activity export disclosure are required')
    requireValue(evidence.finalAnswer === null || text(evidence.finalAnswer), 'Missing final answer must be null')
    requireValue(row.outcome !== 'pass' || text(evidence.finalAnswer), 'Passing tasks must include the recorded final answer')
    requireValue(Array.isArray(evidence.activity) && Array.isArray(evidence.previews) && Array.isArray(evidence.workflow), 'Evidence needs activity, previews and workflow arrays')
    for (const event of evidence.activity) requireValue(text(event.title) && text(event.detail) && (event.at === null || Number.isFinite(Date.parse(event.at))), 'Activity needs a title, detail and timestamp or null')
    for (const step of evidence.workflow) requireValue(text(step.title) && text(step.description), 'Workflow steps require title and description')
    for (const p of evidence.previews) {
      requireValue(/^assets\/[a-zA-Z0-9_./-]+\.(png|jpg|jpeg|webp)$/.test(p.path), 'Only raster previews in assets/ are allowed')
      requireValue(text(p.alt) && text(p.caption) && text(p.attribution) && text(p.license), 'Previews need alt text, caption, attribution and rights information')
      const image = await readOwned(root,p.path)
      requireValue(image.length <= 5 * 1024 * 1024, 'Compress previews below 5 MiB')
      requireValue(digest(image) === p.sha256, 'Preview checksum mismatch')
      files.set(p.path,image)
    }
    files.set(row.evidencePath,buffer)
  }
  return {manifest,files}
}

function csvCell(value) {
  let cell = value === null || value === undefined ? '' : String(value)
  if (/^[=+@-]/.test(cell)) cell = `'${cell}`
  return `"${cell.replaceAll('"','""')}"`
}
export function resultsCsv(m) {
  const columns=['taskId','title','family','cohort','outcome','measurementValid','selectedAttemptId','durationSeconds','toolCalls','totalTokens','costUsd','applicationCommit','explanation','evidencePath']
  return [columns.join(','),...m.results.map(r=>columns.map(k=>csvCell(r[k])).join(','))].join('\n')+'\n'
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const [action,root] = process.argv.slice(2)
  try {
    requireValue(root && action === 'validate', 'Usage: node scripts/release.mjs validate RELEASE_DIR')
    const {manifest,files}=await validateRelease(root)
    console.log(`Valid ${manifest.status} release: ${manifest.releaseId}; ${manifest.results.length} tasks; ${files.size} evidence files`)
  } catch(error) { console.error(error.message); process.exitCode=1 }
}
