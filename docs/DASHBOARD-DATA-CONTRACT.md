# Dashboard Data Contract

Maps every visible value on the TrustOffice dashboard to its API field and backend query. No visible value may be static, hardcoded, or unsubstantiated.

## API: GET /api/dashboard?trust_id=X

Source: `backend/routers/governance.py` → `get_dashboard()`

## Response Model: DashboardResponse (backend/models.py)

| Field | Type | Source |
|-------|------|--------|
| `trust_id` | str | Resolved from query param or user's first trust |
| `trust_name` | str | `db.trusts.find_one().name` |
| `health_score` | HealthScoreResponse | `calculate_health_score(trust_id, user_id)` |
| `onboarding_state` | OnboardingState | `get_onboarding_state(user_id, trust_id)` |
| `recent_activity` | List[dict] | `get_recent_activity(user_id, trust_id, limit=10)` |
| `stats` | DashboardStats | `get_dashboard_stats(trust_id, user_id)` |
| `governance_insights` | List[GovernanceInsight] | `_get_active_insights(trust_id, user_id, criteria)` |
| `subscription` | DashboardSubscriptionState | `get_subscription_state(user_id)` |
| `pending_quarterly_draft` | Optional[dict] | `_get_pending_quarterly_draft(trust_id, user_id)` |

## Additional API Calls (Frontend)

| Call | Endpoint | Component |
|------|----------|-----------|
| Tax deadlines | `GET /api/trusts/{trust_id}/tax-calendar/upcoming?days=90` | DashboardTaxCalendar |
| Weekly briefing | `GET /api/ai/weekly-briefing?trust_id=X` | DashboardWeeklyBriefing |
| Banking summary | `GET /api/trusts/{trust_id}/bank-accounts/summary` | BankingSummaryCard |
| Spending threshold | (internal) | SpendingThresholdCard |

## Component → Data Mapping

### DashboardNextActionHero
- **Title/CTA/Context:** Derived from `computeNextAction(taxDeadlines, onboardingProgress, insights)` in `constants.js`
- **Priority:** 1. Overdue tax deadline (from tax API) → 2. First incomplete onboarding step → 3. Highest-point governance insight
- **"All caught up":** Shown when `computeNextAction()` returns null (no overdue, no incomplete onboarding, no insights)

### DashboardTodaysFocus
- **Insight count:** `insights.length` from `dashboard.governance_insights`
- **Points total:** Sum of `insight.points` for displayed insights (after dedup with hero)
- **Each insight:** `type`, `title`, `description`, `action_path`, `action_label`, `points` — all from GovernanceInsight model
- **Perfect score badge:** `healthScore.total_score === healthScore.max_score`

### DashboardHealthScoreCard
- **Score:** `healthScore.total_score`
- **Criteria:** `healthScore.criteria[]` — each has `name`, `achieved`, `points`, `max_points`, `description`
- **Banners:** Contextual — new trust (<14 days) with low score → encouragement; score <72 → urgent; 72-95 → needs attention

### DashboardQuickActionsCard
- **Stats:** `stats.total_decisions` (minutes_records + minutes_templates count), `stats.pending_reviews` (incomplete governance_tasks count)
- **Quick actions:** Static config in `constants.js` — links to known pages, not data-driven

### DashboardRecentActivity
- **Activities:** `dashboard.recent_activity[]` — each has `type`, `title`, `date`, `status`, `id`
- **Stats sidebar:** `stats.total_distributions`, `stats.ytd_distributions_amount`

### DashboardTaxCalendar
- **Deadlines:** `taxDeadlines[]` from tax calendar API — each has `description`, `due_date`, `days_remaining`, `filing_status`, `is_overdue`
- **Empty state:** "No tax calendar generated yet" with setup CTA — only shown when API returns empty array
- **All not required:** When all deadlines have `filing_status === 'not_required'` (trust created mid-year, past deadlines marked N/A)

### DashboardWeeklyBriefing
- **Items:** `weeklyBriefing[]` from AI briefing API — each has `title`, `severity`, `action_link`, `cta_prompt`
- **Dedup:** Removes items whose `action_link` matches an insight `action_path` already in Today's Focus

### BankingSummaryCard
- **Account count:** `summary.account_count` from banking API
- **Total balance:** `summary.total_latest_balance`
- **States:** Loading → Error (with retry) → Empty (0 accounts, CTA to add) → Data (count + balance)
- **Processing:** `accountCount > 0 && totalBalance == null` → "Statements Processing"

## Error Handling Rules

1. **API failure must show error state, not empty state.** Banking card already implements this (TO-004 fix).
2. **Loading state must prevent null renders.** Dashboard uses skeleton cards during `loading === true`.
3. **No static engagement bait.** "N actions to boost your score" is derived from actual insight points, not a static number.
4. **Progressive disclosure.** Recommendations (Today's Focus, Weekly Briefing, Tax Calendar) only appear after onboarding is complete or dismissed.

## Layout Rules

1. **Two columns** for comparable compact summaries: Banking + Spending Threshold cards
2. **Full width** for sequential/priority content: Next Action Hero, Onboarding Checklist, Today's Focus, Weekly Briefing, Tax Calendar
3. **Health Score:** 2/3 width, Quick Actions: 1/3 width (lg:grid-cols-3)
4. **Recent Activity:** Full width at bottom (it's a timeline, not a priority card)
5. **Responsive:** All grids collapse to single column on mobile