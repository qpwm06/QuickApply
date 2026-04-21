# 抓取与投递流程

[English](./workflows.md)

## Dashboard

`Dashboard` 负责做最上层总览。

它汇总了：

- 最近高分职位
- 最近抓取记录
- 最近投递追踪
- 最近精修情况

![Dashboard](./screenshots/dashboard-en.png)

## Crawler

`Crawler` 是搜索画像和抓取控制中心。

主要操作：

- 新增画像
- 修改关键词
- 修改地点
- 选择抓取站点
- 查看抓取历史

需要注意：

- JobSpy 抓不到，不代表你自己的 Chrome 也一定打不开
- LinkedIn 和 Indeed 可能出现限流
- 判断某个关键词有没有价值，主要看 crawl history

![Crawler](./screenshots/crawler-en.png)

## Jobs

`Jobs` 是完整职位池。

主要操作：

- 按画像、关键词、地点、分数、时间、国家做筛选
- 打开原始职位页
- 排除噪音公司
- dismiss 岗位
- 标记投递
- 进入 Tailor

行为上要知道：

- 标记 applied 后，岗位不会继续留在 remaining 池
- dismiss 会计入 reviewed
- 被排除的公司后续会继续被隐藏

![Jobs](./screenshots/jobs-en.png)

## Tracker

`Tracker` 用来管理投递时间线。

两个来源：

- `Mark Applied` 自动同步过来的 track
- 手动补录的岗位

每条 track 可以记录：

- 当前阶段
- 阶段时间
- 备注
- 完整事件流

![Tracker](./screenshots/tracker-en.png)
