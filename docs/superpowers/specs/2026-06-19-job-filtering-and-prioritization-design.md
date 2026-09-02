# Design Spec: Enhanced Job Filtering & Prioritization

**Date**: 2026-06-19  
**Status**: Approved

This document specifies the enhancements to the job hunting pipeline to expand the roles net (Sales, Account Management, Partnerships, Customer Success) while applying stricter filters to remove roles requiring 5+ years of experience or hard Dutch speaking fluency. In addition, it defines a prioritization mechanism to highlight roles with collaborative team structures and learning opportunities.

## Proposed Changes

### 1. Title Keywords Expansion (`jobhunt/config.py`)
Add keyword targets for Sales, Account Management, Partnerships, and Customer Success to the default matching targets:
*   **Target Keywords**: `"sales"`, `"account manager"`, `"account management"`, `"customer success"`, `"client success"`, `"partnership"`, `"partnerships"`, `"business development"`, `"growth"`

### 2. Strict Filter Checks (`jobhunt/filters.py`)
Extend `job_ok` to inspect the job description and title for the following constraints:
*   **Dutch Language fluency exclusions**: Exclude postings containing explicit requirements for native or fluent Dutch. 
    *   *Exclusions*: `vloeiend nederlands`, `nederlands vereist`, `nederlands is een vereiste`, `nederlands als moedertaal`, `dutch fluency is a must`, `must be fluent in dutch`.
    *   *Permitted*: Postings written in Dutch without strict fluency requirements, or ones indicating "Dutch is a pre/plus" or "bilingual English/Dutch".
*   **Experience Threshold exclusions**: Exclude postings requiring 5 or more years of experience.
    *   *Exclusions*: Matches for `[5-9]\+?\s*(?:-|to|tot)?\s*[0-9]*\s*(?:years?|yrs?|jaar|jr)` (e.g. `5+ years`, `5-8 years`, `at least 5 years`, `5 jaar ervaring`).
    *   *Permitted*: Postings requiring 2-4 years, or postings that do not specify any experience requirements.

### 3. Priority Scoring (`jobhunt/filters.py`)
Compute a priority level based on description keywords:
*   **Team Keywords**: `team`, `collaborate`, `collaboration`, `collaborative`, `cross-functional`, `peer`, `together`
*   **Learning/Growth Keywords**: `learn`, `training`, `growth`, `mentor`, `mentorship`, `development`, `coach`, `coaching`, `upskill`
*   **Classifications**:
    *   `⭐ High`: Contains $\ge 1$ Team keyword AND $\ge 1$ Learning/Growth keyword.
    *   `Medium`: Contains either a Team keyword OR a Learning/Growth keyword, but not both.
    *   `Low`: Contains neither.

### 4. Database Schema Migration (`jobhunt/database.py`)
*   Add the `priority` column (TEXT) to the `jobs` database.
*   Implement safe migration in `init_db()` by checking for the column's existence and running `ALTER TABLE jobs ADD COLUMN priority TEXT` if missing.
*   Update `upsert_jobs()` to save the calculated priority.

### 5. CSV and Markdown Export (`jobhunt/export.py`)
*   Include the `priority` column in `jobs.csv`.
*   Include the `priority` column in `careers-directory.md` next to the `date` field.
*   Update schema notes in `careers-directory.md` to explain the priority column.
