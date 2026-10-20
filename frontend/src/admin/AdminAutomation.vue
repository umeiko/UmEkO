<script setup>
import { computed, ref } from 'vue';
import UiIcon from '../shared/UiIcon.vue';
import UiModal from '../shared/UiModal.vue';
import { copyText } from '../shared/clipboard.js';
import { useAdminI18n } from '../shared/adminI18n.js';
import { notify } from './state.js';
import { adminAutomationPrompt, adminAutomationUrls } from './automation.js';
defineProps({ compact: Boolean });
const { tr } = useAdminI18n();
const open = ref(false);
const prompt = computed(() => adminAutomationPrompt(tr));
const urls = adminAutomationUrls();
async function copy() {
  try {
    await copyText(prompt.value);
    notify(tr('AI 管理接入提示词已复制'));
  } catch {
    notify(tr('复制失败'), true);
  }
}
</script>
<template>
  <div class="admin-automation" :class="{ compact }">
    <button
      type="button"
      data-admin-automation-open
      :title="tr('使用AI来配置')"
      :aria-label="tr('使用AI来配置')"
      @click="open = true"
    >
      <UiIcon name="terminal" :size="16" /><span>{{ tr('使用AI来配置') }}</span>
    </button>
  </div>
  <UiModal
    v-model="open"
    :title="tr('使用AI来配置')"
    class="automation-modal"
    initial-focus=".modal-header > button"
    data-admin-automation-dialog
  >
    <div class="automation-guide">
      <div class="automation-intro">
        <h3>{{ tr('将这些提示词交给你的本地 Agent') }}</h3>
        <p>
          {{
            tr(
              '让能访问本服务的 AI，按你的要求配置模型、智能体、技能和权限。你也可以下载完整 Skill，安装到常用的 AI 客户端。',
            )
          }}
        </p>
      </div>
      <ol class="automation-steps">
        <li>
          <strong>{{ tr('复制并说明目标') }}</strong
          ><span>{{ tr('把下方提示词粘贴给本地 Agent，再补充这次需要完成的配置。') }}</span>
        </li>
        <li>
          <strong>{{ tr('在本地配置管理员身份') }}</strong
          ><span>{{
            tr(
              '在 Agent 运行环境设置管理员账号与密码，或使用已有的管理员会话。不要把凭据发进聊天。',
            )
          }}</span>
        </li>
        <li>
          <strong>{{ tr('执行后回读验证') }}</strong
          ><span>{{
            tr(
              'Agent 会读取当前接口规范、修改指定配置并确认结果；发布智能体时可按包内指南做冒烟测试。',
            )
          }}</span>
        </li>
      </ol>
      <section class="automation-prompt">
        <div class="automation-section-head">
          <label for="admin-automation-prompt">{{ tr('交给 Agent 的提示词') }}</label>
          <button type="button" data-admin-automation-copy @click="copy">
            <UiIcon name="copy" :size="15" />{{ tr('复制提示词') }}
          </button>
        </div>
        <textarea
          id="admin-automation-prompt"
          :value="prompt"
          readonly
          rows="8"
          spellcheck="false"
        ></textarea>
      </section>
      <section class="automation-package">
        <UiIcon name="skills" :size="24" />
        <div class="grow">
          <strong>{{ tr('完整管理 Skill') }}</strong>
          <p>
            {{
              tr(
                '内含平台介绍、配置指引、完整 API 文档、智能体发布与冒烟测试方法，以及 Python 调用脚本。',
              )
            }}
          </p>
        </div>
        <a :href="urls.archive" download="umeko-server-admin.zip" data-admin-automation-download
          ><UiIcon name="download" :size="16" />{{ tr('下载 Skill.zip') }}</a
        >
      </section>
      <p class="automation-note">
        {{
          tr(
            '提示词和 Skill 不含密码或密钥。下载不代表授权，管理操作仍需管理员身份；调用方应能访问当前管理地址。',
          )
        }}
      </p>
    </div>
    <template #footer
      ><button type="button" @click="open = false">{{ tr('关闭') }}</button></template
    >
  </UiModal>
</template>
<style scoped>
.automation-modal[open] {
  width: min(720px, calc(100vw - 32px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.automation-modal :deep(.modal-header),
.automation-modal :deep(.modal-footer) {
  flex-shrink: 0;
}
.automation-modal :deep(.modal-body) {
  min-height: 0;
  overflow: auto;
}
.admin-automation {
  display: flex;
  align-items: center;
  gap: 5px;
}
.admin-automation > button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
}
.admin-automation:not(.compact) {
  margin-top: 12px;
}
.admin-automation:not(.compact) > button {
  flex: 1;
}
.automation-guide {
  display: grid;
  gap: 22px;
  font-size: 14px;
  line-height: 1.65;
}
.automation-guide h3 {
  margin: 0 0 8px;
  font-size: 19px;
}
.automation-guide p {
  margin: 0;
  color: var(--muted);
}
.automation-steps {
  margin: 0;
  padding-left: 23px;
  display: grid;
  gap: 12px;
}
.automation-steps li::marker {
  color: var(--accent);
  font-weight: 600;
}
.automation-steps strong,
.automation-steps span {
  display: block;
}
.automation-steps span {
  color: var(--muted);
  margin-top: 2px;
}
.automation-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 9px;
}
.automation-section-head label {
  font-weight: 600;
}
.automation-section-head button,
.automation-package a {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
}
.automation-package a {
  padding: 9px 13px;
  border-radius: 7px;
  background: var(--accent);
  color: var(--on-accent);
  text-decoration: none;
  font-weight: 600;
}
.automation-package a:hover {
  background: var(--accent-hover);
}
.automation-prompt textarea {
  width: 100%;
  resize: vertical;
  min-height: 150px;
  max-height: 400px;
  font-size: 13px;
  line-height: 1.7;
}
.automation-package {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--accent-soft);
}
.automation-package > svg {
  flex-shrink: 0;
  color: var(--accent);
}
.automation-package p {
  margin-top: 5px;
  font-size: 13px;
}
.automation-note {
  font-size: 13px;
}
@media (max-width: 760px) {
  .compact > button span {
    display: none;
  }
  .automation-package {
    flex-wrap: wrap;
  }
  .automation-package .grow {
    flex-basis: calc(100% - 40px);
  }
  .automation-package a {
    justify-content: center;
    width: 100%;
  }
}
</style>
