# 项目文档

- [启动与生产部署指南](deployment.md)：源码 / Windows exe 启动、Provider 与 `.env` 的分工、配置迁移、NGINX / ALB 前缀、模型 CA、流式验证、备份升级和常见故障。
- [本地代理验证实验](../scripts/proxy_lab/README.md)：Windows / WSL / 红帽 Docker 验证方式、假模型与独立 CA、修复前后的证据范围。
- [架构说明](../ARCHITECTURE.md)：内核、运行时、宿主服务和 Web / CLI 交付层的职责。

首次使用从“启动与生产部署指南”开始；生产配置以该文档为准，代理实验用于隔离验证。
