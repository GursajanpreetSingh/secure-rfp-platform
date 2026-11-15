"""DOC-001 Information Security Policy, part 4: sections 19 to 22 and the appendices."""

from app.datagen import model as m
from app.datagen.facts import Facts
from app.datagen.markup import section


def sections(facts: Facts, entry) -> tuple[m.Section, ...]:
    return (
        _incidents(facts),
        _continuity(facts),
        _compliance(),
        _maintenance(facts),
        _appendix_requirements(facts),
        _appendix_related(),
    )


def _incidents(facts: Facts) -> m.Section:
    ir = facts.get("incident_response")
    hours = facts.get("security.incident_notification_hours")
    levels = "\n".join(
        f"        | {s['level']} | {s['name']} | {s['definition']} |" for s in ir["severity_levels"]
    )
    phases = ", ".join(ir["phases"][:-1]) + f" and {ir['phases'][-1]}"
    roles = ", ".join(ir["roles"][:-1]) + f" and {ir['roles'][-1]}"
    return section(
        "19. Incident management",
        f"""
        An incident is any event that compromises, or may compromise, the confidentiality,
        integrity or availability of information or services. Incidents cannot be prevented
        entirely, so the company prepares to handle them quickly and honestly.

        ### 19.1 Reporting

        Every person who notices an incident or a suspicious event must report it to the
        security team immediately, using the incident channel or the security mailbox. A report
        made in good faith is never grounds for discipline, even if it turns out to be a false
        alarm. Customers are told how to report suspected incidents in their service documents.

        ### 19.2 Severity levels

        The incident commander assigns a severity when the incident is triaged and revises it as
        facts emerge. The severity decides who is involved and how quickly the company acts.

        | Level | Name | Definition |
        |---|---|---|
{levels}
        Caption: Table 12. Incident severity levels

        ### 19.3 Response lifecycle

        Every incident passes through six phases: {phases}. Each phase has a named owner, and
        the scribe keeps a timeline of decisions and actions as the incident unfolds. The
        incident roles are {roles}. Detailed procedures and checklists for each phase are held
        in the incident response plan that supports this policy.

        ### 19.4 Notifying customers and authorities

        If an incident affects customer data, the company notifies the affected customers
        without undue delay and in any case within {hours} hours of becoming aware of it. The
        notice states what happened, what information is involved, what the company has done
        and what the customer should do. The Data Protection Officer decides whether a
        regulator must also be told, and makes that notification within the period that the
        law sets.

        IMPORTANT: Nobody other than the communications lead, or a person they authorise, may
        speak to customers, the press or regulators about an incident.

        ### 19.5 Review and learning

        After every severity 1 or severity 2 incident the incident commander leads a review that
        does not seek to blame individuals. The review records the cause, what worked and what
        did not, and the actions that will stop it recurring. The Information Security Steering
        Committee tracks those actions to completion.

        ### 19.6 Evidence

        Evidence includes incident tickets and timelines, notification records, review reports
        and the log of actions closed.
        """,
    )


def _continuity(facts: Facts) -> m.Section:
    c = facts.get("continuity")
    return section(
        "20. Business continuity and backup",
        f"""
        Customers depend on the platform for their own compliance work, so the company plans to
        keep it running through failures and to restore it quickly when something goes wrong.

        ### 20.1 Backups

        Customer data and the configuration needed to restore the platform are backed up
        {c["backup_frequency"]}. Backups are encrypted as described in section 10, are stored in
        the same region as the data they protect, and are protected from deletion by the
        accounts that run the platform. The backup service verifies each backup and reports
        failures to the on-call engineer.

        ### 20.2 Recovery objectives

        The company plans its recovery around two objectives. The recovery point objective is
        the most data the company accepts to lose, and the recovery time objective is the
        longest the platform may be unavailable after a major failure.

        | Objective | Target |
        |---|---|
        | Recovery point objective (RPO) | {c["rpo_hours"]} hours |
        | Recovery time objective (RTO) | {c["rto_hours"]} hours |
        | Backup frequency | {c["backup_frequency"].capitalize()} |
        | Disaster recovery test | {c["dr_test_frequency"].capitalize()} |
        Caption: Table 13. Continuity objectives

        ### 20.3 Testing

        Restore procedures and the disaster recovery plan are tested {c["dr_test_frequency"]}.
        Each test uses a realistic scenario, such as the loss of the primary data centre, and
        records how long recovery took and whether data was lost. Gaps found during a test are
        raised as actions and tracked to closure.

        ### 20.4 Evidence

        Evidence includes backup job reports, restore test results, disaster recovery test
        reports and the continuity plan with its approval record.
        """,
    )


def _compliance() -> m.Section:
    return section(
        "21. Compliance, audit and exceptions",
        """
        The company follows the law and its own rules, and it shows that it does so.

        ### 21.1 Legal and contractual obligations

        The Head of Legal and Compliance keeps a register of the laws, regulations and customer
        contract terms that affect information security, and updates it when they change. Each
        obligation in the register is linked to the control that meets it and to the person
        responsible for that control.

        ### 21.2 Management system and audits

        The company operates an information security management system that is certified to
        ISO/IEC 27001. The system is audited internally each year, and by an independent
        certification body on the schedule that the standard requires. Findings are recorded,
        given an owner and a date, and followed up until they are closed. Customers may ask to
        review evidence of the company's controls, and requests for an on-site audit are
        agreed in advance in the customer contract.

        ### 21.3 Non-compliance

        Failure to follow this policy is reported to the line manager and the security team.
        The Chief Information Security Officer decides what is needed to correct the failure.
        Where a breach was deliberate or careless, the disciplinary process in section 17.3
        applies.

        ### 21.4 Evidence

        Evidence includes the register of obligations, internal audit reports, certification
        audit reports and the tracker of audit findings.
        """,
    )


def _maintenance(facts: Facts) -> m.Section:
    reg = facts.get("policy_register.information_security_policy")
    return section(
        "22. Policy maintenance",
        f"""
        The {reg["owner"]} reviews this policy at least every {reg["review_cycle_months"]}
        months, and sooner after a major incident, a significant change to the platform, a
        change in the law or a finding from an audit. The review checks that each requirement
        is still necessary, that it can be met in practice and that it matches the standards
        and procedures beneath it.

        Changes are drafted by the Information Security Manager, reviewed by the Information
        Security Steering Committee and approved as described in section 1.3. A new version
        replaces the old one on its effective date, the revision history is updated, and the
        old version is withdrawn from the intranet and kept in the archive. Staff are told
        about every material change, and training material is updated to match.
        """,
    )


def _appendix_requirements(facts: Facts) -> m.Section:
    s = facts.get("security")
    c = facts.get("continuity")
    p = facts.get("privacy")
    regions = " and ".join(s["data_residency"])
    pentest = s["pentest_frequency"].capitalize()
    return section(
        "Appendix A. Summary of key requirements",
        f"""
        The table collects the numerical and technical requirements that customers ask about most
        often, with the section that states each one. The sections remain the authoritative text.

        | Topic | Requirement | Section |
        |---|---|---|
        | Multi-factor authentication | Required for all staff | 9.2 |
        | Password length | At least {s["password_min_length"]} characters | 9.2 |
        | Encryption at rest | {s["encryption_at_rest"]} | 10.2 |
        | Encryption in transit | {s["encryption_in_transit"]} | 10.3 |
        | Key rotation | At least every {s["key_rotation_days"]} days | 10.4 |
        | Data hosting regions | {regions} | 11.1 |
        | Deletion of customer data | Within {p["customer_data_deletion_days"]} days of request or
          contract end | 11.4 |
        | Critical vulnerability patching | Within {s["patch_sla_days"]["critical"]} days | 12.2 |
        | High vulnerability patching | Within {s["patch_sla_days"]["high"]} days | 12.2 |
        | Log retention | {s["log_retention_days"]} days | 13.2 |
        | Penetration testing | {pentest}, by an independent firm | 14.1 |
        | Customer incident notification | Within {s["incident_notification_hours"]} hours of
          awareness | 19.4 |
        | Backup frequency | {c["backup_frequency"].capitalize()} | 20.1 |
        | Recovery point objective | {c["rpo_hours"]} hours | 20.2 |
        | Recovery time objective | {c["rto_hours"]} hours | 20.2 |
        Caption: Table 14. Key requirements and where they are stated
        """,
    )


def _appendix_related() -> m.Section:
    return section(
        "Appendix B. Related documents",
        """
        This policy is supported by the documents below. When one of them disagrees with this
        policy, this policy prevails, as section 3.4 explains.

        | Document | Purpose |
        |---|---|
        | Security Architecture | Describes how the platform is built and protected |
        | Business Continuity, Disaster Recovery and Incident Response Plan | Procedures that
          carry out sections 19 and 20 |
        | Support Policy and Service Level Agreement | The service commitments made to customers |
        | ISO/IEC 27001 Certification Package | Evidence of the certified management system |
        | Employee Handbook | Conduct, leave and working arrangements for staff |
        Caption: Table 15. Related documents
        """,
    )
