(() => {
  const STORAGE_KEY = "quickapply:ui-language";
  const DEFAULT_LANGUAGE = "zh";
  const SUPPORTED_LANGUAGES = new Set(["zh", "en"]);
  const SKIP_SELECTOR = [
    "textarea",
    "pre",
    "code",
    "script",
    "style",
    "iframe",
    ".markdown-preview",
    ".markdown-source",
    ".workspace-edit-grid",
    ".session-log-list",
  ].join(", ");

  const TEXT_PAIRS = [
    { zh: "总览", en: "Overview" },
    { zh: "运营", en: "Operations" },
    { zh: "内容管理", en: "Content" },
    { zh: "仪表盘", en: "Dashboard" },
    { zh: "爬虫", en: "Crawler" },
    { zh: "职位", en: "Jobs" },
    { zh: "追踪", en: "Tracker" },
    { zh: "精修", en: "Tailor" },
    { zh: "整体看职位、抓取和精修任务的运行情况，不在这里放重操作。", en: "Watch jobs, crawls, and tailoring health here without placing heavy actions on the dashboard." },
    { zh: "爬虫中心", en: "Crawler Center" },
    { zh: "管理抓取状态、搜索画像、关键词和最近刷新记录。", en: "Manage crawl state, search profiles, keywords, and recent refresh history." },
    { zh: "投递追踪", en: "Application Tracker" },
    { zh: "把已投递岗位和手工补录记录集中放在一个运营页面里。", en: "Keep applied jobs and manual entries together in one operations page." },
    { zh: "精修会话", en: "Tailor Sessions" },
    { zh: "按职位工作区管理建议、session 和最新 PDF，避免同一 job 的重复 run 挤满列表。", en: "Manage advice, sessions, and the latest PDFs by job workspace without crowding the list with duplicate runs." },
    { zh: "Career Ops", en: "Career Ops" },
    { zh: "爬虫控制", en: "Crawler Control" },
    { zh: "投递流水线", en: "Pipeline" },
    { zh: "投递追踪", en: "Application Tracker" },
    { zh: "精修会话", en: "Tailor Sessions" },
    { zh: "精修会话", en: "Tailor Session" },
    { zh: "职位预览", en: "Job Preview" },
    { zh: "精修 Skill", en: "Tailor Skill" },
    { zh: "整体统计", en: "Overview Stats" },
    { zh: "最近高分职位", en: "Recent High Matches" },
    { zh: "最近抓取", en: "Recent Crawls" },
    { zh: "最近精修", en: "Recent Tailor Work" },
    { zh: "整体信息", en: "Overview" },
    { zh: "抓取、职位、精修任务的统一总览", en: "One surface for crawl, jobs, and tailoring status." },
    { zh: "进入爬虫中心", en: "Open Crawler Center" },
    { zh: "查看 Jobs", en: "Open Jobs" },
    { zh: "职位总数", en: "Total Jobs" },
    { zh: "高分职位", en: "High Matches" },
    { zh: "近 7 天更新", en: "Updated in 7 Days" },
    { zh: "精修任务", en: "Tailor Tasks" },
    { zh: "从总览直接看到值得先投的岗位", en: "See the best jobs to prioritize from the dashboard." },
    { zh: "全部 Jobs", en: "All Jobs" },
    { zh: "看抓取成效和是否被站点限制", en: "Check crawl yield and whether sites are rate-limiting." },
    { zh: "去爬虫中心", en: "Go to Crawler Center" },
    { zh: "进行中", en: "Running" },
    { zh: "运行中", en: "Running" },
    { zh: "还没有抓取记录。", en: "No crawl history yet." },
    { zh: "按职位工作区查看最近精修", en: "Review recent tailoring work by job workspace." },
    { zh: "任务中心", en: "Task Center" },
    { zh: "未知职位", en: "Unknown Job" },
    { zh: "无职位信息", en: "No job info" },
    { zh: "还没有精修任务。", en: "No tailoring tasks yet." },
    { zh: "最近标记投递的岗位和投递时间", en: "Recently marked applications and their timestamps." },
    { zh: "进入 Tracker", en: "Open Tracker" },
    { zh: "总追踪", en: "Total Tracking" },
    { zh: "关联职位", en: "Linked Jobs" },
    { zh: "手工录入", en: "Manual Entries" },
    { zh: "还没有投递追踪记录。", en: "No application tracking records yet." },
    { zh: "查看", en: "View" },
    { zh: "职位页", en: "Job Page" },
    { zh: "投递时间", en: "Applied At" },
    { zh: "运行状态", en: "Status" },
    { zh: "这里集中管理抓取控制、自动刷新和当前来源", en: "Manage crawl control, auto refresh, and active sources here." },
    { zh: "全部画像", en: "All Profiles" },
    { zh: "抓取中", en: "Running" },
    { zh: "立即抓取", en: "Run Now" },
    { zh: "当前状态", en: "Current Status" },
    { zh: "自动刷新", en: "Auto Refresh" },
    { zh: "待机", en: "Idle" },
    { zh: "未启动", en: "Not Scheduled" },
    { zh: "当前没有后台抓取任务。", en: "No crawl task is running in the background." },
    { zh: "未记录工作区", en: "Workspace missing" },
    { zh: "搜索画像", en: "Search Profiles" },
    { zh: "在这里维护关键词、站点、默认简历和当前画像命中情况", en: "Manage keywords, sites, default resume files, and profile hit quality here." },
    { zh: "新增画像", en: "Add Profile" },
    { zh: "先加一个画像，再继续补关键词和刷新", en: "Create a profile first, then add keywords and refresh." },
    { zh: "名称", en: "Name" },
    { zh: "Slug", en: "Slug" },
    { zh: "初始关键词", en: "Initial Keywords" },
    { zh: "地点", en: "Location" },
    { zh: "默认简历", en: "Default Resume" },
    { zh: "抓取站点", en: "Source Sites" },
    { zh: "刷新该画像", en: "Refresh Profile" },
    { zh: "删除画像", en: "Delete Profile" },
    { zh: "当前还没有关键词。", en: "No keywords yet." },
    { zh: "添加关键词", en: "Add Keyword" },
    { zh: "保存地点", en: "Save Locations" },
    { zh: "市场层级", en: "Market Tier" },
    { zh: "搜索地点", en: "Search Locations" },
    { zh: "未设置", en: "Unset" },
    { zh: "抓取记录", en: "Crawl History" },
    { zh: "快速看每次抓取的产出和异常", en: "Quickly review output and errors for each crawl run." },
    { zh: "画像", en: "Profile" },
    { zh: "开始时间", en: "Started" },
    { zh: "结束时间", en: "Finished" },
    { zh: "抓到", en: "Seen" },
    { zh: "保存", en: "Saved" },
    { zh: "状态", en: "Status" },
    { zh: "详情", en: "Details" },
    { zh: "成功", en: "Success" },
    { zh: "失败", en: "Failed" },
    { zh: "查看详情", en: "View Details" },
    { zh: "← 返回 Crawler", en: "← Back to Crawler" },
    { zh: "Run Summary", en: "Run Summary" },
    { zh: "写入职位", en: "Saved Jobs" },
    { zh: "异常数量", en: "Warnings" },
    { zh: "Query 数量", en: "Queries" },
    { zh: "这次抓取请求的站点：", en: "Sites requested in this run:" },
    { zh: "未记录", en: "Not recorded" },
    { zh: "Query Results", en: "Query Results" },
    { zh: "按关键词和地点拆开的抓取结果", en: "Results split by keyword and location." },
    { zh: "关键词", en: "Keyword" },
    { zh: "站点", en: "Site" },
    { zh: "结果", en: "Rows" },
    { zh: "请求", en: "Requested" },
    { zh: "空结果", en: "Empty" },
    { zh: "当前没有结构化 query 结果，通常说明这是旧记录。", en: "No structured query results were stored; this is usually an older run." },
    { zh: "Warnings", en: "Warnings" },
    { zh: "异常和抓取告警", en: "Errors and crawl warnings." },
    { zh: "需要关注", en: "Needs attention" },
    { zh: "回到列表", en: "Back to List" },
    { zh: "这次抓取没有记录到 warning。", en: "No warnings were recorded for this crawl." },
    { zh: "筛选工具栏", en: "Filter Bar" },
    { zh: "完整职位池在这里筛选，再进入单个岗位精修", en: "Filter the full job pool here, then jump into a single job workspace." },
    { zh: "查看 Tailor Sessions", en: "View Tailor Sessions" },
    { zh: "地点关键词", en: "Location Keywords" },
    { zh: "关键词筛选", en: "Include Keywords" },
    { zh: "关键词屏蔽", en: "Exclude Keywords" },
    { zh: "最低分", en: "Min Score" },
    { zh: "排序", en: "Sort" },
    { zh: "时间窗口", en: "Time Window" },
    { zh: "条数", en: "Limit" },
    { zh: "国家", en: "Countries" },
    { zh: "应用筛选", en: "Apply Filters" },
    { zh: "排除公司", en: "Exclude Company" },
    { zh: "加入排除", en: "Add" },
    { zh: "当前排除列表", en: "Excluded Companies" },
    { zh: "当前没有排除公司。", en: "No companies are excluded yet." },
    { zh: "移除排除公司", en: "Remove Excluded Company" },
    { zh: "职位表格", en: "Jobs Table" },
    { zh: "每个职位一行，优先从这里进入精修", en: "One job per row. Start tailoring from here first." },
    { zh: "投递追踪页", en: "Tracker Page" },
    { zh: "职位", en: "Role" },
    { zh: "画像 / 来源", en: "Profile / Source" },
    { zh: "分数", en: "Score" },
    { zh: "操作", en: "Actions" },
    { zh: "地点未注明", en: "Location unavailable" },
    { zh: "标记投递", en: "Mark Applied" },
    { zh: "不合适", en: "Dismiss" },
    { zh: "简历精修", en: "Tailor Resume" },
    { zh: "岗位描述", en: "Job Page" },
    { zh: "当前筛选条件下还没有职位。可以回到 Crawler 增加关键词或刷新一次。", en: "No jobs match the current filters. Go back to Crawler to add keywords or refresh." },
    { zh: "全部", en: "All" },
    { zh: "最近刷新", en: "Recently Refreshed" },
    { zh: "最高", en: "Best" },
    { zh: "供给", en: "Supply" },
    { zh: "画像供给权重", en: "Market priority" },
    { zh: "匹配分", en: "Match Score" },
    { zh: "最近 24 小时", en: "Last 24 Hours" },
    { zh: "追踪概览", en: "Tracking Overview" },
    { zh: "统一管理投递状态、时间线和后续精修入口", en: "Manage application state, timeline, and follow-up tailoring in one place." },
    { zh: "回到 Jobs", en: "Back to Jobs" },
    { zh: "回到爬虫中心", en: "Back to Crawler Center" },
    { zh: "当前筛选", en: "Active Filter" },
    { zh: "剩余", en: "Remaining" },
    { zh: "已投递", en: "Applied" },
    { zh: "已查阅", en: "Reviewed" },
    { zh: "手工新增", en: "Manual Add" },
    { zh: "没有抓到的岗位，也可以先录入这里继续跟踪", en: "Jobs that were not crawled can still be tracked here." },
    { zh: "职位名称", en: "Job Title" },
    { zh: "公司", en: "Company" },
    { zh: "来源站点", en: "Source Site" },
    { zh: "关联画像", en: "Profile Label" },
    { zh: "职位链接", en: "Job URL" },
    { zh: "备注", en: "Notes" },
    { zh: "新增追踪", en: "Create Track" },
    { zh: "追踪列表", en: "Tracking List" },
    { zh: "每条 track 同时显示当前阶段、完整时间线和下一步更新入口", en: "Each track shows the stage, full timeline, and next action entry point." },
    { zh: "来源类型", en: "Source Kind" },
    { zh: "当前阶段", en: "Current Stage" },
    { zh: "清空筛选", en: "Clear Filters" },
    { zh: "个事件", en: "events" },
    { zh: "尚未更新", en: "Not updated yet" },
    { zh: "最近备注", en: "Latest Notes" },
    { zh: "暂无备注", en: "No notes yet" },
    { zh: "事件流", en: "Event Timeline" },
    { zh: "无附加备注", en: "No extra notes" },
    { zh: "当前还没有事件记录。", en: "No events yet." },
    { zh: "追加阶段", en: "Add Stage Event" },
    { zh: "阶段", en: "Stage" },
    { zh: "时间", en: "Time" },
    { zh: "追加事件", en: "Add Event" },
    { zh: "取消追踪", en: "Stop Tracking" },
    { zh: "删除记录", en: "Delete Record" },
    { zh: "当前筛选条件下还没有投递追踪记录。", en: "No tracked applications match the current filters." },
    { zh: "Session 概览", en: "Session Overview" },
    { zh: "这里不再强调旧流水线，而是集中看 advice、session 和 PDF 是否可继续使用", en: "This page focuses on advice, sessions, and PDFs instead of the old pipeline." },
    { zh: "总记录", en: "Total Records" },
    { zh: "成功结束", en: "Succeeded" },
    { zh: "已停止", en: "Stopped" },
    { zh: "工作区列表", en: "Workspace List" },
    { zh: "每个职位工作区只保留一行，用累计运行数代替重复 run 堆叠", en: "Keep one row per job workspace and summarize repeated runs." },
    { zh: "PDF / Session", en: "PDF / Session" },
    { zh: "最近状态", en: "Latest Status" },
    { zh: "已生成", en: "Ready" },
    { zh: "暂无", en: "None yet" },
    { zh: "继续编辑", en: "Continue Editing" },
    { zh: "停止", en: "Stop" },
    { zh: "删除", en: "Delete" },
    { zh: "当前筛选下还没有 Tailor session 记录。", en: "No Tailor sessions match the current filters." },
    { zh: "Workspace Summary", en: "Workspace Summary" },
    { zh: "当前工作区按职位汇总，不再把每次 run 堆成主视图", en: "This workspace is summarized by job instead of stacking every run." },
    { zh: "同一职位工作区内的总 Tailor 次数", en: "Total tailor runs inside this job workspace." },
    { zh: "主视图只看最新一次状态", en: "The main view only tracks the latest state." },
    { zh: "最近更新时间", en: "Last Updated" },
    { zh: "用于判断是否需要重新生成建议", en: "Use this to decide whether advice should be regenerated." },
    { zh: "最近 Session", en: "Latest Session" },
    { zh: "保持当前工作区与 session 对齐", en: "Keep the current workspace aligned with the session." },
    { zh: "最近消息", en: "Latest Message" },
    { zh: "还没有 session 记录。", en: "No session history yet." },
    { zh: "Session 状态", en: "Session Status" },
    { zh: "已建立 Session", en: "Session Ready" },
    { zh: "Session 建立中", en: "Session Starting" },
    { zh: "Session 建立失败", en: "Session Failed" },
    { zh: "Session 未建立", en: "Session Missing" },
    { zh: "岗位描述窗口", en: "Open Job Window" },
    { zh: "新标签打开职位页", en: "Open Job Page in New Tab" },
    { zh: "完整筛选职位列表，并从这里进入单个岗位的简历精修。", en: "Filter the full job list and enter job-specific tailoring from here." },
    { zh: "单次抓取的 query 粒度结果、错误和时间线都收在这里，主列表保持简洁。", en: "Per-query results, errors, and the timeline for a single crawl are collected here while the main list stays compact." },
    { zh: "会话概览", en: "Session Overview" },
    { zh: "会话列表", en: "Session List" },
    { zh: "运行概览", en: "Run Overview" },
    { zh: "Query 结果", en: "Query Results" },
    { zh: "异常信息", en: "Warnings" },
    { zh: "工作区", en: "Workspace" },
    { zh: "PDF 预览", en: "PDF Preview" },
    { zh: "操作已完成。", en: "Action completed." },
    { zh: "异步提交失败，正在改用普通提交。", en: "Async submit failed. Falling back to a native form submit." },
    { zh: "请求失败，请查看终端日志。", en: "Request failed. Check the terminal log." },
    { zh: "当前画像", en: "current profile" },
    { zh: "切换侧栏", en: "Toggle sidebar" },
    { zh: "切换到中文", en: "Switch to Chinese" },
    { zh: "Switch to English", en: "Switch to English" },
    { zh: "界面语言", en: "UI language" },
    { zh: "主池", en: "Core Pool" },
    { zh: "桥接池", en: "Bridge Pool" },
    { zh: "卫星池", en: "Satellite Pool" },
    { zh: "打分公式", en: "Scoring" },
    { zh: "手工加入需要屏蔽的公司", en: "Add a company to exclude manually" },
    { zh: "LinkedIn / Indeed / 内推公司", en: "LinkedIn / Indeed / referral company" },
    { zh: "比如：内推人、当前状态、面试安排、需要补充的材料", en: "Example: referrer, current stage, interview schedule, materials to prepare" },
    { zh: "例如：约到 phone screen / 推荐人已介绍 / 面试失败原因", en: "Example: phone screen booked / referral intro completed / interview feedback" },
    { zh: "职位或公司", en: "Job title or company" },
    { zh: "可留空，自动根据名称生成", en: "Optional. Auto-generate from the name if left empty." },
    { zh: "例如 \"growth marketing manager\" saas | \"customer success manager\" b2b", en: "e.g. \"growth marketing manager\" saas | \"customer success manager\" b2b" },
    { zh: "新增搜索关键词，例如 \"growth marketing manager\" saas", en: "Add a search keyword, for example \"growth marketing manager\" saas" },
    { zh: "删除关键词", en: "Delete keyword" },
  ];

  const RUNTIME_MESSAGES = {
    unknownTime: { zh: "未知时间", en: "Unknown time" },
    requestFailed: {
      zh: ({ status }) => `请求失败（${status}）。`,
      en: ({ status }) => `Request failed (${status}).`,
    },
    jobWindowActionCompleted: {
      zh: "岗位描述窗口操作已完成。",
      en: "Job window action completed.",
    },
    manualOpenFallback: {
      zh: ({ url }) => ` 可手动打开：${url}`,
      en: ({ url }) => ` Open manually: ${url}`,
    },
    jobWindowOpenFailed: {
      zh: "打开岗位工作窗失败。",
      en: "Failed to open the job window.",
    },
    jobsJsonMissing: {
      zh: ({ status }) => `服务器没有返回 JSON（${status}）。`,
      en: ({ status }) => `The server did not return JSON (${status}).`,
    },
    jobsPageRequestFailed: {
      zh: ({ status }) => `Jobs 页面请求失败（${status}）。`,
      en: ({ status }) => `Jobs page request failed (${status}).`,
    },
    crawlerRunningBanner: {
      zh: ({ profileLabel, startedAt }) => `正在抓取 ${profileLabel}，开始于 ${startedAt}。`,
      en: ({ profileLabel, startedAt }) => `Crawling ${profileLabel}, started at ${startedAt}.`,
    },
    crawlerFinishedBanner: {
      zh: "后台抓取已结束。",
      en: "Background crawling has finished.",
    },
  };

  const PATTERN_TRANSLATORS = [
    {
      re: /^当前时区：(.+)$/,
      zh: (_, zone) => `当前时区：${zone}`,
      en: (_, zone) => `Timezone: ${zone}`,
    },
    {
      re: /^抓取中：(.+)$/,
      zh: (_, label) => `抓取中：${label}`,
      en: (_, label) => `Running: ${label}`,
    },
    {
      re: /^自动刷新 (\d+) 分钟$/,
      zh: (_, minutes) => `自动刷新 ${minutes} 分钟`,
      en: (_, minutes) => `Auto refresh ${minutes} min`,
    },
    {
      re: /^(\d+) 个画像$/,
      zh: (_, count) => `${count} 个画像`,
      en: (_, count) => `${count} profiles`,
    },
    {
      re: /^(\d+) 个职位$/,
      zh: (_, count) => `${count} 个职位`,
      en: (_, count) => `${count} jobs`,
    },
    {
      re: /^剩余 (\d+)$/,
      zh: (_, count) => `剩余 ${count}`,
      en: (_, count) => `Remaining ${count}`,
    },
    {
      re: /^已投递 (\d+)$/,
      zh: (_, count) => `已投递 ${count}`,
      en: (_, count) => `Applied ${count}`,
    },
    {
      re: /^已查阅 (\d+)$/,
      zh: (_, count) => `已查阅 ${count}`,
      en: (_, count) => `Reviewed ${count}`,
    },
    {
      re: /^最低分 (\d+)$/,
      zh: (_, score) => `最低分 ${score}`,
      en: (_, score) => `Min score ${score}`,
    },
    {
      re: /^总追踪 (\d+)$/,
      zh: (_, count) => `总追踪 ${count}`,
      en: (_, count) => `Tracks ${count}`,
    },
    {
      re: /^总任务 (\d+)$/,
      zh: (_, count) => `总任务 ${count}`,
      en: (_, count) => `Tasks ${count}`,
    },
    {
      re: /^运行中 (\d+)$/,
      zh: (_, count) => `运行中 ${count}`,
      en: (_, count) => `Running ${count}`,
    },
    {
      re: /^最高 ([\d.]+)$/,
      zh: (_, score) => `最高 ${score}`,
      en: (_, score) => `Best ${score}`,
    },
    {
      re: /^最佳 ([\d.]+)$/,
      zh: (_, score) => `最佳 ${score}`,
      en: (_, score) => `Best ${score}`,
    },
    {
      re: /^匹配分 ([\d.]+)$/,
      zh: (_, score) => `匹配分 ${score}`,
      en: (_, score) => `Match ${score}`,
    },
    {
      re: /^供给 ([\d.]+)$/,
      zh: (_, score) => `供给 ${score}`,
      en: (_, score) => `Supply ${score}`,
    },
    {
      re: /^画像供给权重 ([\d.]+)$/,
      zh: (_, score) => `画像供给权重 ${score}`,
      en: (_, score) => `Market priority ${score}`,
    },
    {
      re: /^开始 (.+)$/,
      zh: (_, value) => `开始 ${value}`,
      en: (_, value) => `Started ${value}`,
    },
    {
      re: /^结束 (.+)$/,
      zh: (_, value) => `结束 ${value}`,
      en: (_, value) => `Finished ${value}`,
    },
    {
      re: /^发布 (.+)$/,
      zh: (_, value) => `发布 ${value}`,
      en: (_, value) => `Posted ${value}`,
    },
    {
      re: /^投递 (.+)$/,
      zh: (_, value) => `投递 ${value}`,
      en: (_, value) => `Applied ${value}`,
    },
    {
      re: /^抓到 (\d+)$/,
      zh: (_, count) => `抓到 ${count}`,
      en: (_, count) => `Seen ${count}`,
    },
    {
      re: /^保存 (\d+)$/,
      zh: (_, count) => `保存 ${count}`,
      en: (_, count) => `Saved ${count}`,
    },
    {
      re: /^默认折叠，累计 (\d+) 次$/,
      zh: (_, count) => `默认折叠，累计 ${count} 次`,
      en: (_, count) => `Collapsed by default, ${count} runs total`,
    },
    {
      re: /^累计 (\d+) 次$/,
      zh: (_, count) => `累计 ${count} 次`,
      en: (_, count) => `${count} runs`,
    },
    {
      re: /^(\d+) 个事件$/,
      zh: (_, count) => `${count} 个事件`,
      en: (_, count) => `${count} events`,
    },
    {
      re: /^最近刷新 (.+)$/,
      zh: (_, value) => `最近刷新 ${value}`,
      en: (_, value) => `Refreshed ${value}`,
    },
    {
      re: /^时间按 (.+) 解释并保存。$/,
      zh: (_, tz) => `时间按 ${tz} 解释并保存。`,
      en: (_, tz) => `Time is parsed and saved in ${tz}.`,
    },
    {
      re: /^关键词：(.+)$/,
      zh: (_, value) => `关键词：${value}`,
      en: (_, value) => `Keyword: ${value}`,
    },
    {
      re: /^打分公式：(.+)$/,
      zh: (_, formula) => `打分公式：${translateScoringFormula(formula, "zh")}`,
      en: (_, formula) => `Scoring: ${translateScoringFormula(formula, "en")}`,
    },
    {
      re: /^刷新完成：(\d+) 个画像，合计保存 (\d+) 条职位。$/,
      zh: (_, profileCount, jobsCount) => `刷新完成：${profileCount} 个画像，合计保存 ${jobsCount} 条职位。`,
      en: (_, profileCount, jobsCount) => `Refresh finished: ${profileCount} profiles, ${jobsCount} jobs saved in total.`,
    },
    {
      re: /^画像 (.+) 刷新完成：抓到 (\d+) 条，保存 (\d+) 条。$/,
      zh: (_, profileLabel, seen, saved) => `画像 ${profileLabel} 刷新完成：抓到 ${seen} 条，保存 ${saved} 条。`,
      en: (_, profileLabel, seen, saved) => `Profile ${profileLabel} finished: ${seen} seen, ${saved} saved.`,
    },
    {
      re: /^正在抓取 (.+)，开始于 (.+)。$/,
      zh: (_, profileLabel, startedAt) => `正在抓取 ${profileLabel}，开始于 ${startedAt}。`,
      en: (_, profileLabel, startedAt) => `Crawling ${profileLabel}, started at ${startedAt}.`,
    },
    {
      re: /^(.+) 抓取详情$/,
      zh: (_, profileLabel) => `${profileLabel} 抓取详情`,
      en: (_, profileLabel) => `${profileLabel} Crawl Detail`,
    },
    {
      re: /^(.+) 的单次抓取结果$/,
      zh: (_, profileLabel) => `${profileLabel} 的单次抓取结果`,
      en: (_, profileLabel) => `Single crawl run for ${profileLabel}`,
    },
  ];

  const AUTO_TEXT_SELECTORS = [
    ".sidebar-link-label",
    ".sidebar-group-title",
    ".sidebar-meta-title",
    ".section-link",
    "#sidebar-summary-label",
    "#sidebar-summary-title",
    "#sidebar-summary-copy",
    "#page-eyebrow",
    "#page-title",
    "#page-subtitle",
    ".header-badge",
    ".page-action-link",
    ".section-kicker",
    ".section-card-header h3",
    ".stat-label",
    ".stat-card strong",
    ".quick-actions a",
    ".empty-state",
    ".back-link",
    ".mini-surface-label",
    ".mini-surface strong",
    ".mini-surface-head > span",
    ".table-header span",
    ".table-sort-link",
    ".jobs-summary-pill",
    ".jobs-summary-label",
    ".term-chip-launch",
    ".row-inline-button",
    ".ghost-link",
    ".primary-link",
    ".ghost-button",
    ".primary-button",
    "#sidebar-status-copy",
    "#sidebar-timezone-note",
    ".wide-note",
    ".table-line span",
    ".meta-pill",
    ".status-pill",
    ".row-subtitle",
    ".mini-surface-text",
    ".muted-copy",
    ".tracker-subhead strong",
    ".timeline-fallback-copy",
    ".markdown-card-kicker",
    ".markdown-card-title",
    "summary > span",
    "option",
    "legend",
    ".warning-pill",
  ];

  const TEXT_INDEX = new Map();
  for (const pair of TEXT_PAIRS) {
    TEXT_INDEX.set(pair.zh, pair);
    TEXT_INDEX.set(pair.en, pair);
  }
  const originalElementTexts = new WeakMap();
  const originalTextNodes = new WeakMap();
  const originalAttributes = new WeakMap();
  const rootMetadata = {
    documentTitle: document.title,
  };

  function translateScoringFormula(text, language) {
    if (!text) return text;
    if (language === "en") {
      return text
        .replace(/^总分 = /, "Total = ")
        .replaceAll("标题相似度", "title similarity")
        .replaceAll("关键词覆盖", "keyword coverage")
        .replaceAll("领域相似度", "domain similarity")
        .replaceAll("市场供给匹配", "market supply fit")
        .replaceAll("stop-keyword 命中", "stop-keyword hit");
    }
    return text
      .replace(/^Total = /, "总分 = ")
      .replaceAll("title similarity", "标题相似度")
      .replaceAll("keyword coverage", "关键词覆盖")
      .replaceAll("domain similarity", "领域相似度")
      .replaceAll("market supply fit", "市场供给匹配")
      .replaceAll("stop-keyword hit", "stop-keyword 命中");
  }

  function translateSingleValue(text, language) {
    const entry = TEXT_INDEX.get(text);
    if (entry) {
      return entry[language];
    }

    for (const translator of PATTERN_TRANSLATORS) {
      const match = text.match(translator.re);
      if (match) {
        return translator[language](...match);
      }
    }

    return text;
  }

  function getLanguage() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      if (value && SUPPORTED_LANGUAGES.has(value)) {
        return value;
      }
    } catch (error) {
      console.warn("Failed to read UI language preference.", error);
    }
    return DEFAULT_LANGUAGE;
  }

  function setLanguage(language, { persist = true } = {}) {
    if (!SUPPORTED_LANGUAGES.has(language)) {
      return;
    }
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, language);
      } catch (error) {
        console.warn("Failed to persist UI language preference.", error);
      }
    }
    applyLanguage(document, language);
    window.dispatchEvent(
      new CustomEvent("quickapply:languagechange", {
        detail: { language },
      }),
    );
  }

  function replaceBoundaryWhitespace(original, translated) {
    const leading = original.match(/^\s*/)?.[0] || "";
    const trailing = original.match(/\s*$/)?.[0] || "";
    return `${leading}${translated}${trailing}`;
  }

  function translateLooseFragments(text, language) {
    if (!text) return text;
    const separatorPattern = /(\s+[·/]\s+)/;
    const parts = text.split(separatorPattern);
    if (parts.length > 1) {
      return parts
        .map((part) => {
          if (!part || separatorPattern.test(part)) {
            return part;
          }
          return replaceBoundaryWhitespace(
            part,
            translateSingleValue(part.trim(), language),
          );
        })
        .join("");
    }
    if (language === "en") {
      return text
        .replaceAll("地点未注明", "Location unavailable")
        .replaceAll("未记录工作区", "Workspace missing");
    }
    return text
      .replaceAll("Location unavailable", "地点未注明")
      .replaceAll("Workspace missing", "未记录工作区");
  }

  function translateTextValue(text, language = getLanguage()) {
    const trimmed = text.trim();
    if (!trimmed) {
      return text;
    }

    const translatedExact = translateSingleValue(trimmed, language);
    if (translatedExact !== trimmed) {
      return replaceBoundaryWhitespace(text, translatedExact);
    }

    const fragmentTranslated = translateLooseFragments(trimmed, language);
    if (fragmentTranslated !== trimmed) {
      return replaceBoundaryWhitespace(text, fragmentTranslated);
    }
    return text;
  }

  function translateAttributeValue(value, language = getLanguage()) {
    return translateTextValue(value, language);
  }

  function shouldSkipElement(element) {
    return Boolean(element.closest(SKIP_SELECTOR));
  }

  function applyTextTranslation(element, language) {
    if (!(element instanceof Element) || shouldSkipElement(element)) {
      return;
    }
    const hasElementChildren = Array.from(element.childNodes).some(
      (node) => node.nodeType === Node.ELEMENT_NODE,
    );
    if (!hasElementChildren) {
      const originalText = originalElementTexts.get(element) ?? element.textContent ?? "";
      originalElementTexts.set(element, originalText);
      const translated = translateTextValue(originalText, language);
      if (translated !== element.textContent) {
        element.textContent = translated;
      }
      return;
    }

    for (const node of element.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE) {
        continue;
      }
      const originalText = originalTextNodes.get(node) ?? node.textContent ?? "";
      originalTextNodes.set(node, originalText);
      const translated = translateTextValue(originalText, language);
      if (translated !== node.textContent) {
        node.textContent = translated;
      }
    }
  }

  function applyLabelTranslation(label, language) {
    if (!(label instanceof HTMLLabelElement) || shouldSkipElement(label)) {
      return;
    }
    for (const node of label.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE) {
        continue;
      }
      if (!node.textContent || !node.textContent.trim()) {
        continue;
      }
      const originalText = originalTextNodes.get(node) ?? node.textContent ?? "";
      originalTextNodes.set(node, originalText);
      const translated = translateTextValue(originalText, language);
      if (translated !== node.textContent) {
        node.textContent = translated;
      }
      break;
    }
  }

  function applyAttributeTranslations(root, language) {
    for (const element of root.querySelectorAll("[placeholder], [title], [aria-label]")) {
      if (!(element instanceof Element) || shouldSkipElement(element)) {
        continue;
      }
      const originalValues = originalAttributes.get(element) ?? {};
      for (const attributeName of ["placeholder", "title", "aria-label"]) {
        const baselineValue = originalValues[attributeName] ?? element.getAttribute(attributeName);
        if (!baselineValue) continue;
        originalValues[attributeName] = baselineValue;
        const translated = translateAttributeValue(baselineValue, language);
        if (translated !== element.getAttribute(attributeName)) {
          element.setAttribute(attributeName, translated);
        }
      }
      originalAttributes.set(element, originalValues);
    }
  }

  function applyDataTranslations(root, language) {
    for (const element of root.querySelectorAll("[data-i18n-text]")) {
      if (!(element instanceof Element) || shouldSkipElement(element)) {
        continue;
      }
      const baselineText = element.getAttribute("data-i18n-text") || "";
      const translated = translateTextValue(baselineText, language);
      if (translated !== element.textContent) {
        element.textContent = translated;
      }
    }

    for (const element of root.querySelectorAll("[data-i18n-placeholder]")) {
      if (!(element instanceof Element)) {
        continue;
      }
      const baselineValue = element.getAttribute("data-i18n-placeholder") || "";
      element.setAttribute("placeholder", translateAttributeValue(baselineValue, language));
    }

    for (const element of root.querySelectorAll("[data-i18n-title]")) {
      if (!(element instanceof Element)) {
        continue;
      }
      const baselineValue = element.getAttribute("data-i18n-title") || "";
      element.setAttribute("title", translateAttributeValue(baselineValue, language));
    }

    for (const element of root.querySelectorAll("[data-i18n-aria-label]")) {
      if (!(element instanceof Element)) {
        continue;
      }
      const baselineValue = element.getAttribute("data-i18n-aria-label") || "";
      element.setAttribute("aria-label", translateAttributeValue(baselineValue, language));
    }
  }

  function syncLanguageSwitch(root, language) {
    for (const button of root.querySelectorAll("[data-language-option]")) {
      if (!(button instanceof HTMLButtonElement)) continue;
      const isActive = button.dataset.languageOption === language;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    }
  }

  function applyLanguage(root = document, forcedLanguage = null) {
    const language = forcedLanguage || getLanguage();
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";

    for (const selector of AUTO_TEXT_SELECTORS) {
      for (const element of root.querySelectorAll(selector)) {
        applyTextTranslation(element, language);
      }
    }

    applyDataTranslations(root, language);

    for (const label of root.querySelectorAll("label")) {
      applyLabelTranslation(label, language);
    }

    applyAttributeTranslations(root, language);
    document.title = translateTextValue(rootMetadata.documentTitle, language);
    syncLanguageSwitch(root, language);
  }

  function runtimeText(messageKey, params = {}) {
    const language = getLanguage();
    const entry = RUNTIME_MESSAGES[messageKey];
    if (!entry) {
      return "";
    }
    const value = entry[language];
    return typeof value === "function" ? value(params) : value;
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-language-option]");
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    const language = button.dataset.languageOption;
    if (!language) {
      return;
    }
    setLanguage(language);
  });

  window.resumeJobMonitor = Object.assign(window.resumeJobMonitor || {}, {
    getLanguage,
    setLanguage,
    applyLanguage,
    translateText: translateTextValue,
    translateAttributeValue,
    rt: runtimeText,
  });

  applyLanguage(document);
})();
