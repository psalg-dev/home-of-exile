export async function importPob(exportCode) {
  const resp = await fetch('/api/import/pob', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ exportCode })
  })

  const contentType = resp.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')
  const data = isJson ? await resp.json() : null

  if (!resp.ok) {
    const message = data?.error?.message || `Request failed (${resp.status})`
    const details = data?.error?.details || []
    const err = new Error(message)
    err.code = data?.error?.code
    err.details = details
    throw err
  }

  return data
}
