import {modeConfig,guardSource} from '../../../Alcor/packages/alcor-plugin-info/src/host-policy.js'
import { registerBundledSkills } from '../../../Alcor/packages/alcor-organizer/src/skills.js'
import { fileURLToPath } from 'node:url'
import { readFile } from 'node:fs/promises'
import { join, toNamespacedPath } from 'node:path'
import { Service } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import { dshHomePath } from '@deepseek-ai/dsh-home-paths'
import MailConnection from './connection.js'
import { remote, schemas } from './remote.js'
import { initializeProfile } from '../../../Alcor/packages/alcor-organizer/src/profile-migration.js'

class MailRemote extends TypertRemoteService {
  static inject = ['typert', 'alcorMailConnection']
  constructor(ctx) { super(ctx, 'alcorMail', { namespace: 'alcorMail' }) }
  async [Service.init]() { this.ctx.typert.register({ package: '@alcor/mail', face: 'host', schemas: [], invocations: remote.descriptors, model: { services: [], events: [], objects: [] } }) }
  private checkOwner() {
    const call = this.ctx.invocation
    if (call?.peer?.principal?.kind !== 'owner' || call.signal.aborted || call.peer.signal.aborted) throw new Error('请在本机插件设置中管理邮箱。')
  }
  @Remote state(request) { this.checkOwner(); schemas.state[0].parse(request); return this.ctx.alcorMailConnection.state() }
  @Remote save(request) { this.checkOwner(); return this.ctx.alcorMailConnection.save(request) }
  @Remote removeAccount(request) { this.checkOwner(); return this.ctx.alcorMailConnection.remove(request) }
  @Remote check(request) { this.checkOwner(); return this.ctx.alcorMailConnection.check(request) }
}
export const inject = ['credentials', 'authorization', 'tools', 'typert']
export const Config=modeConfig('both')
export async function apply(ctx, config) {
  const selected = ctx.get('profileContext')?.startedBundles
  if (!Array.isArray(selected)) throw new Error('无法确认当前 Profile 的插件，已停止 Alcor 启动。')
  if (selected.includes('@stella/mail')) throw new Error('旧版 Stella 插件与 Alcor 不能同时启用，请先迁移 Profile。')
  const directory = fileURLToPath(new URL('../server/', import.meta.url))
  const { target } = JSON.parse(await readFile(join(directory, 'platform.json'), 'utf8'))
  if (target !== `${process.platform}-${process.arch}`) throw new Error(`此安装包适用于 ${target}，请安装当前平台的版本。`)
  const command = toNamespacedPath(join(directory, process.platform === 'win32' ? 'email-mcp.exe' : 'email-mcp'))
  const cwd = toNamespacedPath(directory)
  await initializeProfile(ctx)
  registerBundledSkills(ctx, 'alcor-mail', new URL('../skills/', import.meta.url))
  guardSource(ctx,config,'mcp__email__')
  const profile = ctx.get('profileContext')?.dir ?? dshHomePath('profiles', 'default')
  await ctx.plugin(MailConnection, { command, cwd, dataDir: join(profile, 'alcor', 'email') }).await()
  await ctx.plugin(MailRemote).await()
}
