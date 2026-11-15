"""DOC-001 Information Security Policy, part 1: sections 1 to 7 (framework and governance)."""

from app.datagen import model as m
from app.datagen.facts import Facts, long_date
from app.datagen.markup import section


def sections(facts: Facts, entry) -> tuple[m.Section, ...]:
    return (
        _document_control(facts, entry),
        _purpose(facts),
        _scope(facts),
        _definitions(),
        _principles(facts),
        _roles(),
        _governance(),
    )


def _document_control(facts: Facts, entry) -> m.Section:
    reg = facts.get("policy_register.information_security_policy")
    v1 = facts.get("old_documents.security_policy_v1")
    effective = long_date(reg["current_effective"])
    approved = long_date(entry.document_date)
    v1_effective = long_date(v1["effective"])
    return section(
        "1. Document control",
        f"""
        This section records who owns this policy, which version is in force, what changed
        between versions and who approved it. Readers who rely on this policy as evidence for a
        customer, auditor or regulator should always confirm that they hold the version
        described here.

        ### 1.1 Document information

        | Field | Value |
        |---|---|
        | Title | {entry.title} |
        | Document number | {reg["document_number"]} |
        | Current version | {reg["current_version"]} |
        | Effective date | {effective} |
        | Policy owner | {reg["owner"]} |
        | Review cycle | Every {reg["review_cycle_months"]} months, or sooner after a
          significant change |
        | Classification | Internal |
        Caption: Table 1. Key facts about this document

        ### 1.2 Revision history

        | Version | Effective | Summary of change | Author |
        |---|---|---|---|
        | 1 | {v1_effective} | First release of the policy for the whole company |
          Information Security Manager |
        | 2 | {effective} | Full revision. Multi-factor authentication now applies to all
          staff rather than administrators only, the minimum password length rises from
          {v1["claims"]["password_min_length"]} to
          {facts.get("security.password_min_length")} characters, and log retention rises
          from {v1["claims"]["log_retention_days"]} to
          {facts.get("security.log_retention_days")} days | Information Security Manager |
        Caption: Table 2. Revision history

        Version 1 of this policy was withdrawn on the day version 2 took effect. Any document,
        questionnaire answer or training slide that still quotes version 1 requirements is out of
        date and must be corrected by its owner.

        ### 1.3 Approval

        | Role | Responsibility | Date |
        |---|---|---|
        | Information Security Manager | Prepared the revision | {approved} |
        | Chief Information Security Officer | Reviewed and recommended | {approved} |
        | Head of Legal and Compliance | Confirmed legal and regulatory alignment |
          {approved} |
        | Chief Executive Officer | Approved for release | {approved} |
        Caption: Table 3. Approval record for version {reg["current_version"]}

        ### 1.4 Distribution

        This policy is classified Internal. It is available to every employee, to executives and
        to external auditors who are working under a confidentiality agreement. The policy is
        published on the company intranet, and the policy owner keeps the controlled master
        copy. Printed copies are uncontrolled and are valid only on the day they are printed.
        """,
    )


def _purpose(facts: Facts) -> m.Section:
    company = facts.get("company.name")
    return section(
        "2. Purpose and objectives",
        f"""
        {company} provides a cloud security and compliance platform to customers who trust it
        with evidence about their own controls, audits and suppliers. That information is often
        sensitive, and customers in regulated industries expect the company to protect it with
        the same care they would apply themselves. This policy sets out how {company} meets that
        expectation.

        The purpose of this policy is to establish the rules by which the company protects the
        confidentiality, integrity and availability of its information and of the information
        entrusted to it. It is the top-level policy of the company's information security
        management system, and every standard, procedure and guideline on the subject derives its
        authority from it.

        ### 2.1 Objectives

        The policy has six objectives.

        1. Protect customer data against unauthorised access, disclosure, alteration and loss.
        2. Keep the platform available to customers at the levels the company has promised in its
        service agreements.
        3. Meet the legal, regulatory and contractual obligations that apply to the company in
        each country where it operates or hosts data.
        4. Give customers and auditors clear evidence that controls exist and are working.
        5. Make security a shared responsibility, so that each person knows what is expected of
        them and has the tools to deliver it.
        6. Improve continuously, using incidents, test results and audit findings as inputs.

        ### 2.2 How this policy is used

        The policy is written to be read by three audiences. Employees use it to learn what they
        must and must not do. Managers use it to decide what to build, buy and approve. Customers
        and auditors use it to understand what the company has committed to. For that reason each
        requirement is stated as a plain rule that can be checked, and sections 8 to 21 end with
        the evidence that shows the rule is being followed.

        NOTE: Where this policy and a customer contract disagree, the stricter requirement applies
        until the Head of Legal and Compliance has resolved the difference in writing.
        """,
    )


def _scope(facts: Facts) -> m.Section:
    company = facts.get("company.name")
    hq = facts.get("company.headquarters")
    founded = facts.get("company.founded")
    return section(
        "3. Scope and applicability",
        f"""
        This policy applies to {company}, a company founded in {founded} and headquartered in
        {hq}. It covers every part of the organisation, including all departments, all offices
        and all remote working arrangements, and it applies to roughly 240 employees together
        with contractors, interns and temporary staff who have access to company systems or data.

        ### 3.1 Information and systems in scope

        The policy covers information in every form and the systems that handle it.

        - Customer data stored, processed or transmitted by the platform, including uploaded
        evidence, generated reports and account details.
        - Company information such as source code, design documents, financial records, staff
        records and commercial agreements.
        - The production platform, the services that support it, and the environments used to
        develop and test it.
        - Corporate systems such as email, collaboration tools, identity services and the laptops
        and phones used to reach them.
        - Paper records, removable media and spoken information, where they contain anything
        classified above Public.

        ### 3.2 Locations and hosting

        The platform is operated for customers in India and the European Union, and customer data
        is hosted in those two regions. Infrastructure is provided by a third-party hosting
        provider, whose responsibilities are covered in section 16. Nothing in this policy
        permits customer data to be moved outside the region in which the customer chose to
        store it, except as section 11 allows.

        ### 3.3 Out of scope

        Personal devices and personal accounts of staff are out of scope unless they are used to
        reach company systems, in which case the access rules in section 9 apply to that use.
        Information that the company has deliberately made public, such as marketing material and
        published certificates, is out of scope for the confidentiality rules but remains
        subject to the integrity rules, so that the public statement is accurate.

        ### 3.4 Relationship to other documents

        This policy is supported by topic standards for access control, cryptography, secure
        development, supplier management, incident response and business continuity. If a
        standard appears to conflict with this policy, this policy prevails and the standard
        must be corrected. Appendix B lists the related documents.
        """,
    )


def _definitions() -> m.Section:
    return section(
        "4. Definitions",
        """
        The terms below have the meanings given here wherever they appear in this policy. Where a
        term is capitalised in another company document and defined there, that definition applies
        to that document only.

        | Term | Meaning |
        |---|---|
        | Asset | Anything of value to the company, including information, software,
          hardware, services and people |
        | Availability | The property of being accessible and usable when an authorised
          person needs it |
        | Confidentiality | The property that information is not made available to people or
          systems that are not authorised to see it |
        | Customer data | Any information that a customer or its users place in, or generate
          through, the platform |
        | Encryption | Transforming data with a cryptographic algorithm and key so that only
          holders of the key can read it |
        | Incident | An event that compromises, or may compromise, the confidentiality,
          integrity or availability of information or services |
        | Integrity | The property that information is accurate and has not been altered
          without authority |
        | Least privilege | Granting a person or system only the access needed to do the
          task at hand |
        | Multi-factor authentication | Proving identity with two or more independent
          factors, such as a password and a one-time code from a device |
        | Personnel | Employees, contractors, interns and any other individuals working
          under the company's direction |
        | Production | The live environment that serves customers |
        | Risk | The combination of how likely a harmful event is and how severe its effect
          would be |
        | Security event | Any observable occurrence that could be relevant to security,
          whether or not it proves harmful |
        | Third party | An organisation outside the company that supplies a product or
          service, or that has access to company information |
        | Vulnerability | A weakness in a system, process or control that a threat could
          exploit |
        Caption: Table 4. Defined terms

        The words "must" and "must not" state mandatory requirements. "Should" states a strong
        recommendation that may be set aside only with a documented reason. "May" states a
        permitted option.
        """,
    )


def _principles(facts: Facts) -> m.Section:
    return section(
        "5. Security principles",
        """
        Eight principles guide every decision made under this policy. They are used when a
        specific rule is silent, and they are the first thing a reviewer checks when judging a
        proposed exception.

        ### 5.1 Protect what customers entrust to us

        Customer data is the most valuable and most sensitive asset the company handles. When two
        goals conflict, such as shipping a feature quickly and protecting customer data, the
        protection of customer data wins unless the Chief Information Security Officer decides
        otherwise in writing.

        ### 5.2 Least privilege and need to know

        People and systems receive the minimum access that lets them do their work, for the
        shortest time that is practical. Access to information is granted because a person needs it
        to perform a defined task, not because of seniority or convenience.

        ### 5.3 Defence in depth

        No single control is trusted to stop every attack. Preventive, detective and corrective
        controls are layered so that the failure of one does not expose customer data. A network
        control, for example, is backed by authentication, by authorisation and by encryption.

        ### 5.4 Secure by default

        Systems are delivered with the safe setting enabled. A person who wants a less restrictive
        setting must ask for it and justify it, and the exception is recorded and reviewed.

        ### 5.5 Separation of duties

        No individual should be able to complete a critical action alone where the action could
        cause serious harm. Requests, approvals and reviews are made by different people, and
        production access is separate from development access.

        ### 5.6 Evidence over assertion

        A control is considered to exist only if the company can show evidence of it. Logs,
        tickets, test results and signed records are preferred to statements that something is
        done. This principle is why the later sections each list the evidence they produce.

        ### 5.7 Accountability

        Every asset, system and risk has a named owner. Actions on systems are traceable to an
        individual, and shared accounts are not permitted for human users.

        ### 5.8 Continuous improvement

        The company treats each incident, near miss, audit finding and test result as an
        opportunity to strengthen a control. Lessons are recorded, assigned and tracked to
        completion rather than left in a report.
        """,
    )


def _roles() -> m.Section:
    return section(
        "6. Roles and responsibilities",
        """
        Security is everyone's job, but specific people carry specific duties. The table
        summarises the main roles, and the paragraphs below it describe the duties in more detail.

        | Role | Main responsibilities under this policy |
        |---|---|
        | Chief Executive Officer | Approves the policy, provides resources and holds
          leaders accountable for security results |
        | Chief Information Security Officer | Owns the policy and the security programme,
          reports on risk to the leadership team and approves exceptions |
        | Information Security Manager | Maintains standards, runs the risk process,
          coordinates audits and manages security tooling |
        | Head of Engineering | Ensures that products are built and released in line with
          the secure development rules |
        | Head of IT Operations | Operates the production platform and corporate systems to
          the standards in this policy |
        | Head of People | Applies the people security rules from hiring to departure |
        | Head of Legal and Compliance | Tracks legal, regulatory and contractual
          obligations and advises on their effect |
        | Data Protection Officer | Oversees privacy compliance and acts as the contact
          point for regulators and data subjects |
        | Asset and system owners | Classify their assets, approve access and keep controls
          working |
        | Line managers | Make sure their teams know and follow the policy and report
          concerns promptly |
        | All personnel | Follow the policy, complete training and report incidents and
          suspicious activity |
        Caption: Table 5. Summary of roles

        ### 6.1 Leadership

        The Chief Executive Officer approves this policy and is ultimately accountable for the
        company's security posture. The Chief Information Security Officer is accountable for the
        design and operation of the security programme, has direct access to the Chief Executive
        Officer, and reports on risk, incidents and audit results to the leadership team every
        quarter.

        ### 6.2 Security function

        The Information Security Manager and the security team turn the policy into standards and
        controls, operate the security tooling, run vulnerability management and monitoring,
        coordinate incident response, and prepare the evidence that customers and auditors ask
        for. The team advises other functions but does not take over their accountability: the
        owner of a system remains responsible for its security.

        ### 6.3 Engineering and operations

        The Head of Engineering is responsible for secure design, code review, testing and release
        practices. The Head of IT Operations is responsible for the build and running of the
        production platform, for backups, for patching and for the monitoring that feeds incident
        detection. Both report any control they cannot meet to the Chief Information Security
        Officer without delay.

        ### 6.4 People, legal and privacy

        The Head of People runs background checks, contracts, induction, training records and the
        departure process. The Head of Legal and Compliance maintains the register of legal,
        regulatory and contractual obligations. The Data Protection Officer monitors compliance
        with privacy law in the jurisdictions the company serves.

        ### 6.5 Owners, managers and personnel

        Each asset and system has an owner who decides who may use it, who classifies the
        information in it, and who answers for its risks. Line managers ensure that new starters
        are enrolled in training, that access matches job needs, and that leavers are reported on
        time. Every person working for the company must follow this policy, complete the required
        training and report any incident or weakness they notice.
        """,
    )


def _governance() -> m.Section:
    return section(
        "7. Governance and risk management",
        """
        Governance is how the company decides what security matters most, who decides it, and how
        it knows the decision was carried out. This section describes the committees, the risk
        process and the exception process that sit behind every other section of the policy.

        ### 7.1 Information Security Steering Committee

        The committee brings together the Chief Information Security Officer, the Head of
        Engineering, the Head of IT Operations, the Head of People, the Head of Legal and
        Compliance and the Data Protection Officer. It meets every quarter and when the Chief
        Information Security Officer calls an extraordinary meeting.

        The committee reviews the risk register, approves new standards, follows up on audit
        findings and incident actions, and checks that the security budget matches the risks the
        company has chosen to treat. Minutes record each decision, the person responsible and the
        due date. The minutes are kept as evidence for audits.

        ### 7.2 Risk management process

        The company manages security risk through a repeating cycle of five steps.

        1. Identify. Owners, engineers and the security team list the threats and weaknesses that
        affect their assets, using incident history, test results, supplier reports and
        threat intelligence.
        2. Analyse. Each risk is rated for likelihood and impact on a five-point scale, giving a
        score that places it in the low, medium, high or critical band.
        3. Evaluate. The score is compared with the company's stated tolerance. Anything above the
        tolerance must be treated or formally accepted.
        4. Treat. The owner chooses to reduce, transfer, avoid or accept the risk, and records the
        action, the person responsible and the date.
        5. Monitor. The register is reviewed every quarter, and a risk is re-rated whenever its
        circumstances change.

        ### 7.3 Risk register and treatment plans

        All risks above the low band are entered in the central risk register. Each entry has an
        owner, a rating before and after treatment, the controls that apply and the status of any
        open actions. Critical and high risks are reported to the Information Security Steering
        Committee at its next meeting and no later than the end of the quarter in which they were
        found.

        | Band | Meaning | Required action |
        |---|---|---|
        | Critical | Could cause severe harm to customers or the company if it occurs |
          Immediate treatment plan and leadership notification |
        | High | Likely to cause significant harm without action | Treatment plan agreed
          within the quarter |
        | Medium | Could cause moderate harm | Treat or accept at owner level with security
          review |
        | Low | Minor effect | Monitor, no register entry required |
        Caption: Table 6. Risk bands and required action

        ### 7.4 Risk acceptance

        Only the Chief Information Security Officer, or a more senior leader, may accept a high
        risk. A critical risk may be accepted only by the Chief Executive Officer, and only for a
        stated period. A person may not accept a risk that arises from their own work without a
        second approver.

        ### 7.5 Exceptions to this policy

        Where a requirement cannot be met, the owner of the affected system may ask for an
        exception. The request describes the requirement, the reason it cannot be met, the risk
        created, the compensating controls and the date by which the gap will close. The Chief
        Information Security Officer decides, and a granted exception lasts no longer than six
        months. An exception can be renewed only after the request has been reviewed again, and
        all exceptions are listed in the register that the steering committee reviews each
        quarter.

        IMPORTANT: An exception never removes the duty to report an incident, to protect customer
        data or to comply with the law.

        ### 7.6 Measuring and reporting

        The security team reports a small set of measures to the steering committee every quarter.
        These include the number of open critical and high risks, the age of overdue actions, the
        time taken to patch, the completion of security training, the number and severity of
        incidents, and the status of supplier reviews. The measures are chosen to show whether
        controls work, not only whether they exist.
        """,
    )
