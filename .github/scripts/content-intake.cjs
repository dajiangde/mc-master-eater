// This code is loaded only from the trusted default branch. Issue text is data.
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const pipeline = 'skills/mcd-hidden-explorer/scripts/content_pipeline.py';
const content = 'skills/mcd-hidden-explorer/content';

exports.assess = async ({github, context, core}) => {
  const number = Number(process.env.INPUT_ISSUE || context.payload.issue?.number);
  if (!Number.isSafeInteger(number) || number <= 0) throw new Error('Invalid issue number');
  const {data: issue} = await github.rest.issues.get({...context.repo, issue_number: number});
  const relevant = !issue.pull_request && /^### 吃法名称$/m.test(issue.body || '');
  core.setOutput('relevant', String(relevant));
  core.setOutput('issue_number', String(number));
  if (!relevant) return;
  fs.writeFileSync(path.join(process.env.RUNNER_TEMP, 'intake-issue.json'), JSON.stringify(issue));
  const label = context.payload.action === 'labeled' ? context.payload.label?.name : '';
  const requested = context.eventName === 'workflow_dispatch' || ['intake:prepare', 'intake:approve'].includes(label);
  let authorized = false;
  if (requested) {
    const {data} = await github.rest.repos.getCollaboratorPermissionLevel({...context.repo, username: context.actor});
    authorized = ['admin', 'maintain', 'write'].includes(data.permission);
    if (!authorized) throw new Error('Only a maintainer may prepare or approve intake');
  }
  core.setOutput('authorized', String(authorized));
  core.setOutput('import_ready', String(authorized && (label === 'intake:approve' || process.env.INPUT_IMPORT === 'true')));
};

exports.report = async ({github, context, core}) => {
  const file = path.join(process.env.RUNNER_TEMP, 'submission.json');
  const result = spawnSync('python', [pipeline, 'check-submission', '--submission', file], {encoding: 'utf8'});
  const row = JSON.parse(fs.readFileSync(file, 'utf8'));
  const issueNumber = Number(row.key.replace('issue-', ''));
  const marker = '<!-- mc-master-eater-intake -->';
  const detail = result.status === 0 ? '结构检查通过；仍须维护者核对配方、商品和图片依据。' :
    '待补充：' + (JSON.parse(result.stderr.trim() || '{"error":"检查失败"}').error);
  const body = `${marker}\n${detail}\n\n` +
    '两种入口使用相同的投稿 JSON。维护者可加 `intake:prepare` 生成待审 PR；资料完成后，加 `intake:approve` 制卡、收录并生成完整安装包检查 PR。\n\n' +
    '若已有待审 PR，请在该 PR 完成资料并运行本地收录器，或关闭并删除该分支后重新触发。检查通过不等于真实门店可售、试吃通过或已经发布。';
  const comments = await github.paginate(github.rest.issues.listComments, {...context.repo, issue_number: issueNumber});
  const previous = comments.find(c => c.user?.type === 'Bot' && c.body?.startsWith(marker));
  if (previous) await github.rest.issues.updateComment({...context.repo, comment_id: previous.id, body});
  else await github.rest.issues.createComment({...context.repo, issue_number: issueNumber, body});
  await core.summary.addRaw(body.replace(marker, '')).write();
};

exports.pullRequest = async ({github, context, core}) => {
  const number = Number(process.env.ISSUE_NUMBER);
  if (!Number.isSafeInteger(number) || number <= 0) throw new Error('Invalid issue number');
  const branch = `codex/intake-issue-${number}`;
  const head = `${context.repo.owner}:${branch}`;
  const {data: existing} = await github.rest.pulls.list({...context.repo, head, state: 'open'});
  const ready = process.env.IMPORT_READY === 'true';
  if (existing.length && !ready) {
    core.notice(`已有待审 PR，保留维护者编辑：${existing[0].html_url}`);
    return;
  }
  if (existing.length) {
    const changed = await github.paginate(github.rest.pulls.listFiles, {...context.repo, pull_number: existing[0].number});
    const commits = await github.paginate(github.rest.pulls.listCommits, {...context.repo, pull_number: existing[0].number});
    if (changed.some(f => f.filename !== `submissions/issue-${number}.json`) ||
        commits.some(c => c.author?.type !== 'Bot')) {
      throw new Error('已有 PR 含人工修改或已收录内容，保留该分支；请在原 PR 使用本地收录器完成，不覆盖编辑');
    }
  }
  const defaultBranch = context.payload.repository.default_branch;
  const {data: base} = await github.rest.git.getRef({...context.repo, ref: `heads/${defaultBranch}`});
  const {data: commit} = await github.rest.git.getCommit({...context.repo, commit_sha: base.object.sha});
  const submission = `submissions/issue-${number}.json`;
  const files = [submission];
  if (process.env.IMPORT_READY === 'true') {
    const catalog = JSON.parse(fs.readFileSync(`${content}/catalog.json`, 'utf8'));
    const recipe = catalog.recipes.find(r => r.key === `issue-${number}`);
    if (!recipe) throw new Error('Imported recipe missing');
    files.push(`${content}/catalog.json`, `${content}/${recipe.card.path}`, `${content}/${recipe.thumbnail.path}`);
  }
  const tree = [];
  for (const file of files) {
    const {data: blob} = await github.rest.git.createBlob({...context.repo,
      content: fs.readFileSync(file).toString('base64'), encoding: 'base64'});
    tree.push({path: file, mode: '100644', type: 'blob', sha: blob.sha});
  }
  // Use the exact checked-out base. A moving default branch must never be overwritten.
  const localHead = spawnSync('git', ['rev-parse', 'HEAD'], {encoding: 'utf8'}).stdout.trim();
  if (base.object.sha !== localHead) throw new Error('主分支已变化，请重新运行；不覆盖新收录');
  const {data: newTree} = await github.rest.git.createTree({...context.repo, base_tree: commit.tree.sha, tree});
  const parents = existing.length ? [...new Set([existing[0].head.sha, base.object.sha])] : [base.object.sha];
  const {data: newCommit} = await github.rest.git.createCommit({...context.repo,
    message: `Prepare hidden recipe from issue #${number}`, tree: newTree.sha, parents});
  if (existing.length) {
    await github.rest.git.updateRef({...context.repo, ref: `heads/${branch}`, sha: newCommit.sha, force: false});
    await github.rest.pulls.update({...context.repo, pull_number: existing[0].number,
      title: `收录隐藏吃法 #${number}`});
    await core.summary.addLink('已更新待审 PR', existing[0].html_url).write();
    return;
  }
  await github.rest.git.createRef({...context.repo, ref: `refs/heads/${branch}`, sha: newCommit.sha});
  const {data: pr} = await github.rest.pulls.create({...context.repo, head: branch, base: defaultBranch, draft: true,
    title: `${ready ? '收录' : '待审'}隐藏吃法 #${number}`,
    body: `来自 #${number}。${ready ? '已通过共用收录器制卡和商品配置检查；请审核图片、来源及完整安装包检查。' :
      '待审资料使用与本地添加相同的格式。补齐商品、来源和图片使用依据后，运行 content_pipeline.py add，将生成的资料和卡片提交到本 PR。'}\n\n` +
      '合并前须通过 Content and installable Skill 检查。机器人创建的 PR 可能需要维护者点击 Approve workflows to run。合并后自动构建完整 ZIP；正式发布通过单独的 Release reviewed Skill 工作流。'});
  await github.rest.issues.createComment({...context.repo, issue_number: number, body: `已生成待审 PR：${pr.html_url}`});
  await core.summary.addLink('待审 PR', pr.html_url).write();
};
