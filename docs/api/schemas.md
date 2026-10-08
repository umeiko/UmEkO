# 数据结构

> 自动生成：字段必填性、默认值、枚举与约束以以下 JSON Schema 为准。

用户和管理服务各有独立模型。`$ref` 指向同一 OpenAPI 文件的 `components/schemas`；管理模型名称的下划线是源码中的名称。

## 用户服务

### ArtifactView

```json
{
  "properties": {
    "download_url": {
      "title": "Download Url",
      "type": "string"
    },
    "id": {
      "title": "Id",
      "type": "string"
    },
    "kind": {
      "title": "Kind",
      "type": "string"
    },
    "name": {
      "title": "Name",
      "type": "string"
    },
    "size": {
      "title": "Size",
      "type": "integer"
    }
  },
  "required": [
    "id",
    "name",
    "kind",
    "size",
    "download_url"
  ],
  "title": "ArtifactView",
  "type": "object"
}
```

### AuthInput

```json
{
  "properties": {
    "password": {
      "maxLength": 256,
      "minLength": 4,
      "title": "Password",
      "type": "string"
    },
    "username": {
      "maxLength": 80,
      "minLength": 3,
      "title": "Username",
      "type": "string"
    }
  },
  "required": [
    "username",
    "password"
  ],
  "title": "AuthInput",
  "type": "object"
}
```

### ClientResourceGenerate

```json
{
  "properties": {
    "description": {
      "minLength": 1,
      "title": "Description",
      "type": "string"
    },
    "name": {
      "minLength": 1,
      "title": "Name",
      "type": "string"
    }
  },
  "required": [
    "name",
    "description"
  ],
  "title": "ClientResourceGenerate",
  "type": "object"
}
```

### ClientResourceUpdate

```json
{
  "properties": {
    "content": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Content"
    },
    "mounted": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Mounted"
    }
  },
  "title": "ClientResourceUpdate",
  "type": "object"
}
```

### ClientResourceView

```json
{
  "properties": {
    "builtin": {
      "title": "Builtin",
      "type": "boolean"
    },
    "content": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Content"
    },
    "kind": {
      "const": "skills",
      "title": "Kind",
      "type": "string"
    },
    "mounted": {
      "title": "Mounted",
      "type": "boolean"
    },
    "name": {
      "title": "Name",
      "type": "string"
    }
  },
  "required": [
    "kind",
    "name",
    "mounted",
    "builtin"
  ],
  "title": "ClientResourceView",
  "type": "object"
}
```

### ContextView

```json
{
  "properties": {
    "before_tokens": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Before Tokens"
    },
    "cleared": {
      "default": false,
      "title": "Cleared",
      "type": "boolean"
    },
    "compressed": {
      "default": false,
      "title": "Compressed",
      "type": "boolean"
    },
    "exact": {
      "default": false,
      "title": "Exact",
      "type": "boolean"
    },
    "limit_tokens": {
      "title": "Limit Tokens",
      "type": "integer"
    },
    "message_count": {
      "title": "Message Count",
      "type": "integer"
    },
    "message_tokens": {
      "title": "Message Tokens",
      "type": "integer"
    },
    "percent": {
      "title": "Percent",
      "type": "number"
    },
    "reason": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason"
    },
    "tool_tokens": {
      "title": "Tool Tokens",
      "type": "integer"
    },
    "used_tokens": {
      "title": "Used Tokens",
      "type": "integer"
    }
  },
  "required": [
    "used_tokens",
    "message_tokens",
    "tool_tokens",
    "limit_tokens",
    "percent",
    "message_count"
  ],
  "title": "ContextView",
  "type": "object"
}
```

### EventView

```json
{
  "properties": {
    "data": {
      "additionalProperties": true,
      "title": "Data",
      "type": "object"
    },
    "id": {
      "title": "Id",
      "type": "integer"
    },
    "run_id": {
      "title": "Run Id",
      "type": "string"
    },
    "session_id": {
      "title": "Session Id",
      "type": "string"
    },
    "timestamp": {
      "title": "Timestamp",
      "type": "string"
    },
    "type": {
      "title": "Type",
      "type": "string"
    }
  },
  "required": [
    "id",
    "run_id",
    "session_id",
    "type",
    "timestamp",
    "data"
  ],
  "title": "EventView",
  "type": "object"
}
```

### FileView

```json
{
  "properties": {
    "filename": {
      "title": "Filename",
      "type": "string"
    },
    "id": {
      "title": "Id",
      "type": "string"
    },
    "size": {
      "title": "Size",
      "type": "integer"
    }
  },
  "required": [
    "id",
    "filename",
    "size"
  ],
  "title": "FileView",
  "type": "object"
}
```

### HTTPValidationError

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "title": "Detail",
      "type": "array"
    }
  },
  "title": "HTTPValidationError",
  "type": "object"
}
```

### MessageView

```json
{
  "properties": {
    "attachments": {
      "items": {
        "type": "string"
      },
      "title": "Attachments",
      "type": "array"
    },
    "content": {
      "title": "Content",
      "type": "string"
    },
    "created_at": {
      "title": "Created At",
      "type": "string"
    },
    "role": {
      "enum": [
        "user",
        "assistant"
      ],
      "title": "Role",
      "type": "string"
    }
  },
  "required": [
    "role",
    "content",
    "created_at"
  ],
  "title": "MessageView",
  "type": "object"
}
```

### ModelPrefsIn

```json
{
  "description": "用户角色级模型偏好；None = 跟随默认（管理员配置的当前模型）。",
  "properties": {
    "main_model_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Main Model Id"
    },
    "sub_model_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Sub Model Id"
    },
    "vision_model_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Vision Model Id"
    }
  },
  "title": "ModelPrefsIn",
  "type": "object"
}
```

### ProxySessionView

```json
{
  "description": "One-shot 代理调用：创建结果（POST /v1/proxy/sessions）。",
  "properties": {
    "files": {
      "items": {
        "type": "string"
      },
      "title": "Files",
      "type": "array"
    },
    "run_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Run Id"
    },
    "session_id": {
      "title": "Session Id",
      "type": "string"
    },
    "skill": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Skill"
    }
  },
  "required": [
    "session_id",
    "run_id"
  ],
  "title": "ProxySessionView",
  "type": "object"
}
```

### ProxyStatusView

```json
{
  "description": "One-shot 代理调用：任务状态（GET /v1/proxy/sessions/{id}）。",
  "properties": {
    "artifacts": {
      "items": {
        "$ref": "#/components/schemas/ArtifactView"
      },
      "title": "Artifacts",
      "type": "array"
    },
    "progress": {
      "default": "",
      "title": "Progress",
      "type": "string"
    },
    "reply": {
      "default": "",
      "title": "Reply",
      "type": "string"
    },
    "result": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Result"
    },
    "run_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Run Id"
    },
    "session_id": {
      "title": "Session Id",
      "type": "string"
    },
    "status": {
      "title": "Status",
      "type": "string"
    }
  },
  "required": [
    "session_id",
    "run_id",
    "status"
  ],
  "title": "ProxyStatusView",
  "type": "object"
}
```

### RunCreate

```json
{
  "properties": {
    "attachments": {
      "items": {
        "type": "string"
      },
      "title": "Attachments",
      "type": "array"
    },
    "input": {
      "minLength": 1,
      "title": "Input",
      "type": "string"
    }
  },
  "required": [
    "input"
  ],
  "title": "RunCreate",
  "type": "object"
}
```

### RunView

```json
{
  "properties": {
    "completed_at": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Completed At"
    },
    "created_at": {
      "title": "Created At",
      "type": "string"
    },
    "error": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Error"
    },
    "id": {
      "title": "Id",
      "type": "string"
    },
    "reply": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reply"
    },
    "session_id": {
      "title": "Session Id",
      "type": "string"
    },
    "status": {
      "enum": [
        "queued",
        "running",
        "cancelling",
        "completed",
        "failed",
        "cancelled"
      ],
      "title": "Status",
      "type": "string"
    }
  },
  "required": [
    "id",
    "session_id",
    "status",
    "created_at"
  ],
  "title": "RunView",
  "type": "object"
}
```

### SessionCreate

```json
{
  "description": "通用基座的 Session 没有领域配置；保留模型以便未来扩展。",
  "properties": {},
  "title": "SessionCreate",
  "type": "object"
}
```

### SessionModelIn

```json
{
  "description": "会话级主模型覆盖；None = 清除覆盖。",
  "properties": {
    "model_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Model Id"
    }
  },
  "title": "SessionModelIn",
  "type": "object"
}
```

### SessionTitlePatch

```json
{
  "properties": {
    "title": {
      "maxLength": 80,
      "minLength": 1,
      "title": "Title",
      "type": "string"
    }
  },
  "required": [
    "title"
  ],
  "title": "SessionTitlePatch",
  "type": "object"
}
```

### SessionView

```json
{
  "properties": {
    "created_at": {
      "title": "Created At",
      "type": "string"
    },
    "id": {
      "title": "Id",
      "type": "string"
    },
    "model_override_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Model Override Id"
    },
    "title": {
      "default": "未命名会话",
      "title": "Title",
      "type": "string"
    }
  },
  "required": [
    "id",
    "created_at"
  ],
  "title": "SessionView",
  "type": "object"
}
```

### TaskCreateInput

```json
{
  "additionalProperties": false,
  "properties": {
    "files": {
      "items": {
        "$ref": "#/components/schemas/TaskFileInput"
      },
      "maxItems": 10,
      "title": "Files",
      "type": "array"
    },
    "model_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Model Id"
    },
    "prompt": {
      "maxLength": 200000,
      "minLength": 1,
      "title": "Prompt",
      "type": "string"
    }
  },
  "required": [
    "prompt"
  ],
  "title": "TaskCreateInput",
  "type": "object"
}
```

### TaskFileInput

```json
{
  "additionalProperties": false,
  "properties": {
    "content_base64": {
      "maxLength": 28000000,
      "title": "Content Base64",
      "type": "string"
    },
    "name": {
      "maxLength": 200,
      "minLength": 1,
      "title": "Name",
      "type": "string"
    }
  },
  "required": [
    "name",
    "content_base64"
  ],
  "title": "TaskFileInput",
  "type": "object"
}
```

### ToolEventView

```json
{
  "properties": {
    "agent": {
      "default": "main",
      "title": "Agent",
      "type": "string"
    },
    "arguments": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Arguments"
    },
    "created_at": {
      "title": "Created At",
      "type": "string"
    },
    "name": {
      "title": "Name",
      "type": "string"
    },
    "result": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Result"
    },
    "run_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Run Id"
    }
  },
  "required": [
    "name",
    "created_at"
  ],
  "title": "ToolEventView",
  "type": "object"
}
```

### UserView

```json
{
  "properties": {
    "avatar_url": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Avatar Url"
    },
    "id": {
      "title": "Id",
      "type": "string"
    },
    "username": {
      "title": "Username",
      "type": "string"
    }
  },
  "required": [
    "id",
    "username"
  ],
  "title": "UserView",
  "type": "object"
}
```

### ValidationError

```json
{
  "properties": {
    "ctx": {
      "title": "Context",
      "type": "object"
    },
    "input": {
      "title": "Input"
    },
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "title": "Location",
      "type": "array"
    },
    "msg": {
      "title": "Message",
      "type": "string"
    },
    "type": {
      "title": "Error Type",
      "type": "string"
    }
  },
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError",
  "type": "object"
}
```

### WorkspaceAttachmentCreate

```json
{
  "properties": {
    "path": {
      "minLength": 1,
      "title": "Path",
      "type": "string"
    }
  },
  "required": [
    "path"
  ],
  "title": "WorkspaceAttachmentCreate",
  "type": "object"
}
```

### WorkspaceEntryCreate

```json
{
  "properties": {
    "path": {
      "maxLength": 500,
      "minLength": 1,
      "title": "Path",
      "type": "string"
    },
    "type": {
      "enum": [
        "file",
        "directory"
      ],
      "title": "Type",
      "type": "string"
    }
  },
  "required": [
    "path",
    "type"
  ],
  "title": "WorkspaceEntryCreate",
  "type": "object"
}
```

### WorkspaceExtract

```json
{
  "properties": {
    "path": {
      "maxLength": 500,
      "minLength": 1,
      "title": "Path",
      "type": "string"
    }
  },
  "required": [
    "path"
  ],
  "title": "WorkspaceExtract",
  "type": "object"
}
```

### WorkspaceFileView

```json
{
  "properties": {
    "filename": {
      "title": "Filename",
      "type": "string"
    },
    "path": {
      "title": "Path",
      "type": "string"
    },
    "size": {
      "title": "Size",
      "type": "integer"
    }
  },
  "required": [
    "path",
    "filename",
    "size"
  ],
  "title": "WorkspaceFileView",
  "type": "object"
}
```

### WorkspaceNode

```json
{
  "properties": {
    "children": {
      "items": {
        "$ref": "#/components/schemas/WorkspaceNode"
      },
      "title": "Children",
      "type": "array"
    },
    "name": {
      "title": "Name",
      "type": "string"
    },
    "path": {
      "title": "Path",
      "type": "string"
    },
    "size": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Size"
    },
    "truncated": {
      "default": false,
      "title": "Truncated",
      "type": "boolean"
    },
    "type": {
      "enum": [
        "directory",
        "file"
      ],
      "title": "Type",
      "type": "string"
    },
    "virtual": {
      "default": false,
      "title": "Virtual",
      "type": "boolean"
    }
  },
  "required": [
    "name",
    "path",
    "type"
  ],
  "title": "WorkspaceNode",
  "type": "object"
}
```

### WorkspaceTransfer

```json
{
  "properties": {
    "operation": {
      "enum": [
        "copy",
        "move"
      ],
      "title": "Operation",
      "type": "string"
    },
    "source": {
      "maxLength": 500,
      "minLength": 1,
      "title": "Source",
      "type": "string"
    },
    "target": {
      "maxLength": 500,
      "minLength": 1,
      "title": "Target",
      "type": "string"
    }
  },
  "required": [
    "source",
    "target",
    "operation"
  ],
  "title": "WorkspaceTransfer",
  "type": "object"
}
```

## 管理服务

### HTTPValidationError

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "title": "Detail",
      "type": "array"
    }
  },
  "title": "HTTPValidationError",
  "type": "object"
}
```

### ValidationError

```json
{
  "properties": {
    "ctx": {
      "title": "Context",
      "type": "object"
    },
    "input": {
      "title": "Input"
    },
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "title": "Location",
      "type": "array"
    },
    "msg": {
      "title": "Message",
      "type": "string"
    },
    "type": {
      "title": "Error Type",
      "type": "string"
    }
  },
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError",
  "type": "object"
}
```

### _ActiveModelIn

```json
{
  "properties": {
    "model_id": {
      "title": "Model Id",
      "type": "string"
    }
  },
  "required": [
    "model_id"
  ],
  "title": "_ActiveModelIn",
  "type": "object"
}
```

### _AgentIn

```json
{
  "additionalProperties": false,
  "properties": {
    "default_model_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Model Id"
    },
    "default_vision_model_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Vision Model Id"
    },
    "description": {
      "maxLength": 10000,
      "minLength": 1,
      "title": "Description",
      "type": "string"
    },
    "documentationUrl": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Documentationurl"
    },
    "enabled": {
      "default": true,
      "title": "Enabled",
      "type": "boolean"
    },
    "iconUrl": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Iconurl"
    },
    "name": {
      "maxLength": 200,
      "minLength": 1,
      "title": "Name",
      "type": "string"
    },
    "provider": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Provider"
    },
    "skill_names": {
      "items": {
        "type": "string"
      },
      "title": "Skill Names",
      "type": "array"
    },
    "slug": {
      "maxLength": 63,
      "minLength": 1,
      "title": "Slug",
      "type": "string"
    },
    "system_prompt": {
      "default": "",
      "maxLength": 100000,
      "title": "System Prompt",
      "type": "string"
    },
    "version": {
      "default": "0.1.2",
      "title": "Version",
      "type": "string"
    }
  },
  "required": [
    "slug",
    "name",
    "description"
  ],
  "title": "_AgentIn",
  "type": "object"
}
```

### _DefaultSkillIn

```json
{
  "properties": {
    "content": {
      "maxLength": 200000,
      "minLength": 1,
      "title": "Content",
      "type": "string"
    }
  },
  "required": [
    "content"
  ],
  "title": "_DefaultSkillIn",
  "type": "object"
}
```

### _ImportIn

```json
{
  "properties": {
    "document": {
      "additionalProperties": true,
      "title": "Document",
      "type": "object"
    }
  },
  "required": [
    "document"
  ],
  "title": "_ImportIn",
  "type": "object"
}
```

### _Login

```json
{
  "properties": {
    "password": {
      "title": "Password",
      "type": "string"
    },
    "username": {
      "title": "Username",
      "type": "string"
    }
  },
  "required": [
    "username",
    "password"
  ],
  "title": "_Login",
  "type": "object"
}
```

### _ModelIn

```json
{
  "properties": {
    "max_concurrent_requests": {
      "default": 0,
      "minimum": 0.0,
      "title": "Max Concurrent Requests",
      "type": "integer"
    },
    "name": {
      "title": "Name",
      "type": "string"
    },
    "vision": {
      "default": false,
      "title": "Vision",
      "type": "boolean"
    }
  },
  "required": [
    "name"
  ],
  "title": "_ModelIn",
  "type": "object"
}
```

### _ModelPatch

```json
{
  "properties": {
    "max_concurrent_requests": {
      "anyOf": [
        {
          "minimum": 0.0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Max Concurrent Requests"
    },
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "vision": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Vision"
    }
  },
  "title": "_ModelPatch",
  "type": "object"
}
```

### _PasswordSet

```json
{
  "properties": {
    "password": {
      "title": "Password",
      "type": "string"
    }
  },
  "required": [
    "password"
  ],
  "title": "_PasswordSet",
  "type": "object"
}
```

### _ProviderIn

```json
{
  "properties": {
    "api_key": {
      "title": "Api Key",
      "type": "string"
    },
    "base_url": {
      "title": "Base Url",
      "type": "string"
    },
    "name": {
      "title": "Name",
      "type": "string"
    },
    "proxy": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Proxy"
    }
  },
  "required": [
    "name",
    "base_url",
    "api_key"
  ],
  "title": "_ProviderIn",
  "type": "object"
}
```

### _ProviderPatch

```json
{
  "properties": {
    "api_key": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Api Key"
    },
    "base_url": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Base Url"
    },
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "proxy": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Proxy"
    }
  },
  "title": "_ProviderPatch",
  "type": "object"
}
```

### _RoleSet

```json
{
  "properties": {
    "role": {
      "title": "Role",
      "type": "string"
    }
  },
  "required": [
    "role"
  ],
  "title": "_RoleSet",
  "type": "object"
}
```

### _RuntimeConfigIn

```json
{
  "properties": {
    "max_tool_iterations": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Max Tool Iterations"
    }
  },
  "title": "_RuntimeConfigIn",
  "type": "object"
}
```

### _ScriptTestIn

```json
{
  "properties": {
    "args": {
      "default": "{}",
      "title": "Args",
      "type": "string"
    },
    "timeout": {
      "default": 10,
      "title": "Timeout",
      "type": "integer"
    }
  },
  "title": "_ScriptTestIn",
  "type": "object"
}
```

### _ServiceAccessIn

```json
{
  "properties": {
    "auth_mode": {
      "enum": [
        "required",
        "anonymous"
      ],
      "title": "Auth Mode",
      "type": "string"
    }
  },
  "required": [
    "auth_mode"
  ],
  "title": "_ServiceAccessIn",
  "type": "object"
}
```

### _ServiceAccountIn

```json
{
  "properties": {
    "expires_days": {
      "default": 90,
      "maximum": 3650.0,
      "minimum": 1.0,
      "title": "Expires Days",
      "type": "integer"
    },
    "name": {
      "maxLength": 80,
      "minLength": 1,
      "title": "Name",
      "type": "string"
    },
    "scopes": {
      "items": {
        "type": "string"
      },
      "title": "Scopes",
      "type": "array"
    }
  },
  "required": [
    "name"
  ],
  "title": "_ServiceAccountIn",
  "type": "object"
}
```

### _ServiceAccountPatch

```json
{
  "properties": {
    "enabled": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Enabled"
    },
    "expires_days": {
      "default": 90,
      "maximum": 3650.0,
      "minimum": 1.0,
      "title": "Expires Days",
      "type": "integer"
    },
    "rotate": {
      "default": false,
      "title": "Rotate",
      "type": "boolean"
    }
  },
  "title": "_ServiceAccountPatch",
  "type": "object"
}
```

### _UserCreate

```json
{
  "properties": {
    "password": {
      "title": "Password",
      "type": "string"
    },
    "role": {
      "default": "user",
      "title": "Role",
      "type": "string"
    },
    "username": {
      "title": "Username",
      "type": "string"
    }
  },
  "required": [
    "username",
    "password"
  ],
  "title": "_UserCreate",
  "type": "object"
}
```
