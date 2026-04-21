# Crawler, Jobs, and Tracker Workflow

[简体中文](./workflows.zh-CN.md)

> Navigation: [← Configuration Guide](./configuration.md) · [Documentation Home](./README.md) · [Next: Tailor Workflow →](./tailor.md)

> 🧭 QuickApply works best as one operations loop: check the board, refresh the market, filter the pool, track real applications, then move into Tailor only for the roles that matter.

## 🖼️ Workflow Overview

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="#1-dashboard">
        <img src="./screenshots/dashboard-en.png" alt="Dashboard" width="100%" />
      </a>
      <br />
      <strong>1. Dashboard</strong>
      <br />
      <sub>Scan the whole operation in one glance.</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="#2-crawler">
        <img src="./screenshots/crawler-en.png" alt="Crawler" width="100%" />
      </a>
      <br />
      <strong>2. Crawler</strong>
      <br />
      <sub>Tune profiles, keywords, sources, and crawl runs.</sub>
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
      <sub>Filter down to roles worth acting on.</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="#4-tracker">
        <img src="./screenshots/tracker-en.png" alt="Tracker" width="100%" />
      </a>
      <br />
      <strong>4. Tracker</strong>
      <br />
      <sub>Turn applied jobs into a maintainable pipeline.</sub>
    </td>
  </tr>
</table>

## 1. Dashboard

![Dashboard](./screenshots/dashboard-en.png)

Use `Dashboard` when you want the fastest answer to a simple question:
**where should I pay attention right now?**

What this page answers:

- are there any strong matches worth opening immediately
- did recent crawls produce useful output
- is tracking activity moving forward
- is any tailoring work still in flight

What to do next:

- jump to `Crawler` if the market looks stale or thin
- jump to `Jobs` if strong matches are already visible
- jump to `Tracker` if you want to review already-applied roles

## 2. Crawler

![Crawler](./screenshots/crawler-en.png)

Use `Crawler` as the market tuning page.

What lives here:

- search profiles
- keyword sets
- default resume mapping
- locations and source sites
- crawl history with run-level output

What to watch:

- a profile can look reasonable but still produce poor crawl yield
- LinkedIn and Indeed can rate-limit repeated runs
- crawl history is the best place to confirm whether a profile is productive

Good next moves:

- add or remove search terms when a profile returns empty runs
- narrow locations when results are too noisy
- keep the strongest profiles and stop feeding weak ones

## 3. Jobs

![Jobs](./screenshots/jobs-en.png)

Use `Jobs` when you need to cut a broad pool down to an actionable shortlist.

What you can do here:

- filter by profile, location, include keywords, exclude keywords, score, time window, and country
- open the original job page in one reused dedicated Chrome window
- exclude bad companies once and keep them out of future review
- dismiss noisy roles
- mark applied jobs and remove them from the remaining pool
- open Tailor only for the jobs that deserve real work

What the counts mean:

- `Remaining`: still worth active review
- `Applied`: already moved into the application pipeline
- `Reviewed`: applied plus dismissed roles

Rule of thumb:

- if the role is weak, dismiss it or exclude the company
- if the role is strong but not yet ready, keep it in the remaining pool
- if you actually applied, mark it and continue in `Tracker`
- if you open multiple roles in sequence, QuickApply keeps refreshing the same dedicated Chrome window so your main browser does not explode into extra tabs

## 4. Tracker

![Tracker](./screenshots/tracker-en.png)

Use `Tracker` after the role becomes real.

This page is for:

- jobs marked as applied from `Jobs`
- manual entries such as referrals or off-platform applications
- stage changes like submitted, introduced, interviewed, or failed
- notes that explain what happened and what comes next

Why it matters:

- it prevents already-applied roles from drifting back into the main review pool
- it keeps stage history tied to one job record
- it becomes the clean handoff point for follow-up tailoring and next actions

## Where Tailor Fits

The loop usually ends like this:

1. discover in `Crawler`
2. shortlist in `Jobs`
3. track real progress in `Tracker`
4. open `Tailor` only for a serious role that deserves a customized resume

For the tailoring side, continue in [tailor.md](./tailor.md).

---

> Continue: [← Configuration Guide](./configuration.md) · [Documentation Home](./README.md) · [Next: Tailor Workflow →](./tailor.md)
