# 项目文档入口

- [启动与生产部署指南](deployment.md)：源码 / Windows exe 启动、Provider 与 `.env` 的分工、配置迁移、NGINX / ALB 前缀、模型 CA、流式验证、备份升级和常见故障。
- [在线文档站](https://umeiko.github.io/UmEkO/)：[首页](index.md)、[快速上手](quickstart.md)。
- [架构设计](architecture/index.md)：CLI、Web Server、API 服务与 MCP / A2A 接入。
- [机器任务](api/machine-tasks.md)、[MCP](api/mcp.md)、[A2A](api/a2a.md)、[资源监控](api/monitoring.md)。
- [API 文档](api/index.md)：现有接口能力、调用示例、流式事件与完整参考。
- [前端开发](frontend.md)：Vue 双入口、深色工作台、构建发布与浏览器验收。
- [本地代理验证实验](https://github.com/umeiko/UmEkO/blob/main/scripts/proxy_lab/README.md)：Windows / WSL / 红帽 Docker 验证方式、假模型与独立 CA、修复前后的证据范围。

首次使用从“启动与生产部署指南”开始；生产配置以该文档为准，代理实验用于隔离验证。
