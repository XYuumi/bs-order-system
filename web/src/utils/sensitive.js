/** 敏感操作密码二次确认弹窗：resolve 出用户输入的密码（取消为 null），由调用方放入 X-Confirm-Password 请求头。 */


export async function sensitiveConfirm({ title = '敏感操作确认', content = '该操作需要输入登录密码确认' } = {}) {
  try {
    const { value } = await ElMessageBox.prompt(content, title, {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputType: 'password',
      inputPlaceholder: '请输入登录密码',
      inputValidator: (v) => (v && v.trim() ? true : '请输入密码'),
      closeOnClickModal: false,
      autofocus: true,
    })
    return value.trim()
  } catch {
    return null
  }
}

/** 带 X-Confirm-Password 的请求配置 */
export function withConfirm(password, config = {}) {
  return { ...config, headers: { 'X-Confirm-Password': password, ...(config.headers || {}) } }
}
