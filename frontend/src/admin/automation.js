import { appUrl } from '../shared/api.js';

export function adminAutomationUrls() {
  const absolute = (path) => new URL(appUrl(path), window.location.origin).href;
  return {
    base: absolute('/').replace(/\/$/, ''),
    manifest: absolute('/admin/automation'),
    skill: absolute('/admin/automation/skill/SKILL.md'),
    schema: absolute('/admin/v1/openapi.json'),
  };
}

export function adminAutomationPrompt(tr) {
  const urls = adminAutomationUrls();
  return [
    tr('请通过 UMEKO 管理 API 帮我管理此服务器，仅执行我明确提出的管理任务。'),
    tr('管理服务基址：{url}', { url: urls.base }),
    tr('先下载并阅读管理 Skill：{url}', { url: urls.skill }),
    tr('完整 Skill 文件清单与版本：{url}；按清单下载引用文档和 Python 调用脚本，保留目录结构。', {
      url: urls.manifest,
    }),
    tr('管理员登录后读取当前接口规范：{url}', { url: urls.schema }),
    tr(
      '登录使用本地环境变量 UMEKO_ADMIN_URL、UMEKO_ADMIN_USERNAME、UMEKO_ADMIN_PASSWORD，或我已有的管理员 Cookie 会话。不要要求我把密码或密钥粘贴进对话；用户登录和机器任务 Token 不能代替管理员身份。',
    ),
    tr(
      '收到具体管理要求前，只验证身份并读取概览；按需读取状态、修改指定配置并回读确认，不自动扩大权限、批准代码或清理数据。',
    ),
    tr(
      '基址已含管理前缀；接口路径仍使用 /admin/...，不要重复拼接，也不要使用用户服务或 Provider 地址。',
    ),
  ].join('\n');
}
