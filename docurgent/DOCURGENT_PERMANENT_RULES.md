# DOCURGENT — PERMANENT HEALTHCARE ENGINEERING RULES

These permanent development rules govern all engineering, maintenance, and enhancement tasks for the **DocUrgent** platform.

---

### Core Principles & Non-Negotiable Rules

1. **Interface Preservation**: Never redesign or alter the existing UI, layouts, spacing, or clinical light-theme color palette (white, medical blue, slate, coral, emerald) unless explicitly instructed by the user.
2. **Feature Preservation**: Never delete, comment out, or degrade existing working features.
3. **Pre-Modification Inspection**: Thoroughly inspect the existing code, dependencies, and state flow before modifying any file.
4. **Content Verification**: Never overwrite existing project files without checking and understanding their current contents.
5. **Version Control Discipline**: Always use Git to track changes, maintain clean commit histories, and preserve the previous working version before applying major modifications.
6. **Incremental Execution**: Implement changes in small, well-bounded, manageable stages.
7. **Continuous Automated Verification**: Run relevant automated test suites (`test_docurgent.py`) after every significant change to detect regressions immediately.
8. **Empirical Truthfulness**: Never claim that a feature or service works without direct automated or manual verification.
9. **Zero Fake/Simulated Data in Production**: Never use simulated, mocked, or placeholder data in production-facing functionality. Clearly label any remaining demo features as demonstration-only.
10. **Secrets & Credentials Security**: Never hardcode passwords, API keys, private tokens, or secrets in source files or frontend scripts. Always use environment variables or secure configuration.
11. **Protected Health Information (PHI) Privacy**: Strictly guard patient privacy. Patients must never access another patient's medical records or consultation data.
12. **Database Integrity & Migrations**: Never modify the production SQLite database (`docurgent.db`) without an approved migration script and a timestamped backup.
13. **Server-Side Validation**: Always validate all user input on the server, enforcing whitelist checks, size limits, and sanitization before processing or storing.
14. **Role-Based Access Control (RBAC)**: Strictly enforce role-based access for `patient`, `doctor`, and `admin` roles across all backend API endpoints and frontend views.
15. **Anti-Privilege Escalation**: Never allow a normal user (patient or doctor) to promote themselves to administrator.
16. **Environment Separation**: Maintain a clear separation between development, staging/demo, and production configurations.
17. **Transparent Reporting**: Always provide a detailed, accurate summary of all modified and newly created files.
18. **Unvarnished Error Reporting**: Always report failed tests, edge-case limitations, and unfinished tasks transparently.
19. **Destructive Action Confirmation**: Do not automatically delete unused files; first explain why they are unused and obtain explicit user approval.
20. **Performance & Simplicity**: Keep the application architecture simple, fast, responsive, and maintainable. Avoid unnecessary dependencies or bloated frameworks.

---

### Mandatory Pre-Completion Verification Checklist

Before marking any task as complete, verify:
- [ ] Application server starts successfully via standard launchers (`Launch_DocUrgent.command`, `python3 server.py`).
- [ ] No critical browser console errors or uncaught runtime exceptions.
- [ ] No broken, unreachable, or unauthenticated API endpoints.
- [ ] No unauthorized data access (patients cannot access other patients or admin endpoints).
- [ ] All existing features remain fully functional.
- [ ] All automated tests pass (`python3 test_docurgent.py`).

---

### Safety Stop Protocol

> **CRITICAL**: If any planned change risks data loss, security compromise, payment calculation corruption, or medical triage safety, **STOP IMMEDIATELY** and request explicit user confirmation before proceeding.
