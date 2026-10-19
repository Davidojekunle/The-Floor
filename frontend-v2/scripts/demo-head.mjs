// Sample data for exploring The Floor as a head. Goes through the real API, so every rule applies.
//
//   node scripts/demo-head.mjs            (backend must be running on :8000)
//
// Builds on the backend seed's head account (head@example.com) and creates it if missing.
// Safe to run again: it skips rooms that already exist. Every account's password is password123.

const API = process.env.API_URL ?? 'http://localhost:8000/api/v1'
const PASSWORD = 'password123'
const TZ = 'Africa/Lagos'

async function call(method, path, token, body) {
  const res = await fetch(API + path, {
    method,
    headers: { ...(body ? { 'content-type': 'application/json' } : {}), ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) {
    const err = new Error(`${method} ${path} → ${res.status} ${data?.error?.code}: ${data?.error?.message}`)
    err.code = data?.error?.code
    throw err
  }
  return data
}

async function user(name, email) {
  try {
    await call('POST', '/auth/register', null, { name, email, password: PASSWORD, timezone: TZ })
  } catch (e) {
    if (e.code !== 'CONFLICT') throw e // already registered
  }
  const { access_token } = await call('POST', '/auth/login', null, { email, password: PASSWORD })
  const me = await call('GET', '/me', access_token)
  return { name, email, token: access_token, id: me.id, rooms: me.rooms }
}

/** End of the day `days` from today, Lagos time (UTC+1), as ISO UTC. */
const due = (days) => {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() + days)
  d.setUTCHours(22, 59, 59, 0)
  return d.toISOString()
}

async function join(member, room, head, { approve = true } = {}) {
  try {
    const m = await call('POST', `/join/${room.invite_code}`, member.token)
    if (approve) await call('POST', `/rooms/${room.id}/join-requests/${m.membership_id}/approve`, head.token)
  } catch (e) {
    if (!['ALREADY_MEMBER', 'ALREADY_REQUESTED'].includes(e.code)) throw e
  }
}

async function memberId(room, head, person) {
  const page = await call('GET', `/rooms/${room.id}/members?limit=100`, head.token)
  return page.items.find((m) => m.user.id === person.id).membership_id
}

/** Move a stage through statuses in order, e.g. ['in_progress', 'done']. */
async function setStatuses(room, head, task, stageIndex, steps, reason) {
  let t = task
  for (const status of steps) {
    const stage = t.stages[stageIndex]
    t = await call('PUT', `/rooms/${room.id}/tasks/${t.id}/stages/${stage.id}/status`, head.token, {
      status,
      blocked_reason: status === 'blocked' ? reason : null,
    })
  }
  return t
}

const hasRoom = (person, name) => person.rooms.find((r) => r.name === name)

async function main() {
  const ada = await user('Ada', 'head@example.com')
  const people = {}
  for (const [key, name] of [
    ['chidi', 'Chidi Eze'],
    ['zainab', 'Zainab Bello'],
    ['kemi', 'Kemi Adebayo'],
    ['femi', 'Femi Balogun'],
    ['ifeoma', 'Ifeoma Okafor'],
    ['daniel', 'Daniel Mensah'],
    ['bisi', 'Bisi Adeyemi'],
    ['funmi', 'Funmi Adeyinka'],
  ]) {
    people[key] = await user(name, `${key}@example.com`)
  }
  const { chidi, zainab, kemi, femi, ifeoma, daniel, bisi, funmi } = people

  // ---------------------------------------------------------------- Lagos Fashion Week (Ada is head)
  if (hasRoom(ada, 'Lagos Fashion Week')) {
    console.log('• Lagos Fashion Week already exists, skipping')
  } else {
    const room = await call('POST', '/rooms', ada.token, { name: 'Lagos Fashion Week' })
    for (const p of [chidi, zainab, kemi, femi]) await join(p, room, ada)
    for (const p of [ifeoma, daniel]) await join(p, room, ada, { approve: false }) // left waiting

    const tag = {}
    for (const name of ['Camera', 'Graphic Designer', 'Scriptwriter', 'Video Editor']) {
      tag[name] = (await call('POST', `/rooms/${room.id}/tags`, ada.token, { name })).id
    }
    const setTags = async (p, names) =>
      call('PATCH', `/rooms/${room.id}/members/${await memberId(room, ada, p)}`, ada.token, { tag_ids: names.map((n) => tag[n]) })
    await setTags(chidi, ['Video Editor', 'Camera'])
    await setTags(zainab, ['Graphic Designer'])
    await setTags(kemi, ['Scriptwriter', 'Graphic Designer'])
    await setTags(femi, ['Camera'])

    const task = (title, days, stages, description) =>
      call('POST', `/rooms/${room.id}/tasks`, ada.token, { title, description, due_date: due(days), stages })

    // Blocked
    let t = await task('Poster series', 3, [
      { title: 'Concepts', tag_id: tag['Graphic Designer'] },
      { title: 'Drafts', tag_id: tag['Graphic Designer'] },
      { title: 'Print files', assignee_ids: [zainab.id] },
    ], 'Three A2 posters for the runway nights, plus square crops for social.')
    t = await setStatuses(room, ada, t, 0, ['done'])
    await setStatuses(room, ada, t, 1, ['in_progress', 'blocked'], 'Waiting on the final logo files from the sponsor.')

    // Overdue
    t = await task('Runway teaser', -2, [
      { title: 'Script', tag_id: tag['Scriptwriter'] },
      { title: 'Shoot', tag_id: tag['Camera'], assignee_ids: [chidi.id] },
      { title: 'Edit', tag_id: tag['Video Editor'] },
    ], '30-second teaser for Instagram and TikTok.')
    await setStatuses(room, ada, t, 0, ['done'])

    // Parallel stages, with a stage for Ada
    t = await task('Behind-the-scenes reel', 12, [
      { title: 'Photos', assignee_ids: [zainab.id] },
      { title: 'Clips', tag_id: tag['Camera'], parallel_with_previous: true },
      { title: 'Cut', assignee_ids: [ada.id] },
    ])
    await setStatuses(room, ada, t, 0, ['in_progress'])

    // Ada's own first stage is ready
    await task('Sponsor thank-you video', 20, [
      { title: 'Write the script', assignee_ids: [ada.id] },
      { title: 'Record', tag_id: tag['Camera'] },
      { title: 'Edit', tag_id: tag['Video Editor'] },
    ])

    // Finished
    t = await task('Press kit', -5, [
      { title: 'Copy', tag_id: tag['Scriptwriter'] },
      { title: 'Layout', tag_id: tag['Graphic Designer'] },
    ])
    t = await setStatuses(room, ada, t, 0, ['done'])
    await setStatuses(room, ada, t, 1, ['done'])

    await call('POST', `/rooms/${room.id}/templates`, ada.token, {
      name: 'Poster',
      stages: [
        { title: 'Concepts', tag_id: tag['Graphic Designer'], parallel_with_previous: false },
        { title: 'Drafts', tag_id: tag['Graphic Designer'], parallel_with_previous: false },
        { title: 'Print files', tag_id: null, parallel_with_previous: false },
      ],
    })
    console.log('✓ Lagos Fashion Week: 5 members, 4 tags, 5 tasks, 1 template, 2 join requests')
  }

  // ---------------------------------------------------------------- Studio Alpha (from the backend seed): more join requests
  const studio = ada.rooms.find((r) => r.name === 'Studio Alpha')
  if (studio) {
    const room = await call('GET', `/rooms/${studio.id}`, ada.token)
    if (room.invite_code) for (const p of [bisi, daniel]) await join(p, room, ada, { approve: false })
    console.log('✓ Studio Alpha: added join requests from Bisi and Daniel')
  }

  // ---------------------------------------------------------------- Class Project (Ada is a plain member)
  if (hasRoom(funmi, 'Class Project')) {
    console.log('• Class Project already exists, skipping')
  } else {
    const room = await call('POST', '/rooms', funmi.token, { name: 'Class Project' })
    for (const p of [ada, kemi]) await join(p, room, funmi)
    const research = (await call('POST', `/rooms/${room.id}/tags`, funmi.token, { name: 'Research' })).id
    await call('PATCH', `/rooms/${room.id}/members/${await memberId(room, funmi, ada)}`, funmi.token, { tag_ids: [research] })
    const t = await call('POST', `/rooms/${room.id}/tasks`, funmi.token, {
      title: 'Survey analysis',
      due_date: due(4),
      stages: [
        { title: 'Collect responses', tag_id: research },
        { title: 'Clean data', assignee_ids: [ada.id] },
        { title: 'Charts', assignee_ids: [kemi.id] },
      ],
    })
    await setStatuses(room, funmi, t, 0, ['done'])
    await call('POST', `/rooms/${room.id}/tasks`, funmi.token, {
      title: 'Literature review',
      due_date: due(9),
      stages: [{ title: 'Find sources', tag_id: research }, { title: 'Summaries', tag_id: research }],
    })
    console.log('✓ Class Project: Ada is a member with the Research tag and 2 stages to work on')
  }

  console.log('\nSign in at http://localhost:5174 as head@example.com / password123')
}

main().catch((e) => {
  console.error('✗', e.message)
  process.exit(1)
})
