# 文档首页

[English](./README.md)

> 导航：[← 仓库首页 README](../README.zh-CN.md) · [下一篇：快速开始 →](./getting-started.zh-CN.md)

> 🧭 这套文档建议按“产品说明书”的方式来看：先启动，再理解工作流，最后再进 Tailor 和部署细节。

## 🚀 建议阅读顺序

1. [快速开始](./getting-started.zh-CN.md)
2. [配置说明](./configuration.zh-CN.md)
3. [抓取与投递流程](./workflows.zh-CN.md)
4. [Tailor 精修说明](./tailor.zh-CN.md)
5. [部署与运维](./deployment.zh-CN.md)

## 🖼️ 工作流总览

公开截图按真实使用链路组织，而不是把单个页面孤零零堆在一起。

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="./workflows.zh-CN.md#1-dashboard">
        <img src="./screenshots/dashboard-en.png" alt="Dashboard" width="100%" />
      </a>
      <br />
      <strong>Dashboard</strong>
      <br />
      <sub>先看高分职位、最近抓取、投递动态和精修状态。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="./workflows.zh-CN.md#2-crawler">
        <img src="./screenshots/crawler-en.png" alt="Crawler" width="100%" />
      </a>
      <br />
      <strong>Crawler</strong>
      <br />
      <sub>这里维护画像、关键词、地点、站点来源和抓取历史。</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="./workflows.zh-CN.md#3-jobs">
        <img src="./screenshots/jobs-en.png" alt="Jobs" width="100%" />
      </a>
      <br />
      <strong>Jobs</strong>
      <br />
      <sub>从完整职位池里做筛选、排噪、打开岗位页并进入 Tailor。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="./workflows.zh-CN.md#4-tracker">
        <img src="./screenshots/tracker-en.png" alt="Tracker" width="100%" />
      </a>
      <br />
      <strong>Tracker</strong>
      <br />
      <sub>把已投递岗位、手工录入、阶段和备注都收进一条时间线。</sub>
    </td>
  </tr>
</table>

## 📚 每一页分别讲什么

### `getting-started.zh-CN.md`

- 本地启动
- Docker 启动
- demo 数据 seed
- 第一次使用路径

### `configuration.zh-CN.md`

- 简历文件
- 搜索画像
- 环境变量
- 代理文件

### `workflows.zh-CN.md`

- 每个核心页面解决什么问题
- 在该页面要看什么信号
- 下一步应该跳到哪里
- 配套截图导览

### `tailor.zh-CN.md`

- 工作区文件
- 修改建议
- Codex session 流程
- PDF 输出

### `deployment.zh-CN.md`

- 本地辅助脚本
- Docker 注意事项
- 测试命令
- 运维边界

---

> 继续阅读：[← 仓库首页 README](../README.zh-CN.md) · [下一篇：快速开始 →](./getting-started.zh-CN.md)
