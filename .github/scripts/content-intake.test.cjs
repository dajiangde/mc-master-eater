const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const intake = require('./content-intake.cjs');

function setup(action = 'opened', label = '', permission = 'read') {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'mcd-issue-test-'));
  process.env.RUNNER_TEMP = temp;
  process.env.INPUT_ISSUE = ''; process.env.INPUT_IMPORT = '';
  const output = {}, calls = [];
  const context = {repo: {owner: 'test', repo: 'mc-master-eater'}, actor: 'contributor', eventName: 'issues',
    payload: {action, issue: {number: 7}, label: {name: label}}};
  const github = {rest: {
    issues: {get: async () => ({data: {number: 7, body: '### 吃法名称\n\n测试吃法'}})},
    repos: {getCollaboratorPermissionLevel: async () => {calls.push('permission'); return {data: {permission}};}}
  }};
  const core = {setOutput: (key, value) => {output[key] = value;}};
  return {github, context, core, output, calls, cleanup: () => fs.rmSync(temp, {recursive: true, force: true})};
}

test('a normal submission is pending and cannot authorize a write', async () => {
  const state = setup();
  try {
    await intake.assess(state);
    assert.equal(state.output.relevant, 'true'); assert.equal(state.output.authorized, 'false');
    assert.equal(state.output.import_ready, 'false'); assert.deepEqual(state.calls, []);
  } finally {state.cleanup();}
});

test('editing an issue with a previous approval does not reuse approval', async () => {
  const state = setup('edited', 'intake:approve', 'admin');
  try {
    state.context.payload.issue.labels = [{name: 'intake:approve'}];
    await intake.assess(state);
    assert.equal(state.output.authorized, 'false'); assert.equal(state.output.import_ready, 'false');
  } finally {state.cleanup();}
});

test('a maintainer label triggers explicit approval', async () => {
  const state = setup('labeled', 'intake:approve', 'write');
  try {
    await intake.assess(state);
    assert.equal(state.output.authorized, 'true'); assert.equal(state.output.import_ready, 'true');
  } finally {state.cleanup();}
});

test('read-only contributors cannot approve by a label or body', async () => {
  const state = setup('labeled', 'intake:approve');
  try {await assert.rejects(intake.assess(state), /maintainer/);}
  finally {state.cleanup();}
});

test('dispatch validates the issue number as data before API access', async () => {
  const state = setup();
  try {
    process.env.INPUT_ISSUE = '7; touch /tmp/never';
    await assert.rejects(intake.assess(state), /Invalid issue number/);
    assert.deepEqual(state.calls, []);
  } finally {state.cleanup(); process.env.INPUT_ISSUE = '';}
});

test('ordinary issues and PRs are ignored', async () => {
  const state = setup();
  try {
    state.github.rest.issues.get = async () => ({data: {number: 7, body: 'normal bug'}});
    await intake.assess(state); assert.equal(state.output.relevant, 'false');
  } finally {state.cleanup();}
});

test('repeated prepare reuses an existing draft without overwriting', async () => {
  process.env.ISSUE_NUMBER = '7'; process.env.IMPORT_READY = 'false';
  let reused = false;
  await intake.pullRequest({context: {repo: {owner: 'test', repo: 'test'}},
    core: {notice: () => {reused = true;}},
    github: {rest: {pulls: {list: async () => ({data: [{number: 8, html_url: 'https://example.invalid/pr'}]})}}}});
  assert.equal(reused, true);
});

test('approval cannot overwrite human edits in an existing PR', async () => {
  process.env.ISSUE_NUMBER = '7'; process.env.IMPORT_READY = 'true';
  const github = {rest: {pulls: {list: async () => ({data: [{number: 8}]}), listFiles: 'files', listCommits: 'commits'}},
    paginate: async (method) => method === 'files' ? [{filename: 'submissions/issue-7.json'}] : [{author: {type: 'User'}}]};
  await assert.rejects(intake.pullRequest({github, core: {}, context: {repo: {owner: 'test', repo: 'test'}}}), /人工修改/);
});
