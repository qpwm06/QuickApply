# 抓取与投递流程

[English](./workflows.md)

> 导航：[← 配置说明](./configuration.zh-CN.md) · [文档首页](./README.zh-CN.md) · [下一篇：Tailor 精修说明 →](./tailor.zh-CN.md)

> 🧭 QuickApply 最适合被当成一条运营链路来用：先看总览，再调市场画像，再筛职位池，接着管投递状态，最后只对真正重要的岗位进入 Tailor。

## 🖼️ 工作流总览

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="#1-dashboard">
        <img src="./screenshots/dashboard-en.png" alt="Dashboard" width="100%" />
      </a>
      <br />
      <strong>1. Dashboard</strong>
      <br />
      <sub>先用一眼总览判断哪里最值得处理。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="#2-crawler">
        <img src="./screenshots/crawler-en.png" alt="Crawler" width="100%" />
      </a>
      <br />
      <strong>2. Crawler</strong>
      <br />
      <sub>在这里调画像、关键词、来源站点和抓取表现。</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="#3-jobs">
        <img src="./screenshots/jobs-en.png" alt="Jobs" width="100%" />
      </a>
      <br />
      <strong>3. Jobs</strong>
      <br />
      <sub>把职位池压缩成真正值得行动的短名单。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="#4-tracker">
        <img src="./screenshots/tracker-en.png" alt="Tracker" width="100%" />
      </a>
      <br />
      <strong>4. Tracker</strong>
      <br />
      <sub>把已投递岗位变成一条可维护的运营流水线。</sub>
    </td>
  </tr>
</table>

## 1. Dashboard

![Dashboard](./screenshots/dashboard-en.png)

`Dashboard` 适合拿来回答一个最快的问题：
**现在最该看哪里？**

这个页面主要回答：

- 有没有应该立刻打开的高分职位
- 最近抓取有没有产出
- 投递追踪有没有推进
- 精修任务是不是还在运行

看完之后通常怎么走：

- 如果市场太旧或太薄，就去 `Crawler`
- 如果已经有不错的岗位，就去 `Jobs`
- 如果想看已经投过的岗位，就去 `Tracker`

## 2. Crawler

![Crawler](./screenshots/crawler-en.png)

`Crawler` 是市场调参页面。

这里主要做：

- 管搜索画像
- 管关键词
- 绑定默认简历
- 设地点和站点来源
- 看每次抓取的历史结果

需要重点看什么：

- 画像看起来合理，不代表抓取产出一定好
- LinkedIn 和 Indeed 可能因为频繁抓取而限流
- 判断某个画像有没有价值，最可靠的是 crawl history

常见下一步：

- 空跑太多时，调整或删掉弱关键词
- 噪音过多时，缩小地点范围
- 把高产画像继续强化，低产画像停止投喂

## 3. Jobs

![Jobs](./screenshots/jobs-en.png)

`Jobs` 用来把大池子切成真正能行动的名单。

这里能做的事：

- 按画像、地点、包含关键词、屏蔽关键词、分数、时间和国家筛选
- 在一个可复用的独立 Chrome 窗口里打开原始岗位页
- 一次性排除垃圾公司，后面持续隐藏
- dismiss 不合适职位
- 标记已投递，把它移出 remaining 池
- 只对真正重要的岗位进入 Tailor

上面的计数怎么理解：

- `Remaining`：还在主动评估中的岗位
- `Applied`：已经进入投递流水线
- `Reviewed`：已投递和已 dismiss 的总和

实用规则：

- 岗位弱，就 dismiss 或直接排除公司
- 岗位强但还没准备好，就继续留在 remaining
- 真正投了，就标记 applied 并转到 `Tracker`
- 连续查看多个岗位时，QuickApply 会持续刷新同一个独立 Chrome 窗口，避免主浏览器越看 tab 越多

## 4. Tracker

![Tracker](./screenshots/tracker-en.png)

`Tracker` 适合在岗位已经“成案子”之后使用。

这个页面负责：

- 接住从 `Jobs` 里标记 applied 的岗位
- 记录手工新增的内推或站外投递
- 管 submitted、introduced、interviewed、failed 这类阶段变化
- 记录备注，说明发生了什么、下一步是什么

它的价值在于：

- 防止已经投过的岗位重新回流到主职位池
- 把阶段历史固定到同一条岗位记录上
- 为后续的 Tailor 或跟进动作提供一个干净入口

## Tailor 在哪里接上

一般这条链路会这样结束：

1. 在 `Crawler` 里发现机会
2. 在 `Jobs` 里压缩清单
3. 在 `Tracker` 里管理真实投递进度
4. 只对真正重要的岗位进入 `Tailor` 做定制化简历

Tailor 的部分继续看 [tailor.zh-CN.md](./tailor.zh-CN.md)。

---

> 继续阅读：[← 配置说明](./configuration.zh-CN.md) · [文档首页](./README.zh-CN.md) · [下一篇：Tailor 精修说明 →](./tailor.zh-CN.md)
