"""DOC-001 Information Security Policy, part 3: sections 12 to 18 (security operations)."""

from app.datagen import model as m
from app.datagen.facts import Facts
from app.datagen.markup import section


def sections(facts: Facts, entry) -> tuple[m.Section, ...]:
    return (
        _vulnerabilities(facts),
        _logging(facts),
        _testing(facts),
        _change(),
        _suppliers(),
        _people(),
        _physical(),
    )


def _vulnerabilities(facts: Facts) -> m.Section:
    critical = facts.get("security.patch_sla_days.critical")
    high = facts.get("security.patch_sla_days.high")
    return section(
        "12. Vulnerability and patch management",
        f"""
        Weaknesses in software are found every day, and attackers move quickly once a fix is
        published. This section sets how quickly the company must find and close them.

        ### 12.1 Finding vulnerabilities

        Production systems, container images and code dependencies are scanned for known
        vulnerabilities on a regular schedule and whenever they change. The security team also
        follows vendor advisories and public vulnerability feeds for the software the company
        uses. Each finding is recorded in the vulnerability register with an owner and a rating
        based on severity and on whether the weakness can be reached from the internet.

        ### 12.2 Patching deadlines

        Fixes must be applied within the deadlines in table 11, counted from the day the fix or
        a workaround is available. Critical vulnerabilities must be patched within {critical}
        days and high vulnerabilities within {high} days.

        | Severity | Deadline | Notes |
        |---|---|---|
        | Critical | {critical} days | Treated as an emergency change if it is exploitable from the
          internet |
        | High | {high} days | Scheduled with the next available maintenance window at the latest |
        | Medium | 90 days | Grouped into regular release cycles |
        | Low | Next scheduled maintenance | Fixed when the affected component is next changed |
        Caption: Table 11. Patching deadlines by severity

        If a fix cannot be applied within the deadline, the system owner must apply a
        compensating control, such as blocking the vulnerable feature or restricting network
        access, and request an exception under section 7.5.

        ### 12.3 Evidence

        Evidence includes scan reports, the vulnerability register with dates of discovery and
        closure, change tickets for patches, and a monthly report of overdue items to the
        Information Security Manager.
        """,
    )


def _logging(facts: Facts) -> m.Section:
    logs = facts.get("security.log_retention_days")
    return section(
        "13. Logging and monitoring",
        f"""
        Logs make it possible to detect an attack, to understand what happened and to prove it
        to a customer or auditor. This section sets what is logged, how long the logs are kept
        and how they are watched.

        ### 13.1 What is logged

        Production systems, identity services and network devices must record sign-ins and
        failures, privileged actions, changes to configuration and permissions, access to
        Restricted information, and security tool alerts. Application logs must never contain
        passwords, keys or the contents of customer files.

        ### 13.2 Protection and retention

        Logs are sent to a central log pipeline as soon as they are produced, so that an
        attacker who gains control of one server cannot erase the record. Access to the log
        store is limited to the security team and is itself logged. Security and audit logs
        are retained for {logs} days.

        ### 13.3 Monitoring and alerting

        The security team defines detection rules for the events that matter most, such as
        repeated failed sign-ins, use of privileged accounts outside approved hours, and
        unexpected changes to data stores. Alerts go to the on-call engineer through the
        metrics and alerting service, and each alert that is judged to be real is recorded as
        a security event and handled under section 19. Clocks on all systems are synchronised to
        a common time source so that logs from different systems can be compared.

        ### 13.4 Evidence

        Evidence includes the log pipeline configuration, the retention settings, the list of
        detection rules, and samples of alerts together with the tickets that show how each one
        was handled.
        """,
    )


def _testing(facts: Facts) -> m.Section:
    frequency = facts.get("security.pentest_frequency")
    return section(
        "14. Security testing",
        f"""
        Testing shows whether controls work in practice, and it finds problems that reviews and
        scans cannot.

        ### 14.1 Penetration testing

        An independent specialist firm performs a penetration test of the platform on an
        {frequency} basis and after any major change to its architecture. The scope covers the
        web application, the programming interfaces, the supporting infrastructure and the
        authentication and authorisation mechanisms. Testers are bound by a confidentiality
        agreement and a signed statement of the rules of engagement.

        ### 14.2 Handling findings

        The firm reports findings with a severity rating. Critical and high findings are
        treated as vulnerabilities under section 12 and fixed within the same deadlines. Medium
        and low findings are added to the engineering backlog and planned. After fixes are
        made, the affected area is retested to confirm the problem is closed.

        ### 14.3 Other testing

        Static analysis, dependency checks and secret scanning run on every code change.
        Dynamic scanning runs against the test environment before each release. The security
        team also runs exercises, such as simulated phishing and tabletop incident drills, so
        that people practise the response before a real event.

        ### 14.4 Sharing results

        Customers may ask for a summary of the latest penetration test. The security team
        prepares the summary, removes technical detail that would help an attacker, and shares
        it under a confidentiality agreement. The full report is Confidential and is not
        released.

        ### 14.5 Evidence

        Evidence includes the penetration test reports, the retest confirmations, the pipeline
        records of automated scans, and the notes and actions from exercises.
        """,
    )


def _change() -> m.Section:
    return section(
        "15. Change management and secure development",
        """
        Most outages and many security incidents begin with a change. This section keeps
        changes controlled and builds security into the way software is written.

        ### 15.1 Change control

        Every change to production is recorded in a ticket that describes what will change, why,
        how it will be tested and how it can be reversed. A person other than the author
        reviews and approves the change. Standard low-risk changes may be pre-approved by the
        Head of IT Operations. Emergency changes may be made without prior approval to restore
        service or to close a critical vulnerability, but they must be recorded and reviewed
        within five working days.

        ### 15.2 Secure development lifecycle

        - Security requirements and threat modelling are part of the design of any feature that
        handles customer data or changes authentication or authorisation.
        - All code is reviewed by at least one other engineer before it is merged, and the
        reviewer checks for security issues as well as correctness.
        - The build pipeline runs automated tests, static analysis, dependency checks and secret
        scanning, and a failing check blocks the release.
        - Developers receive training on secure coding at induction and each year after.

        ### 15.3 Separate environments

        Development, test and production environments are separate, with separate credentials
        and access lists. Real customer data must not be used in development or test
        environments. Where realistic data is needed, engineers use synthetic or masked data
        approved by the Data Protection Officer.

        ### 15.4 Evidence

        Evidence includes change tickets with approvals, code review records, pipeline results,
        and training records for engineers.
        """,
    )


def _suppliers() -> m.Section:
    return section(
        "16. Supplier and third-party security",
        """
        The company relies on suppliers for hosting, testing and business tools. A weakness at a
        supplier can become a weakness for customers, so suppliers are managed under this policy.

        ### 16.1 Selection and due diligence

        Before a supplier is engaged, the business owner and the security team assess the
        supplier according to the sensitivity of the information it will handle. The assessment
        looks at the supplier's certifications, its security practices, its financial standing
        and where it will process data. Suppliers that will host or access customer data must
        be able to keep that data in the regions described in section 11.

        ### 16.2 Contracts

        Contracts with suppliers that handle company or customer information must include
        confidentiality obligations, security requirements that match this policy, the right to
        audit or to receive audit reports, a duty to report incidents promptly, and terms for
        returning or deleting data when the contract ends.

        ### 16.3 Ongoing oversight

        Each important supplier has an owner who reviews its performance and security evidence
        every year. The security team reviews reports and certificates when they are renewed and
        follows up on any exception noted. The company keeps a register of suppliers that
        handle customer data and shares the list with customers who ask for it.

        ### 16.4 Hosting provider

        The infrastructure that hosts the platform is provided by a third-party hosting
        provider. The provider is responsible for physical and environmental security of its
        data centres, and the company is responsible for the configuration of everything that
        runs on that infrastructure, including access, encryption and logging.

        ### 16.5 Evidence

        Evidence includes supplier assessments, signed contracts, annual review records and the
        register of suppliers that handle customer data.
        """,
    )


def _people() -> m.Section:
    return section(
        "17. People security and awareness",
        """
        People are the company's strongest control when they are well chosen, well informed and
        well supported.

        ### 17.1 Before employment

        The Head of People verifies identity, employment history and qualifications for every
        candidate, and carries out background checks that are lawful in the country of
        employment and proportionate to the role. Roles with privileged access or access to
        Restricted information receive additional screening.

        ### 17.2 During employment

        Employment contracts and contractor agreements include confidentiality and acceptable
        use obligations. Every new starter completes security induction before receiving access
        to production systems or customer data. All personnel complete security awareness
        training every year, and engineers and administrators receive extra role-based
        training. The company records attendance and test results.

        ### 17.3 Responsibilities and discipline

        Personnel must report suspected incidents, lost devices and suspicious messages
        immediately and without fear of blame. Deliberate or repeated breaches of this policy
        are handled under the disciplinary process, and serious breaches may lead to
        termination of employment or contract and, where the law allows, legal action.

        ### 17.4 Leaving the company

        When someone leaves or changes role, the Head of People starts the departure process,
        access is removed as described in section 9.1, company devices and badges are returned,
        and the person is reminded in writing that their confidentiality obligations continue.

        ### 17.5 Evidence

        Evidence includes screening records, signed agreements, training completion reports,
        phishing exercise results and departure checklists.
        """,
    )


def _physical() -> m.Section:
    return section(
        "18. Physical and environmental security",
        """
        Physical access to people, devices and paper can bypass technical controls, so premises
        and equipment are protected as well.

        ### 18.1 Offices

        Company offices use controlled entry with badges, and visitors sign in, wear a visitor
        badge and are escorted. Network equipment is kept in locked rooms or cabinets. Staff keep
        their desks clear of Confidential and Restricted material when they leave them, and lock
        their screens when they step away. Printing of Restricted information is avoided, and
        printed copies are collected promptly and shredded after use.

        ### 18.2 Data centres

        Customer data is hosted in data centres operated by the hosting provider described in
        section 16.4. The provider is required to control physical access, to protect against
        fire, flood and power loss, and to supply evidence, such as independent audit reports,
        that these protections are in place. The company reviews that evidence each year.

        ### 18.3 Equipment

        Company laptops are tracked in the asset inventory, encrypted and protected by screen
        locks. Equipment taken out of the office remains the responsibility of the person who
        holds it, who must not leave it unattended in a vehicle or a public place.

        ### 18.4 Evidence

        Evidence includes visitor logs, badge access lists, supplier audit reports for the
        data centres, and records of equipment issue and return.
        """,
    )
