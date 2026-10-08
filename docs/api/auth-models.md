# 登录与模型

## 用户认证

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/v1/auth/register` | 注册并登录，`201` |
| POST | `/v1/auth/login` | 登录，`200` |
| GET | `/v1/auth/me` | 当前用户 |
| POST | `/v1/auth/logout` | 撤销当前 Token、删除 Cookie，`204` |
| GET / PUT / DELETE | `/v1/auth/avatar` | 获取 / 更新 / 删除头像 |

注册与登录 JSON：

```json
{"username": "your-user", "password": "your-password"}
```

用户名长度为 3–80，密码长度为 4–256。返回 `UserView`：`id`、`username`、可空 `avatar_url`。登录通过 `Set-Cookie` 设置 `umeko_auth`，Cookie 为 HttpOnly、SameSite=Lax，客户端需保存并复用。Cookie Path 是配置的服务前缀或 `/`。

Cookie 的 Max-Age 为 14 天；服务还在数据库校验 Token 有效期，不能仅据 Cookie 判断登录有效。当前实现 `Secure=False`，公共 HTTPS 与访问策略由部署层配合。没有通用跨域 CORS 配置；跨站浏览器调用需单独设计，不能假定与同站页面一样可用。

头像 PUT 使用原始字节体，支持 PNG、JPEG、WebP、GIF，最大 2 MiB。获取时直接返回图片，缺少头像返回 `404`。

## 模型列表与偏好

`GET /v1/models` 返回：

```json
{
  "providers": [{"id": "provider_example", "name": "Company", "models": [
    {"id": "model_example", "name": "document-model", "vision": true}
  ]}],
  "active_model_id": "model_example",
  "prefs": {"main_model_id": null, "sub_model_id": null, "vision_model_id": null}
}
```

这是形状示例，不是真实模型配置。用户列表不返回 Provider URL、Key 或模型并发额度。

`PUT /v1/auth/model-prefs` 设置角色级选择：

```json
{"main_model_id": "model_example", "sub_model_id": null, "vision_model_id": null}
```

`null` 表示跟随默认。这个接口保存整组偏好，省略字段也会按 `null` 处理；只改变一个角色时，要同时携带其他希望保留的角色选择。

`PUT /v1/sessions/{session_id}/model` 设置会话主模型覆盖，返回 `204`：

```json
{"model_id": "model_example"}
```

传 `null` 清除覆盖。主模型优先级为会话覆盖、用户偏好、全局激活模型。子模型未指定时跟随主模型；视觉模型根据用户选择和可用视觉能力解析。选择在下一轮 Run 时应用。

模型注册与额度由[管理 API](admin.md)配置。完整参数见[用户参考](reference-user.md)。
