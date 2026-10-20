# 管理 API 数据结构

> 自动生成；由运行版本的 OpenAPI 导出。


## HTTPValidationError

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

## ValidationError

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

## _ActiveModelIn

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

## _AgentIn

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
    "disclosed_model_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Disclosed Model Ids"
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

## _DefaultSkillIn

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

## _ImportIn

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

## _Login

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

## _ModelIn

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
    "user_enabled": {
      "default": true,
      "title": "User Enabled",
      "type": "boolean"
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

## _ModelPatch

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
    "user_enabled": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "User Enabled"
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

## _PasswordSet

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

## _ProviderIn

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

## _ProviderPatch

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

## _RoleSet

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

## _RuntimeConfigIn

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

## _ScriptTestIn

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

## _ServiceAccessIn

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

## _ServiceAccountIn

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

## _ServiceAccountPatch

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

## _SkillApprovalIn

```json
{
  "additionalProperties": false,
  "properties": {
    "sha256": {
      "pattern": "^[0-9a-f]{64}$",
      "title": "Sha256",
      "type": "string"
    }
  },
  "required": [
    "sha256"
  ],
  "title": "_SkillApprovalIn",
  "type": "object"
}
```

## _SkillTrustBatchIn

```json
{
  "additionalProperties": false,
  "properties": {
    "action": {
      "enum": [
        "approve",
        "revoke"
      ],
      "title": "Action",
      "type": "string"
    },
    "items": {
      "items": {
        "$ref": "#/components/schemas/_SkillTrustItem"
      },
      "maxItems": 200,
      "minItems": 1,
      "title": "Items",
      "type": "array"
    }
  },
  "required": [
    "action",
    "items"
  ],
  "title": "_SkillTrustBatchIn",
  "type": "object"
}
```

## _SkillTrustItem

```json
{
  "additionalProperties": false,
  "properties": {
    "member": {
      "maxLength": 500,
      "minLength": 1,
      "title": "Member",
      "type": "string"
    },
    "pack": {
      "maxLength": 120,
      "minLength": 1,
      "title": "Pack",
      "type": "string"
    },
    "sha256": {
      "pattern": "^[0-9a-f]{64}$",
      "title": "Sha256",
      "type": "string"
    }
  },
  "required": [
    "sha256",
    "pack",
    "member"
  ],
  "title": "_SkillTrustItem",
  "type": "object"
}
```

## _ToolDispatchIn

```json
{
  "additionalProperties": false,
  "properties": {
    "enabled": {
      "title": "Enabled",
      "type": "boolean"
    }
  },
  "required": [
    "enabled"
  ],
  "title": "_ToolDispatchIn",
  "type": "object"
}
```

## _UserCreate

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

## _UserModelAccessIn

```json
{
  "additionalProperties": false,
  "properties": {
    "allowed_model_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Allowed Model Ids"
    },
    "allowed_provider_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Allowed Provider Ids"
    }
  },
  "required": [
    "allowed_provider_ids",
    "allowed_model_ids"
  ],
  "title": "_UserModelAccessIn",
  "type": "object"
}
```

## _UserToolAccessIn

```json
{
  "additionalProperties": false,
  "properties": {
    "allowed_tool_names": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Allowed Tool Names"
    }
  },
  "required": [
    "allowed_tool_names"
  ],
  "title": "_UserToolAccessIn",
  "type": "object"
}
```
